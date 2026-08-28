# 延遲是怎麼算出來的 / How the latency is computed

這份文件說明監視器上每一個數字的來源、精度，以及它**不能**代表什麼。
讀完你就知道什麼時候該相信它、什麼時候只能當參考。

---

## 1. 三段延遲

一場直播從主播到你的眼睛，大致會經過：

```
主播端採集 → 主播上行 → B站轉碼/分發 → CDN 邊緣 → 你的網路 → 播放器緩衝 → 解碼 → 合成/送顯 → 螢幕發光
└──────── 監視器看不到 ────────┘└──────── 監視器可以量測 ────────┘└─── 估算 ───┘
```

監視器把可觀測的部分拆成三段：

| 欄位 | 含義 | 取得方式 |
| --- | --- | --- |
| **網路 (network)** | 到實際供流 CDN 邊緣節點的往返時間 | TCP 三向交握計時（`SYN → SYN/ACK`）|
| **推流 (stream)** | 從「伺服器上已經產生這一刻的畫面」到「你的機器拿得到它」 | HLS 播放清單的伺服器時間戳，或 FLV 首個關鍵影格到達時間 |
| **顯示 (display)** | 從「客戶端拿到影格」到「螢幕真的亮起來」 | 由實測影格週期與合成器排隊層數推估，可加上使用者填的面板延遲 |

**總延遲 = 推流 + 顯示**（沒有監測對象時為 `網路 + 顯示`）。

