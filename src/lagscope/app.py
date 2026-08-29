"""Application wiring: overlay + tray + settings + monitoring thread."""

from __future__ import annotations

import copy
import json
import logging
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, REPO_URL, __version__
from .autostart import get_autostart, is_supported as autostart_supported, set_autostart
from .config import Config, app_config_dir
from .i18n import set_language, tr
from .events import SPIKE, STALL, EventLog, Notifier
from .history import History
from .models import (
    KIND_APP, KIND_LIVE, KIND_NETWORK, KIND_TARGET, KIND_VIDEO, LatencySample, RollingStats,
    WatchTarget,
)
from .monitor import (
    MonitorWorker, STATUS_ERROR, STATUS_NO_ROOM, STATUS_OFFLINE, STATUS_OK, STATUS_PAUSED,
)
from .probes.display import DisplayProbe
from .recording import CsvRecorder
from .report import (
    build_html, build_text, default_report_path, write_report,
)
from .single_instance import SingleInstance
from .web import DashboardServer
from .ui.icons import app_icon
from .ui.theme import format_mbps, format_ms, level_for
from .ui.overlay import OverlayWindow
from .ui.history_window import HistoryWindow
from .ui.settings import SettingsDialog
from .ui.tray import TrayIcon

LOG = logging.getLogger(__name__)

DISPLAY_PUSH_INTERVAL_MS = 1000
CONFIG_SAVE_DEBOUNCE_MS = 1500
CLIPBOARD_POLL_INTERVAL_MS = 1500
HISTORY_FLUSH_INTERVAL_MS = 60_000
# Probe error codes that have a sentence a person can act on.
ERROR_MESSAGES = {
    "no-connections": "status.no_connections",
    "no-reply": "status.no_reply",
    "unreachable": "status.unreachable",
    "no-app": "status.no_app",
    "no-video": "status.no_video",
    "no-room": "status.no_room",
}
MAX_CLIPBOARD_CHARS = 4096


