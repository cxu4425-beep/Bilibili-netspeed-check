# LagScope 手機版（Android）

一個**看你電腦上 LagScope 的 App**，不是第二台 LagScope。

## 為什麼手機不能自己量

不是沒做，是作業系統不允許：

| 功能 | 手機上為什麼不行 |
| --- | --- |
| 看其他 App 連到哪 | **Android 10（API 29）起**禁止讀別的 app 的 `/proc/net/tcp` |
| 讀瀏覽器歷史抓直播間 | 要當預設瀏覽器才拿得到 |
| ICMP ping | 一般 app 沒有 raw socket |

量測只能由被量的那台機器做。所以手機負責顯示，電腦負責量。

## 沒有帳號，也沒有伺服器

手機**直接連你的電腦**，資料不經過任何第三方——桌面版「資料不會離開你的電腦」那句話因此還算數。

所謂「登入」其實是**配對**：記住電腦的網址和存取碼，問一次就好。

在電腦上點托盤圖示 →「手機網址…」，把顯示的網址整段貼進 App 就好。

> 手機和電腦要在**同一個 Wi-Fi**。用行動網路連不到家裡的電腦——
> 想在外面看，可以裝 Tailscale 之類的私有網路，資料一樣不經過第三方。

## 自動更新

托盤選單 →「檢查更新」，或每天開啟時自動查一次（最多一次，查不到就安靜略過）。

規矩跟桌面版一樣，因為這是這個 App 裡唯一一個「下載檔案然後交給安裝程式」的功能：

| 規矩 | 為什麼 |
| --- | --- |
| 只收 **https**，主機必須在固定的 GitHub 清單裡，**跟完重導向後再檢查一次** | API 回什麼都不能把它帶到別的地方 |
| 位元組必須符合 releases API 公布的 **sha256**，不符就刪掉 | 這是「下載」和「交給安裝程式」之間唯一的關卡 |
| **沒公布校驗碼就不自動裝**，改開下載頁 | 一個沒驗證過的 APK 會被 Android 當成這個 App 的更新，比任何其他檔案都危險 |

安裝用的是自己寫的 `ApkProvider`（40 行的 `ContentProvider`）。Android 7 起不能把 `file://` 交給別的 App，通常會用 AndroidX 的 `FileProvider`——但它在 Google 的 Maven 上，這台機器連不到。這個版本比 `FileProvider` 更窄：**只提供一個檔案**，而且完全忽略 URI 裡的路徑，所以沒有路徑穿越可談。

`REQUEST_INSTALL_PACKAGES` 權限就是為了這個。Android 8 起還要使用者另外允許，App 會帶你去那個設定頁而不是默默失敗。

## 配色跟桌面版一樣

不是照抄的。`sync_theme.py` 讀 `src/lagscope/ui/theme.py` 裡的 `THEMES["dark"]`，產生 `res/values/colors.xml`：

```bash
python3 sync_theme.py     # 改過桌面配色之後跑，然後把結果一起提交
```

手抄兩份的話，第一次改顏色就會走鐘而且沒人記得有兩個地方。

## 自己編譯

```bash
sudo apt install aapt apksigner zipalign android-sdk-platform-23 default-jdk-headless
./build.sh          # 產生 build/LagScope-viewer.apk
```

沒有用 Gradle。Android Gradle Plugin 只在 Google 的 Maven 上，而這個專案是在連不到那裡的機器上寫的——所以 `build.sh` 直接做 AGP 會做的那幾步：`aapt` → `javac` → `dx` → `zipalign` → `apksigner`。除了 `tools/dx.jar`（來自 Maven Central）以外全部是 Debian 套件。

跑邏輯測試：

```bash
javac -d build/test src/tw/lagscope/viewer/Pairing.java test/PairingTest.java
java -cp build/test PairingTest
```

## 關於簽章金鑰

`build.sh` 第一次跑會產生 `keystore/lagscope.jks` 並自我簽章（sideload 用）。

**這個檔案要留著，它就是這個 App 的身分。** Android 不接受換了金鑰的更新——弄丟的話，每個使用者都得先解除安裝才能裝新版。已經在 `.gitignore` 裡，不要提交到公開 repo：任何人拿到它就能簽一個假的「更新」，而使用者的手機會接受。

