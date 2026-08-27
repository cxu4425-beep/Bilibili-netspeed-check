"""Tiny translation table (zh-CN / zh-TW / English).

Kept dependency free so it can be imported by the probes and by tests without
pulling in Qt.
"""

from __future__ import annotations

import locale
import os
from typing import Iterable

LANGUAGES = ("zh_CN", "zh_TW", "en")
LANGUAGE_NAMES = {"zh_CN": "简体中文", "zh_TW": "繁體中文", "en": "English"}

_current = "zh_CN"

# key: (zh_CN, zh_TW, en)
STRINGS: dict[str, tuple[str, str, str]] = {
    "app.title": ("哔哩哔哩延迟监视器", "嗶哩嗶哩延遲監視器", "Bilibili Latency Monitor"),
    "app.short": ("B站延迟", "B站延遲", "Bili Latency"),

    "menu.show_overlay": ("显示悬浮窗", "顯示懸浮視窗", "Show overlay"),
    "menu.lock": ("锁定位置", "鎖定位置", "Lock position"),
    "menu.click_through": ("鼠标穿透", "滑鼠穿透", "Click-through"),
    "menu.pause": ("暂停监测", "暫停監測", "Pause monitoring"),
    "menu.resume": ("继续监测", "繼續監測", "Resume monitoring"),
    "menu.reset_position": ("重置窗口位置", "重設視窗位置", "Reset overlay position"),
    "menu.settings": ("设置…", "設定…", "Settings…"),
    "menu.copy_diag": ("复制诊断信息", "複製診斷資訊", "Copy diagnostics"),
    "menu.open_config": ("打开配置目录", "開啟設定目錄", "Open config folder"),
    "menu.about": ("关于", "關於", "About"),
    "menu.quit": ("退出", "結束", "Quit"),

    "label.total": ("总延迟", "總延遲", "Total"),
    "label.network": ("网络", "網路", "Network"),
    "label.stream": ("推流", "推流", "Stream"),
    "label.display": ("显示", "顯示", "Display"),
    "label.avg": ("均值", "均值", "avg"),
    "label.p95": ("P95", "P95", "p95"),
    "label.jitter": ("抖动", "抖動", "jitter"),
    "label.range": ("范围", "範圍", "range"),
    "label.room": ("房间", "房間", "Room"),
    "label.measured": ("实测", "實測", "measured"),
    "label.estimated": ("估算", "估算", "estimated"),

    "status.no_room": ("未设置房间号", "未設定房間號", "No room configured"),
    "status.offline": ("主播未开播", "主播未開播", "Stream offline"),
    "status.connecting": ("连接中…", "連線中…", "Connecting…"),
    "status.paused": ("已暂停", "已暫停", "Paused"),
    "status.error": ("探测失败", "偵測失敗", "Probe failed"),
    "status.network_only": ("仅网络模式", "僅網路模式", "Network-only mode"),

    "settings.title": ("设置", "設定", "Settings"),
    "settings.tab.general": ("常规", "一般", "General"),
    "settings.tab.overlay": ("显示", "顯示", "Overlay"),
    "settings.tab.advanced": ("高级", "進階", "Advanced"),
    "settings.tab.about": ("关于", "關於", "About"),

    "general.room": ("直播间号或链接", "直播間號或連結", "Room ID or URL"),
    "general.room_hint": (
        "支持粘贴 https://live.bilibili.com/123456 或直接填 123456；留空则只测网络延迟。",
        "支援貼上 https://live.bilibili.com/123456 或直接填 123456；留空則只測網路延遲。",
        "Paste https://live.bilibili.com/123456 or just 123456. Leave empty for network-only mode.",
    ),
    "general.interval": ("探测间隔 (毫秒)", "偵測間隔 (毫秒)", "Probe interval (ms)"),
    "general.sample_window": ("统计窗口 (样本数)", "統計視窗 (樣本數)", "Stats window (samples)"),
    "general.language": ("界面语言", "介面語言", "Language"),
    "general.language_auto": ("跟随系统", "跟隨系統", "System default"),
    "general.autostart": ("开机自动启动", "開機自動啟動", "Start with the system"),
    "general.autostart_unsupported": (
        "当前系统不支持自动设置开机启动，请参考 README。",
        "目前系統不支援自動設定開機啟動，請參考 README。",
        "Automatic autostart is unsupported here; see the README.",
    ),

    "overlay.enabled": ("显示悬浮窗", "顯示懸浮視窗", "Show overlay window"),
    "overlay.anchor": ("位置模式", "位置模式", "Position mode"),
    "overlay.anchor.free": ("自由拖动", "自由拖曳", "Free (drag me)"),
    "overlay.anchor.screen": ("吸附屏幕角落", "吸附螢幕角落", "Pin to screen corner"),
    "overlay.anchor.window": ("跟随B站窗口", "跟隨B站視窗", "Follow the Bilibili window"),
    "overlay.corner": ("角落", "角落", "Corner"),
    "overlay.corner.top-left": ("左上", "左上", "Top left"),
    "overlay.corner.top-right": ("右上", "右上", "Top right"),
    "overlay.corner.bottom-left": ("左下", "左下", "Bottom left"),
    "overlay.corner.bottom-right": ("右下", "右下", "Bottom right"),
    "overlay.screen": ("屏幕", "螢幕", "Screen"),
    "overlay.screen_primary": ("主屏幕", "主螢幕", "Primary screen"),
    "overlay.offset_x": ("水平偏移", "水平偏移", "Offset X"),
    "overlay.offset_y": ("垂直偏移", "垂直偏移", "Offset Y"),
    "overlay.opacity": ("不透明度", "不透明度", "Opacity"),
    "overlay.scale": ("缩放", "縮放", "Scale"),
    "overlay.on_top": ("总在最前", "總在最前", "Always on top"),
    "overlay.click_through": ("鼠标穿透 (不挡操作)", "滑鼠穿透 (不擋操作)", "Click-through"),
    "overlay.lock": ("锁定位置", "鎖定位置", "Lock position"),
    "overlay.theme": ("主题", "主題", "Theme"),
    "overlay.theme.dark": ("深色", "深色", "Dark"),
    "overlay.theme.light": ("浅色", "淺色", "Light"),
    "overlay.theme.pink": ("粉色", "粉色", "Pink"),
    "overlay.compact": ("紧凑模式 (只显示总延迟)", "緊湊模式 (只顯示總延遲)", "Compact (total only)"),
    "overlay.show_breakdown": ("显示分项延迟", "顯示分項延遲", "Show breakdown"),
    "overlay.show_sparkline": ("显示折线图", "顯示折線圖", "Show sparkline"),
    "overlay.show_stats": ("显示统计行", "顯示統計行", "Show statistics row"),
    "overlay.follow_keyword": ("窗口标题关键字", "視窗標題關鍵字", "Window title keyword"),
    "overlay.window_unsupported": (
        "跟随窗口目前仅支持 Windows，其它系统会退回到屏幕角落模式。",
        "跟隨視窗目前僅支援 Windows，其它系統會退回螢幕角落模式。",
        "Window following works on Windows only; other systems fall back to a screen corner.",
    ),
    "tray.enabled": ("显示状态栏 (托盘) 图标", "顯示狀態列 (系統匣) 圖示", "Show status bar / tray icon"),
    "tray.show_value": ("在图标上显示数值", "在圖示上顯示數值", "Draw the value on the icon"),

    "advanced.timeout": ("请求超时 (毫秒)", "請求逾時 (毫秒)", "Request timeout (ms)"),
    "advanced.playurl_refresh": ("播放地址刷新 (秒)", "播放位址更新 (秒)", "Play URL refresh (s)"),
    "advanced.rtt_host": ("RTT 探测主机", "RTT 偵測主機", "RTT probe host"),
    "advanced.prefer_hls": ("优先使用 HLS (更精确)", "優先使用 HLS (更精確)", "Prefer HLS (more accurate)"),
    "advanced.buffer_segments": ("播放器缓冲分片数", "播放器緩衝分片數", "Player buffer segments"),
    "advanced.frames_in_flight": ("合成器排队帧数", "合成器排隊影格數", "Frames in flight"),
    "advanced.manual_offset": ("显示器输入延迟补偿 (毫秒)", "顯示器輸入延遲補償 (毫秒)", "Panel input lag offset (ms)"),
    "advanced.include_display": ("总延迟包含显示延迟", "總延遲包含顯示延遲", "Include display latency in total"),
    "advanced.csv": ("记录到 CSV 文件", "記錄到 CSV 檔案", "Log samples to CSV"),
    "advanced.csv_hint": (
        "文件位于配置目录的 logs 子目录，自动轮转。",
        "檔案位於設定目錄的 logs 子目錄，會自動輪替。",
        "Written to the logs folder next to the config, with rotation.",
    ),
    "advanced.good": ("绿色阈值 (毫秒)", "綠色門檻 (毫秒)", "Good threshold (ms)"),
    "advanced.warn": ("黄色阈值 (毫秒)", "黃色門檻 (毫秒)", "Warning threshold (ms)"),

    "about.body": (
        "开源、免费、无需登录。测量哔哩哔哩直播从服务器到客户端再到画面的延迟。",
        "開源、免費、無需登入。測量嗶哩嗶哩直播從伺服器到用戶端再到畫面的延遲。",
        "Free and open source, no login required. Measures Bilibili live delay from server to client to screen.",
    ),
    "about.repo": ("项目主页", "專案首頁", "Project page"),
    "about.version": ("版本", "版本", "Version"),

    "button.ok": ("确定", "確定", "OK"),
    "button.cancel": ("取消", "取消", "Cancel"),
    "button.apply": ("应用", "套用", "Apply"),
    "button.defaults": ("恢复默认", "恢復預設", "Restore defaults"),

    "notice.tray_missing": (
        "系统托盘不可用，已改为只显示悬浮窗。",
        "系統匣不可用，已改為只顯示懸浮視窗。",
        "No system tray available; showing the overlay only.",
    ),
    "notice.copied": ("诊断信息已复制到剪贴板。", "診斷資訊已複製到剪貼簿。", "Diagnostics copied to the clipboard."),
    "tray.tooltip": (
        "{title}\n总延迟 {total}\n网络 {network} / 推流 {stream} / 显示 {display}\n{status}",
        "{title}\n總延遲 {total}\n網路 {network} / 推流 {stream} / 顯示 {display}\n{status}",
        "{title}\nTotal {total}\nNetwork {network} / Stream {stream} / Display {display}\n{status}",
    ),
    "notice.hidden_hint": (
        "悬浮窗已隐藏，可从托盘图标重新打开。",
        "懸浮視窗已隱藏，可從系統匣圖示重新開啟。",
        "Overlay hidden. Reopen it from the tray icon.",
    ),
}


