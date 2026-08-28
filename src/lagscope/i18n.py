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
    "app.title": ("哔哩哔哩延迟监视器", "嗶哩嗶哩延遲監視器", "LagScope"),
    "app.short": ("B站延迟", "B站延遲", "Bili Latency"),
    "app.short_generic": ("网络延迟", "網路延遲", "Latency"),

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
    "label.video": ("视频", "影片", "Video"),
    "label.startup": ("起播", "起播", "Startup"),
    "label.speed": ("带宽", "頻寬", "Speed"),
    "label.latency": ("延迟", "延遲", "Latency"),
    "label.connections": ("连接数", "連線數", "Sockets"),
    "label.app": ("应用", "應用", "App"),
    "label.target": ("目标", "目標", "Target"),
    "label.down": ("下载", "下載", "Down"),
    "label.up": ("上传", "上傳", "Up"),
    "label.measured": ("实测", "實測", "measured"),
    "label.estimated": ("估算", "估算", "estimated"),
    "label.auto": ("自动", "自動", "auto"),

    "status.no_room": ("未设置房间号", "未設定房間號", "No room configured"),
    "status.offline": ("主播未开播", "主播未開播", "Stream offline"),
    "status.connecting": ("连接中…", "連線中…", "Connecting…"),
    "status.paused": ("已暂停", "已暫停", "Paused"),
    "status.error": ("探测失败", "偵測失敗", "Probe failed"),
    "status.network_only": ("仅网络模式", "僅網路模式", "Network-only mode"),

    "status.no_video": ("未设置视频", "未設定影片", "No video configured"),
    "status.no_app": ("未选择应用", "未選擇應用", "No app selected"),
    "status.no_connections": (
        "该应用当前没有网络连接", "該應用目前沒有網路連線", "That app has no connections right now",
    ),
    "status.unreachable": ("目标无法连通", "目標無法連通", "Target unreachable"),
    "status.no_reply": (
        "该应用的服务器不回应探测（可能屏蔽了 ping）",
        "該應用的伺服器不回應偵測（可能封鎖了 ping）",
        "That app's servers do not answer probes (ping may be blocked)",
    ),
    "status.detecting": ("正在识别观看页面…", "正在辨識觀看頁面…", "Looking for what you are watching…"),

    "menu.diagnose": ("网络体检…", "網路體檢…", "Diagnose my network…"),
    "diag.title": ("网络体检", "網路體檢", "Network check"),
    "diag.running": ("正在检测各段延迟…（约 10 秒）", "正在檢測各段延遲…（約 10 秒）",
                     "Measuring each segment… (about 10 seconds)"),
    "diag.you_router": ("你 → 路由器", "你 → 路由器", "You → router"),
    "diag.router_isp": ("路由器 → 电信商", "路由器 → 電信商", "Router → ISP"),
    "diag.to_target": ("→ 目标服务器", "→ 目標伺服器", "→ target server"),
    "diag.wifi": ("Wi-Fi", "Wi-Fi", "Wi-Fi"),
    "diag.loss": ("丢包", "丟包", "loss"),
    "diag.no_gateway": ("找不到默认网关", "找不到預設閘道", "No default gateway found"),
    "diag.gateway_silent": (
        "路由器不回应 ping（很多路由器默认如此，不代表有问题）",
        "路由器不回應 ping（很多路由器預設如此，不代表有問題）",
        "The router ignores ping - common, and not a fault by itself",
    ),

    "verdict.ok": (
        "网络看起来正常", "網路看起來正常", "Your network looks fine",
    ),
    "verdict.wifi": (
        "延迟主要卡在你和路由器之间，而且 Wi-Fi 信号偏弱——靠近路由器或改用网线会明显改善。",
        "延遲主要卡在你和路由器之間，而且 Wi-Fi 訊號偏弱——靠近路由器或改用網線會明顯改善。",
        "Most of the delay is between you and the router, and the Wi-Fi signal is weak - "
        "move closer to it or use a cable.",
    ),
    "verdict.home": (
        "延迟主要卡在你家网络（你↔路由器）。检查 Wi-Fi、路由器是否过载，或换成网线。",
        "延遲主要卡在你家網路（你↔路由器）。檢查 Wi-Fi、路由器是否過載，或換成網線。",
        "Most of the delay is inside your own network (you to the router). Check the Wi-Fi or "
        "the router's load, or use a cable.",
    ),
    "verdict.isp": (
        "你家网络正常，延迟是从电信商那一段开始变大的——这一段你改不了，可以拿这份报告去问客服。",
        "你家網路正常，延遲是從電信商那一段開始變大的——這一段你改不了，可以拿這份報告去問客服。",
        "Your own network is fine; the delay appears once traffic reaches your provider. "
        "That part is not yours to fix - this report is what to show them.",
    ),
    "verdict.server": (
        "你的线路正常，延迟主要来自服务器距离或路由——换个服务器／节点通常最有效。",
        "你的線路正常，延遲主要來自伺服器距離或路由——換個伺服器／節點通常最有效。",
        "Your line is fine; the delay comes from how far away the server is. Picking a closer "
        "server or node is usually what helps.",
    ),
    "verdict.loss": (
        "有封包丢失——这比延迟更影响游戏和通话，优先处理。",
        "有封包遺失——這比延遲更影響遊戲和通話，優先處理。",
        "Packets are being lost - that hurts games and calls more than latency does.",
    ),
    "verdict.target_down": (
        "目标没有回应（可能挡了 ping 或已离线），但你的网络本身正常。",
        "目標沒有回應（可能擋了 ping 或已離線），但你的網路本身正常。",
        "The target did not answer (it may block ping, or be down) - your own network is fine.",
    ),
    "verdict.no_ping": (
        "这台电脑上找不到可用的 ping 命令，无法做分段诊断（其它功能不受影响）。",
        "這台電腦上找不到可用的 ping 指令，無法做分段診斷（其它功能不受影響）。",
        "No usable ping command on this machine, so the path cannot be split up "
        "(everything else still works).",
    ),
    "verdict.unknown": ("资料不足，无法判断", "資料不足，無法判斷", "Not enough data to tell"),

    "settings.title": ("设置", "設定", "Settings"),
    "settings.tab.general": ("常规", "一般", "General"),
    "settings.tab.overlay": ("显示", "顯示", "Overlay"),
    "settings.tab.advanced": ("高级", "進階", "Advanced"),
    "settings.tab.about": ("关于", "關於", "About"),

    "general.target": ("监测对象", "監測對象", "What to monitor"),
    "general.target.auto": (
        "自动跟随我正在看的页面", "自動跟隨我正在看的頁面", "Follow whatever I am watching",
    ),
    "general.target.live": ("手动指定直播间", "手動指定直播間", "A live room I pick"),
    "general.target.video": ("手动指定视频", "手動指定影片", "A video I pick"),
    "general.target.app": ("任意应用程序（游戏／通话／浏览器…）", "任意應用程式（遊戲／通話／瀏覽器…）",
                           "Any application (games, calls, browsers…)"),
    "general.target.custom": ("自定义服务器地址", "自訂伺服器位址", "A server address I type"),
    "general.app_name": ("应用程序", "應用程式", "Application"),
    "general.app_follow": (
        "自动跟随当前使用的程序", "自動跟隨目前使用的程式", "Follow whichever app is in front",
    ),
    "general.app_hint": (
        "选一个正在联网的程序，监视器会找出它连的服务器并持续测延迟；"
        "UDP 的游戏会自动改用 ping。",
        "選一個正在連網的程式，監視器會找出它連的伺服器並持續測延遲；"
        "UDP 的遊戲會自動改用 ping。",
        "Pick a program that is on the network: the monitor finds the servers it talks to and "
        "keeps timing them, falling back to ping for UDP games.",
    ),
    "general.app_refresh": ("刷新列表", "重新整理", "Refresh"),
    "general.target_host": ("服务器地址", "伺服器位址", "Server address"),
    "general.target_port": ("端口", "連接埠", "Port"),
    "general.target_hint": (
        "例如游戏服务器、公司 VPN、8.8.8.8。先试 TCP，连不上就用 ping。",
        "例如遊戲伺服器、公司 VPN、8.8.8.8。先試 TCP，連不上就用 ping。",
        "A game server, a VPN gateway, 8.8.8.8 - TCP first, ping if that is refused.",
    ),
    "general.netspeed": (
        "显示全机上传／下载速度", "顯示全機上傳／下載速度", "Show machine upload / download speed",
    ),
    "general.video": ("视频号或链接", "影片編號或連結", "Video ID or URL"),
    "general.video_hint": (
        "支持 BV 号、av 号，或直接粘贴 https://www.bilibili.com/video/BV… （分P 用 ?p=2）。",
        "支援 BV 號、av 號，或直接貼上 https://www.bilibili.com/video/BV…（分P 用 ?p=2）。",
        "A BV id, an av number, or a https://www.bilibili.com/video/BV… URL (?p=2 for a part).",
    ),
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

    "detect.group": ("自动检测", "自動偵測", "Auto-detection"),
    "detect.history": (
        "读取浏览器历史记录（只读）",
        "讀取瀏覽器歷史紀錄（唯讀）",
        "Read the browser history (read-only)",
    ),
    "detect.titles": (
        "用窗口标题识别当前标签页",
        "用視窗標題辨識目前分頁",
        "Match open window titles (Windows)",
    ),
    "detect.bridge": (
        "接收油猴脚本上报（最准）",
        "接收油猴腳本回報（最準）",
        "Accept userscript reports (most accurate)",
    ),
    "detect.client": (
        "读取官方PC客户端正在播放的内容",
        "讀取官方PC用戶端正在播放的內容",
        "Read what the official desktop client is playing",
    ),
    "detect.clipboard": (
        "识别复制的链接（客户端用）",
        "辨識複製的連結（用戶端適用）",
        "Watch for copied links (desktop client)",
    ),
    "detect.remember_titles": (
        "记住窗口标题对应的房间",
        "記住視窗標題對應的房間",
        "Remember which window title is which room",
    ),
    "detect.client_hint": (
        "用官方 PC 客户端时，监视器会直接读客户端自己的记录，不用你动手。"
        "万一读不到（客户端版本不同），在客户端点「分享 → 复制链接」也能立刻切过去。"
        "用命令行加 --detect-report 可以看到到底读到了什么。",
        "用官方 PC 用戶端時，監視器會直接讀用戶端自己的紀錄，不用你動手。"
        "萬一讀不到（用戶端版本不同），在用戶端點「分享 → 複製連結」也能立刻切過去。"
        "用命令列加 --detect-report 可以看到到底讀到了什麼。",
        "With the official desktop client the monitor reads the client's own records, so "
        "there is nothing to do. If a client build stores things differently, share -> copy "
        "link still switches over instantly. Run with --detect-report to see what was found.",
    ),
    "detect.bridge_port": ("脚本上报端口", "腳本回報連接埠", "Bridge port"),
    "detect.window": ("历史记录时间窗口（分钟）", "歷史紀錄時間視窗（分鐘）", "History window (minutes)"),
    "detect.follow_videos": ("也跟随普通视频", "也跟隨一般影片", "Follow ordinary videos too"),
    "detect.interval": ("检测间隔（秒）", "偵測間隔（秒）", "Detection interval (s)"),
    "detect.privacy": (
        "检测只在你的电脑上进行：历史记录会被复制成临时文件后只读打开，只筛选 bilibili.com 的网址，"
        "不会写回、不会上传，也不需要登录。不想用可以关掉这一项。",
        "偵測只在你的電腦上進行：歷史紀錄會被複製成暫存檔後唯讀開啟，只篩選 bilibili.com 的網址，"
        "不會寫回、不會上傳，也不需要登入。不想用可以關掉這一項。",
        "Detection stays on your machine: the history file is copied, opened read-only and filtered "
        "to bilibili.com URLs. Nothing is written back or uploaded, and no login is used. "
        "Turn it off if you would rather not.",
    ),
    "detect.source.manual": ("手动", "手動", "manual"),
    "detect.source.clipboard": ("复制的链接", "複製的連結", "copied link"),
    "detect.source.title": ("窗口标题", "視窗標題", "window title"),
    "menu.phone": ("手机网址…", "手機網址…", "Phone dashboard…"),
    "web.group": ("手机仪表板", "手機儀表板", "Phone dashboard"),
    "web.enabled": (
        "让同一网络下的手机也能看", "讓同一網路下的手機也能看", "Let a phone on this network watch",
    ),
    "web.port": ("端口", "連接埠", "Port"),
    "web.code": ("访问码（留空＝不需要）", "存取碼（留空＝不需要）", "Access code (empty = none)"),
    "web.hint": (
        "打开后，手机浏览器输入下面的网址就能看到同一份实时数字，不用装 App，iPhone 安卓都可以。"
        "只读：手机上改不了任何设置。网址只在你的局域网内有效。",
        "開啟後，手機瀏覽器輸入下面的網址就能看到同一份即時數字，不用裝 App，iPhone 安卓都可以。"
        "唯讀：手機上改不了任何設定。網址只在你的區域網路內有效。",
        "Open the address below in a phone browser to watch the same live numbers - no app to "
        "install, iPhone and Android alike. Read-only: nothing can be changed from the phone, "
        "and the address only works on your own network.",
    ),
    "web.url_label": ("手机上打开：", "手機上開啟：", "Open on your phone:"),
    "web.off": ("未开启（在设置里打开）", "未開啟（在設定裡開啟）", "Not enabled (turn it on in Settings)"),
    "web.copied": ("网址已复制到剪贴板", "網址已複製到剪貼簿", "Address copied to the clipboard"),
    "menu.read_clipboard": ("读取剪贴板里的链接", "讀取剪貼簿裡的連結", "Read link from clipboard"),
    "notice.clipboard_read": (
        "已读取剪贴板。若里面是B站链接，马上就会切过去。",
        "已讀取剪貼簿。若裡面是B站連結，馬上就會切過去。",
        "Clipboard read. If it held a Bilibili link, the monitor is switching now.",
    ),
    "detect.source.history": ("历史记录", "歷史紀錄", "history"),
    "detect.source.history+title": ("当前标签页", "目前分頁", "current tab"),
    "detect.source.bridge": ("脚本", "腳本", "userscript"),
    "menu.auto_detect": ("自动跟随观看页面", "自動跟隨觀看頁面", "Follow what I watch"),

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
    "tray.tooltip_video": (
        "{title}\n视频总延迟 {total}\n网络 {network} / 起播 {stream} / 显示 {display}\n带宽 {speed}\n{status}",
        "{title}\n影片總延遲 {total}\n網路 {network} / 起播 {stream} / 顯示 {display}\n頻寬 {speed}\n{status}",
        "{title}\nVideo total {total}\nNetwork {network} / Startup {stream} / Display {display}\n"
        "Speed {speed}\n{status}",
    ),
    "tray.tooltip_app": (
        "{title}\n延迟 {total}\n服务器 {host}\n连接 {conns}   ↓{down} ↑{up}\n{status}",
        "{title}\n延遲 {total}\n伺服器 {host}\n連線 {conns}   ↓{down} ↑{up}\n{status}",
        "{title}\nLatency {total}\nServer {host}\nSockets {conns}   ↓{down} ↑{up}\n{status}",
    ),
    "notice.stall": (
        "监测中断：连不上服务器，正在重试…",
        "監測中斷：連不上伺服器，正在重試…",
        "Lost the server — retrying…",
    ),
    "notice.spike": (
        "延迟突增：{value}（平常约 {baseline}）",
        "延遲突增：{value}（平常約 {baseline}）",
        "Latency spike: {value} (normally around {baseline})",
    ),
    "general.notify": (
        "卡顿／延迟突增时弹出提示", "卡頓／延遲突增時彈出提示", "Notify me about stalls and spikes",
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