class MonitorApplication(QObject):
    """Owns every long-lived object; one instance per process.

    Everything the worker must do is requested through these signals: the
    worker lives in another thread, and touching its timers directly from the
    GUI thread is not allowed by Qt.
    """

    configChanged = Signal(object)
    pauseRequested = Signal(bool)
    stopRequested = Signal()
    clipboardText = Signal(str)
    diagnosisRequested = Signal()

    def __init__(self, app: QApplication, config: Config,
                 instance: Optional[SingleInstance] = None) -> None:
        super().__init__()
        self._app = app
        self._config = config.sanitized()
        self._stats = RollingStats(self._config.sample_window)
        self._display = DisplayProbe()
        self._recorder: Optional[CsvRecorder] = None
        self._settings_dialog: Optional[SettingsDialog] = None
        self._status_key = STATUS_OK
        self._status_detail = ""
        self._paused = False
        self._room_title = ""
        self._target: Optional[WatchTarget] = None
        self._room_info = None
        self._lines: tuple = ("", [])
        self._events = EventLog()
        self._notifier = Notifier()
        self._extras: dict = {}      # key -> ExtraResult, newest per side watch
        self._dashboard: Optional[DashboardServer] = None
        self._history = History(bucket_s=self._config.history.bucket_s,
                                keep_hours=self._config.history.keep_hours)
        self._history_window: Optional[HistoryWindow] = None
        # Kept so an exported report carries the last check, not a blank section.
        self._last_diagnosis: Optional[tuple] = None

        self._overlay = OverlayWindow(self._config, self._display)
        self._overlay.positionChanged.connect(self._on_overlay_moved)
        self._overlay.contextMenuRequested.connect(self._show_menu_at)
        self._overlay.doubleClicked.connect(self._toggle_compact)

        self._tray: Optional[TrayIcon] = None
        self._menu = QMenu()
        self._build_menu()
        self._setup_tray()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_config_now)

        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._push_display_latency)
        self._display_timer.start(DISPLAY_PUSH_INTERVAL_MS)

        # History is written once a minute, not once a sample: a crash costs
        # at most the minute in progress.
        self._history_timer = QTimer(self)
        self._history_timer.timeout.connect(self._flush_history)
        self._history_timer.start(HISTORY_FLUSH_INTERVAL_MS)

        self._thread = QThread(self)
        # The worker gets its own copy: the GUI thread keeps mutating settings.
        self._worker = MonitorWorker(copy.deepcopy(self._config))
        self._worker.moveToThread(self._thread)
        self._worker.sampleReady.connect(self._on_sample)
        self._worker.statusChanged.connect(self._on_status)
        self._worker.roomInfoChanged.connect(self._on_room_info)
        self._worker.targetChanged.connect(self._on_target)
        self._worker.linesChanged.connect(self._on_lines)
        self._thread.started.connect(self._worker.start)
        self.configChanged.connect(self._worker.applyConfig)
        self.pauseRequested.connect(self._worker.setPaused)
        self.stopRequested.connect(self._worker.stop)
        self.clipboardText.connect(self._worker.submitClipboard)
        self.diagnosisRequested.connect(self._worker.runDiagnosis)
        self._worker.diagnosisReady.connect(self._on_diagnosis)
        self._worker.extraUpdated.connect(self._on_extra)

        # The clipboard belongs to the GUI thread, so it is polled here and the
        # text is handed to the worker, which does the parsing and any lookup.
        self._clipboard_timer = QTimer(self)
        self._clipboard_timer.timeout.connect(self._poll_clipboard)
        self._last_clipboard = ""
        if self._config.detect.enabled and self._config.detect.use_clipboard:
            self._clipboard_timer.start(CLIPBOARD_POLL_INTERVAL_MS)

        self._instance = instance or SingleInstance()
        self._instance.setParent(self)
        self._instance.activated.connect(self._on_second_instance)

        self._apply_recording()
        self._apply_dashboard()
        app.aboutToQuit.connect(self._shutdown)

    # ------------------------------------------------------------------ start
    def start(self) -> None:
        if self._config.overlay.enabled:
            self._overlay.show()
        self._update_status_text()
        self._thread.start()

    def instance_guard(self) -> SingleInstance:
        return self._instance

    # ------------------------------------------------------------------- menu
    def _build_menu(self) -> None:
        self._menu.clear()

        self._action_overlay = QAction(tr("menu.show_overlay"), self._menu, checkable=True)
        self._action_overlay.setChecked(self._config.overlay.enabled)
        self._action_overlay.toggled.connect(self._set_overlay_visible)
        self._menu.addAction(self._action_overlay)

        self._action_lock = QAction(tr("menu.lock"), self._menu, checkable=True)
        self._action_lock.setChecked(self._config.overlay.locked)
        self._action_lock.toggled.connect(self._set_locked)
        self._menu.addAction(self._action_lock)

        self._action_click_through = QAction(tr("menu.click_through"), self._menu, checkable=True)
        self._action_click_through.setChecked(self._config.overlay.click_through)
        self._action_click_through.toggled.connect(self._set_click_through)
        self._menu.addAction(self._action_click_through)

        self._menu.addSeparator()

        self._action_detect = QAction(tr("menu.auto_detect"), self._menu, checkable=True)
        self._action_detect.setChecked(self._config.detect.enabled)
        self._action_detect.toggled.connect(self._set_auto_detect)
        self._menu.addAction(self._action_detect)

        diagnose_action = QAction(tr("menu.diagnose"), self._menu)
        diagnose_action.triggered.connect(self._run_diagnosis)
        self._menu.addAction(diagnose_action)

        history_action = QAction(tr("menu.history"), self._menu)
        history_action.triggered.connect(self.open_history)
        self._menu.addAction(history_action)

        report_action = QAction(tr("menu.report"), self._menu)
        report_action.triggered.connect(self.export_report)
        self._menu.addAction(report_action)

        phone_action = QAction(tr("menu.phone"), self._menu)
        phone_action.triggered.connect(self._show_phone_url)
        self._menu.addAction(phone_action)

        clipboard_action = QAction(tr("menu.read_clipboard"), self._menu)
        clipboard_action.triggered.connect(self._read_clipboard_now)
        self._menu.addAction(clipboard_action)

        theme_menu = self._menu.addMenu(tr("overlay.theme"))
        theme_group = QActionGroup(theme_menu)
        theme_group.setExclusive(True)
        for theme in ("dark", "light", "pink"):
            action = QAction(tr(f"overlay.theme.{theme}"), theme_menu, checkable=True)
            action.setChecked(self._config.overlay.theme == theme)
            action.triggered.connect(lambda _checked, name=theme: self._set_theme(name))
            theme_group.addAction(action)
            theme_menu.addAction(action)

        self._action_pause = QAction(
            tr("menu.resume") if self._paused else tr("menu.pause"), self._menu, checkable=True
        )
        # Rebuilt on a language change: keep the current state without re-firing.
        self._action_pause.blockSignals(True)
        self._action_pause.setChecked(self._paused)
        self._action_pause.blockSignals(False)
        self._action_pause.toggled.connect(self._set_paused)
        self._menu.addAction(self._action_pause)

        reset_action = QAction(tr("menu.reset_position"), self._menu)
        reset_action.triggered.connect(self._reset_position)
        self._menu.addAction(reset_action)

        self._menu.addSeparator()

        settings_action = QAction(tr("menu.settings"), self._menu)
        settings_action.triggered.connect(self.open_settings)
        self._menu.addAction(settings_action)

        diag_action = QAction(tr("menu.copy_diag"), self._menu)
        diag_action.triggered.connect(self._copy_diagnostics)
        self._menu.addAction(diag_action)

        folder_action = QAction(tr("menu.open_config"), self._menu)
        folder_action.triggered.connect(self._open_config_folder)
        self._menu.addAction(folder_action)

        about_action = QAction(tr("menu.about"), self._menu)
        about_action.triggered.connect(self._show_about)
        self._menu.addAction(about_action)

        self._menu.addSeparator()
        quit_action = QAction(tr("menu.quit"), self._menu)
        quit_action.triggered.connect(self._app.quit)
        self._menu.addAction(quit_action)

    def _setup_tray(self) -> None:
        if not self._config.tray.enabled:
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            LOG.warning("system tray not available")
            return
        self._tray = TrayIcon(self._config, self)
        self._tray.set_menu(self._menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._set_overlay_visible(not self._overlay.isVisible())
            self._action_overlay.setChecked(self._overlay.isVisible())

    def _show_menu_at(self, position) -> None:
        self._menu.popup(position)

    # ---------------------------------------------------------------- actions
    def _set_overlay_visible(self, visible: bool) -> None:
        self._config.overlay.enabled = bool(visible)
        if visible:
            self._overlay.show()
            self._overlay.reposition()
        else:
            self._overlay.hide()
        self._schedule_save()

    def _set_locked(self, locked: bool) -> None:
        self._config.overlay.locked = bool(locked)
        self._schedule_save()

    def _set_click_through(self, enabled: bool) -> None:
        self._config.overlay.click_through = bool(enabled)
        self._overlay.apply_config(self._config)
        if self._config.overlay.enabled:
            self._overlay.show()
        self._schedule_save()

    def _set_theme(self, theme: str) -> None:
        self._config.overlay.theme = theme
        self._overlay.apply_config(self._config)
        if self._tray is not None:
            self._tray.apply_config(self._config)
        self._schedule_save()

    def _set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        self._action_pause.setText(tr("menu.resume") if paused else tr("menu.pause"))
        self.pauseRequested.emit(self._paused)
        self._update_status_text()

    def _set_auto_detect(self, enabled: bool) -> None:
        self._config.detect.enabled = bool(enabled)
        self.configChanged.emit(copy.deepcopy(self._config))
        self._schedule_save()

    def _toggle_compact(self) -> None:
        self._config.overlay.compact = not self._config.overlay.compact
        self._overlay.apply_config(self._config)
        if self._config.overlay.enabled:
            self._overlay.show()
        self._schedule_save()

    def _reset_position(self) -> None:
        self._config.overlay.anchor_mode = "free"
        self._config.overlay.x = 80
        self._config.overlay.y = 80
        self._overlay.apply_config(self._config)
        self._overlay.show()
        self._schedule_save()

    def _on_overlay_moved(self, x: int, y: int) -> None:
        self._config.overlay.x = int(x)
        self._config.overlay.y = int(y)
        if self._config.overlay.anchor_mode != "free":
            self._config.overlay.anchor_mode = "free"
        self._schedule_save()

    def open_settings(self) -> None:
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self._config)
            self._settings_dialog.configApplied.connect(self.apply_config)
            self._settings_dialog.openConfigFolderRequested.connect(self._open_config_folder)
        else:
            self._settings_dialog.load_from(self._config)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _run_diagnosis(self) -> None:
        """Kick off the segment-by-segment check and tell the user to wait."""
        if self._tray is not None:
            self._tray.showMessage(tr("diag.title"), tr("diag.running"), app_icon(), 4000)
        self.diagnosisRequested.emit()

    @Slot(object)
    def _on_diagnosis(self, payload) -> None:
        if payload is None:
            QMessageBox.warning(None, tr("diag.title"), tr("verdict.unknown"))
            return
        report, key, detail = payload
        self._last_diagnosis = payload
        QMessageBox.information(None, tr("diag.title"), self._diagnosis_text(report, key, detail))

    def _diagnosis_text(self, report, key: str, detail: str) -> str:
        """The result as something a person can read - and paste to a helpdesk."""
        lines = [f"{tr('diag.title')}: {report.target}", ""]
        rows = [
            (tr("diag.you_router"), report.gateway_stats),
            (tr("diag.router_isp"), report.hop_stats),
            (tr("diag.to_target"), report.target_stats),
        ]
        for label, stats in rows:
            if stats is None:
                lines.append(f"{label}:  --")
            elif not stats.ok:
                lines.append(f"{label}:  {stats.error or '--'}  ({stats.host})")
            else:
                lines.append(
                    f"{label}:  {format_ms(stats.avg_ms)}   "
                    f"{tr('diag.loss')} {stats.loss_pct:.0f}%   ({stats.host})"
                )
        if report.wifi is not None:
            wifi = report.wifi
            signal = f"{wifi.signal_pct}%" if wifi.signal_pct is not None else "--"
            lines.append(f"\n{tr('diag.wifi')}: {wifi.ssid or '--'}  {signal}  {wifi.radio}")
        if "gateway-silent" in report.notes:
            lines.append(tr("diag.gateway_silent"))
        lines.append("")
        lines.append(tr(key) + (f"  [{detail}]" if detail else ""))
        return "\n".join(lines)

    # -------------------------------------------------------------- history
    def open_history(self) -> None:
        """The chart of everything recorded so far, kept live while it is open."""
        if self._history_window is None:
            self._history_window = HistoryWindow(self._config, self._history)
            self._history_window.exportRequested.connect(self.export_report)
            self._history_window.copyRequested.connect(self._copy_report_summary)
        else:
            self._history_window.refresh()
        self._history_window.show()
        self._history_window.raise_()
        self._history_window.activateWindow()

    def _report_context(self) -> dict:
        """Everything the report needs, gathered from what is already known."""
        hours = 24.0
        if self._history_window is not None:
            hours = self._history_window.hours()
        path_report, verdict_key, verdict_detail = (self._last_diagnosis
                                                    or (None, "", ""))
        return {
            "buckets": self._history.buckets(hours),
            "summary": self._history.summary(hours),
            "bucket_s": self._history.bucket_s,
            "worst": self._history.worst_hour(hours),
            "path_report": path_report,
            "verdict_key": verdict_key,
            "verdict_detail": verdict_detail,
            "extras": self._ordered_extras(),
            "target_label": self._room_title or self._watch_label(),
            "good_ms": self._config.thresholds.good_ms,
            "warn_ms": self._config.thresholds.warn_ms,
        }

    def _watch_label(self) -> str:
        target = self._target
        if target is None or target.is_empty:
            return ""
        return target.title or target.ident

    def export_report(self) -> None:
        """Write the health report and open it in the browser."""
        self._flush_history()
        context = self._report_context()
        document = build_html(**context)
        try:
            path = write_report(document, default_report_path())
        except OSError as exc:
            LOG.warning("could not write the report: %s", exc)
            QMessageBox.warning(None, tr("report.title"), f"{tr('report.failed')}\n{exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        if self._tray is not None:
            self._tray.showMessage(tr("report.title"), f"{tr('report.saved')} {path}",
                                   app_icon(), 6000)

    def _copy_report_summary(self) -> None:
        """The same findings as text, for a forum reply or a chat message."""
        context = self._report_context()
        QGuiApplication.clipboard().setText(build_text(
            summary=context["summary"], worst=context["worst"],
            path_report=context["path_report"], verdict_key=context["verdict_key"],
            verdict_detail=context["verdict_detail"], target_label=context["target_label"],
        ))
        if self._tray is not None:
            self._tray.showMessage(tr("report.title"), tr("report.copied"), app_icon(), 4000)

    def _flush_history(self) -> None:
        if self._config.history.enabled:
            self._history.flush()

    def _show_phone_url(self) -> None:
        """Show (and copy) the address to type into a phone browser."""
        if self._dashboard is None:
            QMessageBox.information(None, tr("web.group"), tr("web.off"))
            return
        urls = self._dashboard.urls()
        if not urls:
            QMessageBox.information(None, tr("web.group"), tr("web.off"))
            return
        QGuiApplication.clipboard().setText(urls[0])
        QMessageBox.information(
            None, tr("web.group"),
            f"{tr('web.url_label')}\n\n" + "\n".join(urls) + f"\n\n{tr('web.copied')}",
        )

    def _copy_diagnostics(self) -> None:
        QGuiApplication.clipboard().setText(self.diagnostics_text())
        if self._tray is not None:
            self._tray.showMessage(APP_NAME, tr("notice.copied"), app_icon(), 3000)

    def _open_config_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_config_dir())))

    def _show_about(self) -> None:
        QMessageBox.information(
            None,
            f"{APP_NAME} {__version__}",
            f"{tr('about.body')}\n\n{REPO_URL}\n{app_config_dir()}",
        )

    # ----------------------------------------------------------------- config
    @Slot(object)
    def apply_config(self, config: Config) -> None:
        previous_language = self._config.language
        previous_autostart = self._config.autostart
        self._config = config.sanitized()

        if self._config.language != previous_language:
            set_language(self._config.language)
            self._build_menu()
            if self._tray is not None:
                self._tray.set_menu(self._menu)
            if self._settings_dialog is not None:
                self._settings_dialog.deleteLater()
                self._settings_dialog = None
            # Its labels are built once, so it is rebuilt in the new language too.
            if self._history_window is not None:
                self._history_window.deleteLater()
                self._history_window = None

        self._stats.resize(self._config.sample_window)
        self._overlay.apply_config(self._config)
        if self._config.overlay.enabled:
            self._overlay.show()
        else:
            self._overlay.hide()
        self._action_overlay.setChecked(self._config.overlay.enabled)
        self._action_lock.setChecked(self._config.overlay.locked)
        self._action_click_through.setChecked(self._config.overlay.click_through)
        self._action_detect.blockSignals(True)
        self._action_detect.setChecked(self._config.detect.enabled)
        self._action_detect.blockSignals(False)

        if self._config.tray.enabled and self._tray is None:
            self._setup_tray()
        elif self._tray is not None:
            self._tray.apply_config(self._config)
            self._tray.setVisible(self._config.tray.enabled)

        if self._config.autostart != previous_autostart and autostart_supported():
            if not set_autostart(self._config.autostart):
                self._config.autostart = bool(get_autostart())

        if self._config.detect.enabled and self._config.detect.use_clipboard:
            if not self._clipboard_timer.isActive():
                self._clipboard_timer.start(CLIPBOARD_POLL_INTERVAL_MS)
        else:
            self._clipboard_timer.stop()

        self._prune_extras()
        self._overlay.set_extras(self._ordered_extras())
        self._apply_recording()
        self._apply_history()
        self._apply_dashboard()
        self.configChanged.emit(copy.deepcopy(self._config))
        self._save_config_now()
        self._update_status_text()

    def _apply_dashboard(self) -> None:
        """Start, restart or stop the phone dashboard to match the settings."""
        web = self._config.web
        if self._dashboard is not None:
            same = (self._dashboard.port == web.port
                    and self._dashboard.access_code == web.access_code
                    and self._dashboard.bind_host == web.bind_host)
            if web.enabled and same:
                return
            self._dashboard.stop()
            self._dashboard = None
        if not web.enabled:
            return
        server = DashboardServer(web.port, web.access_code, web.bind_host)
        if server.start():
            self._dashboard = server
            self._publish_dashboard()
        else:
            LOG.warning("phone dashboard could not start on port %s", web.port)

    def _publish_dashboard(self) -> None:
        """Hand the current state to the dashboard in ready-to-render form."""
        if self._dashboard is None:
            return
        sample = self._stats.last()
        kind = sample.kind if sample else KIND_LIVE
        value = sample.total_ms if (sample and sample.ok) else None
        level = level_for(value, self._config.thresholds.good_ms,
                          self._config.thresholds.warn_ms)

        if kind == KIND_APP:
            rows = [
                (tr("label.latency"), format_ms(sample.network_ms if sample else None)),
                (tr("label.connections"), str(sample.connections) if sample and sample.connections else "--"),
                (tr("label.display"), format_ms(sample.display_ms if sample else None)),
            ]
        elif kind == KIND_TARGET:
            rows = [
                (tr("label.latency"), format_ms(sample.network_ms if sample else None)),
                (tr("label.display"), format_ms(sample.display_ms if sample else None)),
            ]
        else:
            second = tr("label.startup") if kind == KIND_VIDEO else tr("label.stream")
            rows = [
                (tr("label.network"), format_ms(sample.network_ms if sample else None)),
                (second, format_ms(sample.stream_ms if sample else None)),
                (tr("label.display"), format_ms(sample.display_ms if sample else None)),
            ]

        events = self._events.summary()
        stats = [
            (tr("label.avg"), format_ms(self._stats.avg())),
            (tr("label.p95"), format_ms(self._stats.percentile(95))),
            (tr("label.down"), format_mbps(sample.down_mbps if sample else None)),
            (tr("label.up"), format_mbps(sample.up_mbps if sample else None)),
        ]
        self._dashboard.publish({
            "ok": bool(sample and sample.ok),
            "total_ms": value,
            "level": level,
            "status": self._status_line() or (
                tr("label.measured") if (sample and not sample.estimated) else tr("label.estimated")
            ),
            "target": self._room_title or (sample.title if sample else ""),
            "rows": rows,
            "stats": stats,
            "spark": self._stats.spark_values(60),
            "extras": [
                {
                    "label": extra.label,
                    "value": format_ms(extra.rtt_ms) if extra.ok else "--",
                    "level": level_for(extra.rtt_ms if extra.ok else None,
                                       self._config.thresholds.good_ms,
                                       self._config.thresholds.warn_ms),
                }
                for extra in self._ordered_extras()
            ],
            "measured": bool(sample and not sample.estimated),
            "foot": f"{APP_NAME} {__version__} · {tr('label.jitter')} "
                    f"{format_ms(self._stats.jitter())} · "
                    f"{events['stalls'] + events['spikes']} / {events['window_min']}min",
        })

    def _apply_history(self) -> None:
        """Follow a changed retention setting without losing what is stored."""
        history = self._config.history
        if history.keep_hours != self._history.keep_hours or \
                history.bucket_s != self._history.bucket_s:
            self._history.close()
            self._history = History(bucket_s=history.bucket_s, keep_hours=history.keep_hours)
            if self._history_window is not None:
                self._history_window.deleteLater()
                self._history_window = None
        if not history.enabled:
            self._history.flush()
        if self._history_window is not None:
            self._history_window.apply_config(self._config)

    def _apply_recording(self) -> None:
        if self._config.recording.csv_enabled:
            if self._recorder is None:
                self._recorder = CsvRecorder(
                    max_bytes=self._config.recording.csv_max_bytes,
                    backups=self._config.recording.csv_backups,
                )
        elif self._recorder is not None:
            self._recorder.close()
            self._recorder = None

    def _schedule_save(self) -> None:
        self._save_timer.start(CONFIG_SAVE_DEBOUNCE_MS)

    def _save_config_now(self) -> None:
        try:
            self._config.save()
        except OSError as exc:
            LOG.warning("could not save config: %s", exc)

    # ------------------------------------------------------------------ data
    @Slot(object)
    def _on_extra(self, result) -> None:
        self._extras[result.key] = result
        self._prune_extras()
        self._overlay.set_extras(self._ordered_extras())
        self._publish_dashboard()

    def _prune_extras(self) -> None:
        """Forget watches the user has removed from the settings."""
        wanted = {
            f"{entry.get('kind', 'target')}:{str(entry.get('ident', '')).lower()}:"
            f"{entry.get('port') if entry.get('kind', 'target') == KIND_TARGET else ''}"
            for entry in self._config.watch_extras
        }
        for key in list(self._extras):
            if key not in wanted:
                self._extras.pop(key, None)

    def _ordered_extras(self) -> list:
        """In the order the user arranged them, not the order they answered."""
        ordered = []
        for entry in self._config.watch_extras:
            kind = entry.get("kind", "target")
            port = entry.get("port") if kind == KIND_TARGET else ""
            key = f"{kind}:{str(entry.get('ident', '')).lower()}:{port}"
            result = self._extras.get(key)
            if result is not None:
                ordered.append(result)
        return ordered

    @Slot(object)
    def _on_lines(self, payload) -> None:
        self._lines = payload

    @Slot(object)
    def _on_sample(self, sample: LatencySample) -> None:
        event = self._events.observe(sample)
        if event is not None:
            self._announce(event)
        self._stats.append(sample)
        if self._config.history.enabled:
            self._history.add(sample)
            if event is not None:
                self._history.note_event(event.kind)
            if self._history_window is not None and self._history_window.isVisible():
                self._history_window.refresh()
        self._overlay.update_sample(sample, self._stats)
        if self._tray is not None:
            self._tray.update_sample(sample, self._status_line())
        if self._recorder is not None:
            self._recorder.write(sample)
        self._publish_dashboard()

    @Slot(str, str)
    def _on_status(self, status: str, detail: str) -> None:
        self._status_key = status
        self._status_detail = detail
        self._update_status_text()

    def _announce(self, event) -> None:
        """One tray balloon per problem, never one per sample."""
        if self._tray is None or not self._config.notify_enabled:
            return
        if not self._notifier.should_notify():
            return
        if event.kind == STALL:
            text = tr("notice.stall")
        else:
            text = tr("notice.spike", value=format_ms(event.value_ms),
                      baseline=format_ms(event.baseline_ms))
        self._tray.showMessage(APP_NAME, text, app_icon(), 5000)

    @Slot(object)
    def _on_room_info(self, info) -> None:
        self._room_info = info
        if info is not None and self._target is not None and self._target.kind == KIND_LIVE:
            self._room_title = f"{tr('label.room')} {info.room_id}"
            self._overlay.set_room_label(self._room_title)

    @Slot(object)
    def _on_target(self, target) -> None:
        self._target = target
        if target is None or target.kind == KIND_NETWORK:
            self._room_title = ""
        elif target.kind == KIND_VIDEO:
            self._room_title = f"{tr('label.video')} {target.title or target.ident}"
        else:
            self._room_title = f"{tr('label.room')} {target.ident}"
        self._overlay.set_room_label(self._room_title)

    def _status_line(self) -> str:
        if self._paused:
            return tr("status.paused")
        mapping = {
            STATUS_OK: "",
            STATUS_OFFLINE: tr("status.offline"),
            STATUS_NO_ROOM: tr("status.network_only"),
            STATUS_ERROR: tr("status.error"),
            STATUS_PAUSED: tr("status.paused"),
        }
        if self._status_key == STATUS_OK:
            # Nothing to say once samples are flowing.
            return "" if len(self._stats) else tr("status.connecting")
        if self._status_key == STATUS_NO_ROOM and self._config.detect.enabled:
            # Auto-detection is on but has not found a page yet.
            return tr("status.detecting")
        text = mapping.get(self._status_key, "")
        if self._status_key == STATUS_ERROR and self._status_detail:
            # Probe errors are codes; show the translated sentence where there
            # is one, and the raw detail (a network message) otherwise.
            known = ERROR_MESSAGES.get(self._status_detail)
            return tr(known) if known else f"{text}: {self._status_detail}"
        return text or tr("status.connecting")

    def _update_status_text(self) -> None:
        self._overlay.set_status(self._status_line())
        if self._tray is not None:
            self._tray.update_sample(self._stats.last(), self._status_line())

    def _poll_clipboard(self, force: bool = False) -> None:
        """Hand a freshly copied Bilibili link to the worker.

        Only the text is passed on, and only when it changed; the worker throws
        away anything that is not a Bilibili link.
        """
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return
        try:
            text = clipboard.text() or ""
        except RuntimeError:  # clipboard busy or owned by another app
            return
        text = text.strip()[:MAX_CLIPBOARD_CHARS]
        if not text or (text == self._last_clipboard and not force):
            return
        self._last_clipboard = text
        self.clipboardText.emit(text)

    def _read_clipboard_now(self) -> None:
        self._poll_clipboard(force=True)
        if self._tray is not None:
            self._tray.showMessage(APP_NAME, tr("notice.clipboard_read"), app_icon(), 2500)

    def _push_display_latency(self) -> None:
        if not self._overlay.isVisible():
            # Without a visible overlay there are no frames to time; the
            # configured panel offset is still meaningful.
            manual = self._config.display.manual_offset_ms
            self._worker.setDisplayLatency(manual if manual > 0 else None)
            return
        self._worker.setDisplayLatency(
            self._display.estimate_ms(
                self._config.display.frames_in_flight,
                self._config.display.manual_offset_ms,
            )
        )

    # ---------------------------------------------------------------- helpers
    def diagnostics_text(self) -> str:
        sample = self._stats.last()
        payload = {
            "app": APP_NAME,
            "version": __version__,
            "language": self._config.language,
            "auto_detect": self._config.detect.enabled,
            "target": {
                "kind": self._target.kind if self._target else None,
                "id": self._target.ident if self._target else None,
                "page": self._target.page if self._target else None,
                "source": self._target.source if self._target else None,
            },
            "room_id": self._config.room_id or None,
            "video_id": self._config.video_id or None,
            "status": self._status_key,
            "status_detail": self._status_detail,
            "samples": len(self._stats),
            "avg_ms": self._stats.avg(),
            "p95_ms": self._stats.percentile(95),
            "jitter_ms": self._stats.jitter(),
            "failure_rate": self._stats.failure_rate(),
            "last_sample": sample.to_dict() if sample else None,
            "display": self._display.snapshot(
                self._config.display.frames_in_flight, self._config.display.manual_offset_ms
            ),
            "events": self._events.summary(),
            "extras": [
                {"label": extra.label, "kind": extra.kind, "ident": extra.ident,
                 "rtt_ms": extra.rtt_ms, "method": extra.method, "ok": extra.ok,
                 "age_s": round(extra.age_s, 1), "error": extra.error}
                for extra in self._ordered_extras()
            ],
            "netspeed": {
                "down_mbps": sample.down_mbps if sample else None,
                "up_mbps": sample.up_mbps if sample else None,
            },
            "cdn_lines": {
                "current": self._lines[0],
                "measured": [
                    {"host": line.host, "rtt_ms": line.rtt_ms} for line in (self._lines[1] or [])
                ],
            },
            "room": None if self._room_info is None else {
                "id": self._room_info.room_id,
                "title": self._room_info.title,
                "online": self._room_info.online,
                "area": self._room_info.area,
                "live_seconds": self._room_info.live_seconds(),
            },
            "config_dir": str(app_config_dir()),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @Slot()
    def _on_second_instance(self) -> None:
        """Someone launched the app again: bring the overlay back instead."""
        self._set_overlay_visible(True)
        self._action_overlay.setChecked(True)
        self._overlay.raise_()

    def _shutdown(self) -> None:
        self._display_timer.stop()
        self._clipboard_timer.stop()
        self._history_timer.stop()
        self._history.close()
        if self._save_timer.isActive():
            self._save_timer.stop()
        self._save_config_now()
        # Queued: the worker stops its own timers inside its own thread, then
        # quit() ends that thread's event loop.
        self.stopRequested.emit()
        self._thread.quit()
        if not self._thread.wait(3000):
            LOG.warning("monitor thread did not stop in time")
            self._thread.terminate()
        if self._recorder is not None:
            self._recorder.close()
        if self._dashboard is not None:
            self._dashboard.stop()
        if self._tray is not None:
            self._tray.hide()
        self._instance.close()


def create_application(argv: list[str]) -> QApplication:
    QApplication.setAttribute(Qt.AA_DontShowIconsInMenus, False)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setWindowIcon(app_icon())
    # Closing the settings dialog must not end the process.
    app.setQuitOnLastWindowClosed(False)
    return app