def normalize(code: str) -> str:
    code = (code or "").replace("-", "_")
    if code in LANGUAGES:
        return code
    lowered = code.lower()
    if lowered.startswith("zh"):
        if any(tag in lowered for tag in ("tw", "hk", "mo", "hant")):
            return "zh_TW"
        return "zh_CN"
    if lowered.startswith("en"):
        return "en"
    return ""


def detect_system_language(candidates: Iterable[str] | None = None) -> str:
    if candidates is None:
        env = [os.environ.get(name, "") for name in ("BILI_LATENCY_LANG", "LC_ALL", "LC_MESSAGES", "LANG")]
        try:
            env.append(locale.getdefaultlocale()[0] or "")
        except (ValueError, TypeError):  # pragma: no cover - platform dependent
            pass
        candidates = env
    for candidate in candidates:
        resolved = normalize(candidate)
        if resolved:
            return resolved
    return "zh_CN"


def set_language(code: str) -> str:
    """Set the active language; ``auto`` resolves against the environment."""
    global _current
    if not code or code == "auto":
        _current = detect_system_language()
    else:
        _current = normalize(code) or "zh_CN"
    return _current


def current_language() -> str:
    return _current


def tr(key: str, **kwargs) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry[LANGUAGES.index(_current)]
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text