> 早期版本把它放在 `build/` 裡，而 `build.sh` 每次開頭都 `rm -rf build`——所以**每次建置都在偷偷換一把新金鑰**。做出來的 APK 在乾淨的手機上裝得起來，卻沒辦法更新任何已經裝過的人。這種 bug 只會在別人的手機上現形，在這裡看不到。現在它放在 `keystore/`，不會被清掉。

### 讓每次發布都附上 APK

**最省事的做法:跑一次 `Create the Android signing key` 這個 workflow。**

Actions → 選那個 workflow → Run workflow。它會在 GitHub 的 runner 上產一把金鑰，
以 artifact 交給你下載 —— **金鑰不會經過聊天視窗、不會進 commit、也不會出現在 log 裡**。
下載後照裡面的 `README.txt` 加兩個 secret 就完成了。

> 它會拒絕覆蓋已經在用的金鑰,除非你在輸入欄打 `regenerate`。
> 換金鑰等於讓每一支已經裝了 App 的手機再也無法更新 —— Android 不接受不同金鑰簽的更新。

要自己產也可以:

1. 把 `keystore/lagscope.jks` 轉成 base64：
   `base64 -w0 keystore/lagscope.jks`（macOS 用 `base64 -i`）
2. 在 repo 的 **Settings → Secrets and variables → Actions** 新增：
   - `ANDROID_KEYSTORE_BASE64` — 上一步的內容
   - `ANDROID_KEYSTORE_PASSWORD` — 金鑰密碼

不管用哪一種，設好之後每次發布都會自動附上 `LagScope-viewer.apk`。

**把那把金鑰和密碼另外存一份。** 它就是這個 App 的身分,弄丟了就沒有第二把 ——
所有裝過的人都得先解除安裝才能再更新。artifact 一天後就會被刪掉,你留的那份就是唯一備份。

### APK 的版本會跟著 release 走

發布時 CI 會先把 release 標籤蓋到 `AndroidManifest.xml` 上（`v4.11.3` → `versionName=4.11.3`、
`versionCode=41103`），再編譯。

這不是為了整齊,是**更新功能的前提**:手機是拿 release 標籤比對 APK 自己的 manifest 版本
來判斷有沒有新版。兩邊各自編號的話（release 4.11.x vs manifest 1.3），那個比較**永遠成立** ——
裝了最新版之後它還是會天天說有新版,而且裝再多次也不會變。

**沒有設這兩個 secret 的話，CI 會印一個警告然後跳過 APK，不會讓建置失敗。** 這是刻意的：寧可沒有 APK，也不要發一個用臨時金鑰簽、誰都更新不了的 APK。

## 沒有 iOS

`.ipa` 需要 macOS + Xcode、Apple 開發者帳號（$99/年）和簽章憑證，而且要給別人裝只有 App Store 審核、TestFlight 或 ad-hoc（綁定特定裝置 UDID）三條路。這些都不是這個 repo 能自己產出的。

iPhone 可以改用 Safari 開同一個網址，再「加入主畫面」——沒有 App Store，但拿到的東西差不多。

## 這個 App 沒有在真的手機上跑過

寫它的機器沒有 Android 裝置也沒有模擬器（模擬器和系統映像檔都在連不到的那個網域上）。

**已經驗證**：

- 編得過，而且 `build.sh` 會先跑測試才打包
- `aapt dump badging` 讀回來的 manifest 正確：minSdk 23 / targetSdk 34、只要 INTERNET 和 REQUEST_INSTALL_PACKAGES
- `ApkProvider` 在編譯後的 manifest 裡 `exported=false`
- 四個桌面配色確實出現在編譯後的資源裡（不是我宣稱，是從 APK 裡讀出來的）
- v1+v2+v3 簽章通過
- **40 個單元測試**在一般 JVM 上跑：配對網址 10 個、更新邏輯 30 個（版本比較、JSON 解析、主機白名單、拒絕沒有校驗碼的 APK、擋掉 `https://github.com@evil.example` 這種偽裝）

**沒有驗證**：畫面在真實螢幕上長什麼樣、WebView 實際載入的行為、安裝流程實際跑起來會怎樣。第一個裝的人就是第一個測的人。