看**一般影片（VOD）**時沒有「直播邊緣」這回事，中間那一段會換成**起播延遲**，
詳見 [第 3 節](#3-一般影片vod起播延遲與頻寬餘量)。

網路那一欄是**參考值，不會再加一次**：推流欄本身就是在你的機器上計時的，
網路傳輸時間已經包含在裡面，重複相加會高估。

---

## 2. 直播推流延遲：三種量法

### 2.1 HLS + `EXT-X-PROGRAM-DATE-TIME`（實測，method = `hls-pdt`）

B站的 fmp4/HLS 播放清單通常帶有 `#EXT-X-PROGRAM-DATE-TIME`，也就是伺服器對每個分片標註的
**牆上時鐘**。監視器抓下清單後：

```
直播邊緣時刻 = 最後一個帶時間戳的分片起點 + 其後所有分片長度
邊緣落後量 edge_lag = 伺服器現在時刻 − 直播邊緣時刻
推流延遲 = edge_lag + 播放器緩衝 + TTFB
```

* `伺服器現在時刻` = 本機時鐘 + 時鐘偏移量。偏移量每 60 秒用一次 HTTP `Date`
  標頭重新估算：`offset = server_time − local_recv_time + RTT/2`。
  HTTP `Date` 只有「秒」的精度，所以這一項帶有約 ±0.5 秒的量化誤差。
* `播放器緩衝` = 平均分片長度 × 設定裡的「播放器緩衝分片數」（預設 1）。
  真正的網頁播放器會依網路狀況調整，這裡取一個保守的常數。
* 若算出來的 `edge_lag` 超過 10 分鐘，代表本機時鐘離譜（或清單異常），
  監視器會丟棄這個結果，自動退回 2.2 的估算法。

這是唯一一種**用伺服器時間直接量到**的模式，UI 上標示為「實測」。

### 2.2 HLS 播放清單視窗（估算，method = `hls-window`）

清單沒有日期標籤時（例如某些 ts 切片），只能用結構推算：

```
推流延遲 ≈ 平均分片長度 × (1 + 播放器緩衝分片數) + TTFB
```

播放器至少要等一個分片下載完才能開播，再加上它自己要墊的緩衝。
UI 標示為「估算」。

### 2.3 HTTP-FLV 首個關鍵影格（估算，method = `flv-keyframe`）

走 FLV 時，監視器直接連上串流，邊收邊解析 FLV tag 標頭，
計時到**第一個關鍵影格**（`FrameType == 1`）為止：

```
推流延遲 ≈ 從發出請求到收到第一個關鍵影格的時間
```

它反映的是「伺服器 GOP 快取 + 網路傳輸」讓一個新觀眾等多久才有畫面，
和實際播放中的穩態延遲高度相關，但不是同一個量。UI 標示為「估算」。
量測完就立刻關閉連線，不會持續佔用頻寬。

> 想要最準的數字，就讓「優先使用 HLS」保持開啟（預設）。

---

## 3. 一般影片（VOD）：起播延遲與頻寬餘量

錄播沒有「直播邊緣」，所以「延遲」要換一個有意義的定義。看影片時真正會影響體驗的是
**要等多久才有畫面**，以及**線路撐不撐得住碼率**（會不會轉圈），監視器就量這兩件事：

1. 用 `x/web-interface/view` 取得該影片（含分 P）的 `cid`；
2. 用 `x/player/playurl` 取得播放地址，挑 API 給出的最高畫質（未登入時通常是 360P/480P，
   量的是同一條 CDN 線路）；
3. 對該 CDN 發一個 **Range 請求**（預設前 512 KB），量到：
   - `TTFB`：從送出請求到收到第一個位元組（**實測**）
   - `throughput`：這段資料的實際下載速度（**實測**）

然後推出：

```
一秒影像資料所需時間 = 該畫質碼率 (Mbps) ÷ 實測下載速度 (Mbps) × 1000 ms
起播延遲 ≈ TTFB + 一秒影像資料所需時間
頻寬餘量 = 實測下載速度 ÷ 該畫質碼率
```

* **總延遲 = 起播延遲 + 顯示延遲**，UI 上第二列會顯示成「起播」而不是「推流」。
* 統計列會多出**帶寬**（實測下載速度）。餘量小於 1× 代表這條線路餵不飽這個畫質，
  播放時會卡；2× 以上就相當寬裕。
* 這一段永遠標示為「估算」：TTFB 和速度是實測，但「一秒資料」是用碼率換算出來的，
  而且真實播放器的緩衝策略比這複雜。
* API 沒給碼率（少數 `durl` 格式）時，退回用探測本身花的時間當作起播時間，
  並在診斷資料裡標記 `bitrate_unknown`。
* 每輪只下載 512 KB 就中斷連線；預設 2 秒一輪的話大約 2 Mbps，比實際播放輕得多。
  嫌多可以把探測間隔調長。

## 4. 顯示延遲：為什麼只能估算

任何一般應用程式都拿不到「像素真正發光」的時刻——那需要顯示器端的硬體量測
（高速攝影機或光感測器）。監視器只量它能量的：

* **影格週期**：懸浮窗每畫一格就記一次時間，取中位數。窗被遮住或隱藏時會停止繪製，
  所以超過 200 ms 的間隔會被丟掉，不讓它污染中位數。為了不整天以 60 fps 重繪，
  監視器平常只在資料更新時重畫，每 30 秒才做一次約 24 格的密集取樣。
* **事件迴圈延遲**：排一個 0 毫秒的計時器，量它實際晚了多久，反映系統忙碌程度。

估算式：

```
顯示延遲 ≈ 影格週期 × 合成器排隊影格數 + 事件迴圈延遲 + 面板延遲補償
```

* `合成器排隊影格數` 預設 2（雙緩衝的常見情形），設定裡可改。
* `面板延遲補償` 預設 0。想要更貼近真實，可以查你的螢幕型號評測（例如 RTINGS
  的 input lag 數據）填進去。
* 如果你不想讓這個估算值進到總延遲，關掉「總延遲包含顯示延遲」即可，
  它仍會顯示在分項裡。

在 60 Hz 螢幕上這一項通常是 30–50 ms，相對於直播本身動輒 2–5 秒的延遲，
影響很小；填不填都不會改變你對「卡不卡」的判斷。

---

## 5. 自動偵測：監視器怎麼知道你在看什麼

不用瀏覽器外掛也能跟著你切換頁面，靠的是幾個各自獨立、都可以關掉的來源。
排序原則是：**「現在畫面上開著什麼」的證據 ＞ 「最近發生過什麼」的證據**。

| 順位 | 來源 | 怎麼運作 | 適用 |
| --- | --- | --- | --- |
| 1 | **油猴腳本 (bridge)** | 頁面本身把網址 POST 到 `http://127.0.0.1:23124/report` | 瀏覽器 |
| 2 | **歷史紀錄 + 視窗標題** | 取最近造訪的 B站網址，再用開著的視窗標題比對出「現在這個分頁」 | 瀏覽器（Windows）|
| 3 | **視窗標題記憶 (title)** | 用學過的「標題 ↔ 房間」對應表，認出現在開著的視窗 | 客戶端／瀏覽器（Windows）|
| 4 | **客戶端紀錄 (client)、複製連結 (clipboard)、瀏覽器歷史紀錄**，取時間最新的那個 | 見下 | 客戶端／任何 App／瀏覽器 |

### 官方客戶端：直接讀它自己的紀錄

客戶端沒有網址列可讀、也不寫瀏覽器的歷史紀錄，但它是 **Chromium 核心的桌面程式**，
會在自己的使用者資料夾裡留下一份 **Chromium 格式的 `History` 資料庫**——
和瀏覽器完全同一套 schema，所以同一段唯讀複製的程式碼就能讀。

* 資料夾用「找」的，不寫死：`%APPDATA%` 與 `%LOCALAPPDATA%` 底下的
  `bilibili` / `BiliBili` / `哔哩哔哩` / `bilibili-desktop` 等名稱，
  加上 Store 版的 `Packages\*Bilibili*`；使用者也能在設定裡補上自訂路徑。
* 掃描時會跳過 `Cache`、`GPUCache`、`Service Worker` 這類只有幾千個檔案的目錄，
  並限制遞迴深度，避免翻整顆硬碟。
* 找不到 `History` 時，退而掃客戶端自己的 `.log` 檔（只讀最後 256 KB），
  用正則抓 `roomid` / `room_id` / `live.bilibili.com/<id>` / `BV` 號，
  **只取出 id，不保留任何其他內容**；檔案修改時間就是這筆證據的時間。
* 讀到的第一筆（最新）同時會拿去和**當下前景視窗標題**配對存進 `titles.json`，
  所以之後光靠標題就能認出同一個房間。
* 客戶端版本千百種，這條路不保證每個版本都通——
  `--detect-report` 會把找到的資料夾、資料庫、讀到的房間號全部印出來，一眼就知道通不通。

### 備援：複製連結

客戶端資料讀不到時（或使用者關掉了這個來源），還有一條不依賴任何內部格式的路：
使用者按 **分享 → 複製連結**，監視器認剪貼簿。

* 剪貼簿每 1.5 秒讀一次（在 GUI 執行緒，因為剪貼簿屬於它），只有內容變動才處理；
  文字裡沒有 B站網址就直接丟掉，不記錄也不上傳。
* `b23.tv` 短連結用一次 HTTP 轉址還原成正式網址（在工作執行緒做，不卡介面）。
* 一樣會學「標題 ↔ 房間」：條件是標題夠特別（不是「哔哩哔哩」這類通用名稱），
  而且看起來就是 B站的視窗，免得把聊天軟體的標題學進去。
* 學不到時，複製過的目標會一直維持到下一次複製為止。

實作細節與界線：

* 歷史紀錄檔會先**複製**成暫存檔再以**唯讀**方式開啟（`file:...?mode=ro`），
  瀏覽器開著也能讀，且絕不會寫回原檔；連 `-wal` 旁檔一起複製，才看得到剛剛的造訪。
* SQL 只撈 `url LIKE '%bilibili.com%'` 的列，其他網站的紀錄不會被讀出來。
* 只有能解析成「直播間」或「影片」的網址才算數；首頁、空間、番劇播放頁都會被忽略，
  這時監視器維持上一個目標或退回你手動設定的對象。
* 歷史掃描預設每 5 秒一次（可調），中間直接沿用上次結果，不會反覆讀檔。
* bridge 伺服器只綁 `127.0.0.1`，只接受 `*.bilibili.com` 來源，
  上報超過 120 秒沒更新就視為過期。
* 剪貼簿只讀不寫，且只處理含 B站網址的文字；`titles.json` 只存標題與房間號／BV 號。
* 客戶端的資料夾同樣只讀不寫：`History` 先複製再唯讀開啟，log 只讀最後 256 KB 並且只取 id。
* 偵測不到任何東西時，會回到設定裡手動填的直播間／影片；兩個都沒填就是僅網路模式。

## 6. 這個數字和播放器顯示的延遲會一樣嗎？

不一定完全一樣，原因是：

1. 監視器問的是「**現在**開始播會落後多少」，而你的播放器可能已經播了兩小時，
   期間因為卡頓累積了額外緩衝（播放器通常不會主動追回來）。
2. 網頁播放器有自己的緩衝策略、低延遲模式與追幀邏輯。
3. B站對同一個房間可能給不同觀眾不同的 CDN 節點與分片長度。

實務上：**監視器的數字是你目前線路能達到的最好情況**。
如果它顯示 2.5 秒、而你感覺互動延遲有 8 秒，那多半是播放器緩衝積太多——
重新整理頁面通常就會回到監視器顯示的水準。這正是這個工具最好用的地方。

---

## 7. 誤差來源整理

| 來源 | 影響 | 備註 |
| --- | --- | --- |
| HTTP `Date` 只有秒精度 | ±500 ms | 只影響 `hls-pdt` 模式 |
| 播放器緩衝分片數為假設值 | ±1 個分片長度 | 可在設定調整 |
| 分片長度不固定 | 數百毫秒 | 取平均值處理 |
| CDN 節點切換 | 突然跳動 | 播放地址預設每 4 分鐘重取 |
| 顯示延遲為模型估算 | 10–40 ms | 可關閉或手動校正 |
| 本機時鐘誤差 | 已用時鐘偏移補償 | 偏差過大時自動退回估算法 |
| 影片碼率為 API 宣告值 | 影響起播延遲的比例 | 未宣告時標記 `bitrate_unknown` |
| 512 KB 取樣估速 | 短時波動 | 拉長探測間隔可讓數字更穩 |
| 自動偵測認錯頁面 | 量到別的房間 | 用油猴腳本或改成手動指定最保險 |

---

## 8. 任意應用程式：延遲是怎麼量的

不是 B 站的時候，監視器改用一條完全不同、但同樣只用公開資訊的路：

1. 向系統要**連線表**（Windows/Linux 直接可讀自己的行程；macOS 對其他行程可能需要權限），
   找出這個程式目前連著哪些遠端位址。
2. 把相同 `IP:埠` 的連線合併計數，**公網位址優先、連線數多的優先**，
   區網／回環位址排在後面（它們說明不了外網品質）。
3. 對排第一的位址計時一次 **TCP 交握**。連不上就退回**系統 `ping`**（ICMP），
   因為很多遊戲和語音走 UDP，對 UDP 埠做 TCP 交握必然失敗。
   哪些位址只能用 ping 會被記住，不會每輪都白試一次 TCP。
4. `總延遲 = 該位址的往返時間 + 顯示延遲`。

限制講在前面：

* 這是**到伺服器的網路往返**，不是遊戲客戶端顯示的「ping」——後者常常還含伺服器處理時間、
  tick rate 或客戶端自己的補償，兩者相近但不會完全一樣。
* 程式如果同時連很多台（例如瀏覽器），量到的是**連線數最多的那一台**，不代表全部。
* 沒有任何連線時（程式剛開、或走的是本機代理）會直接說「該應用當前沒有網絡連接」。
* 不注入行程、不抓封包、不看任何內容，只讀「誰連到哪個位址」這一層。

**全機網速**則是讀作業系統的網卡累計計數器（psutil），兩次取樣相減除以間隔；
回環與 `docker`/`veth`/`vmnet` 這類虛擬介面會排除，避免重複計算。
第一筆只當基準所以不顯示，網卡重連導致計數器歸零時會自動重新取基準，不會冒出負數。

**卡頓／延遲突增**：探測失敗記一次「卡頓」（連續失敗只記一次，避免刷屏）；
成功樣本超過近期中位數的 2 倍記一次「突增」，而突增本身不會被算進中位數，
免得一次抽風把基準線帶歪。事件保留一小時，可選擇彈出提示（有冷卻時間）。

## 9. 隱私與對伺服器的負擔

* 任意應用模式只讀本機的連線表與網卡計數器，不連任何第三方服務；
  對外只有一次 TCP 交握或一次 `ping`，打的是那個程式本來就在連的伺服器。
* 只呼叫 B站**公開**的網頁 API：直播用 `Room/get_info`、`getRoomPlayInfo`，
  影片用 `web-interface/view`、`player/playurl`，和你用瀏覽器打開頁面時是同一批介面。
* **不需要登入、不讀取也不上傳任何 Cookie 或帳號資訊**，沒有任何遙測。
* 自動偵測完全在本機進行：歷史紀錄唯讀、只篩 bilibili.com 網址、
  bridge 只綁 `127.0.0.1`；偵測結果（房間號／BV 號）只留在記憶體裡。
* 預設每 2 秒一次探測：一個 TCP 交握 + 一份播放清單（數 KB）；
  FLV 模式下讀到第一個關鍵影格就中斷連線，影片模式下讀滿 512 KB 就中斷。
* 探測失敗會指數退避（最多 8 倍間隔），不會在對方出問題時猛打。
* 所有設定與紀錄都只存在你自己的使用者目錄裡。

---

## English summary

The overlay splits the observable delay into three parts:

* **network** – a TCP handshake RTT to the CDN edge that actually serves the room;
* **stream** – how far behind the live edge a player starting now would be, measured
  from the HLS playlist's `EXT-X-PROGRAM-DATE-TIME` server clock (labelled *measured*),
  or estimated from the playlist window / the time until the first FLV key frame
  (labelled *estimated*);
* **display** – an *estimate* of the client-to-photons delay: measured frame period
  times the number of frames the compositor keeps in flight, plus event-loop lag and
  an optional panel-latency offset you can enter yourself.

The total is `stream + display` (or `network + display` with nothing selected).
The network figure is shown for context and deliberately **not** added again: the
stream figure is timed on your machine and already contains the transit time.

For an **ordinary video (VOD)** there is no live edge, so the middle term becomes
**start-up delay**: a real ranged download (512 KB) from the video's CDN gives a
measured TTFB and throughput, and the reported figure is
`TTFB + bitrate ÷ throughput` - the wait before playback could begin. The stats row
then shows the measured download speed; headroom below 1x means the connection
cannot sustain that quality and playback will stall.

**Auto-detection** works out what you are watching from optional local sources,
evidence about what is on screen right now ranking above what happened recently:
the companion userscript posting the page URL to `127.0.0.1`; the browser history
matched against open window titles; a learned "window title → room" table; and,
last, whichever is newer of a Bilibili link copied to the clipboard or the newest
page in the browser history.

The **official desktop client** exposes no URL and writes nothing to the browser's
history, but it is a Chromium-based app that keeps its own `History` database, which
is read with exactly the same read-only copy as the browser sources (falling back to
the ids mentioned in the client's own logs). `--detect-report` prints what was found.
When a client build stores things differently, share → copy link switches the target
and pairs the client's window title with that room, after which the title alone is
enough. History files are copied and opened read-only, only rows whose URL contains
`bilibili.com` are read, and clipboard text without a Bilibili URL is discarded.

Clock skew between your PC and Bilibili is estimated every 60 s from the HTTP `Date`
header (`offset = server_time − local_recv_time + RTT/2`), which carries roughly
±500 ms of quantisation error. An absurd result (over 10 minutes) is discarded and
the estimator falls back to the playlist-window method.

No login, no cookies, no telemetry: only the same public endpoints a browser hits.
