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

`build.sh` 第一次跑會產生 `build/debug.keystore` 並自我簽章（sideload 用）。

**這個檔案要留著。** Android 不接受換了金鑰的更新——弄丟的話，每個使用者都得先解除安裝才能裝新版。它已經在 `.gitignore` 裡，不要提交到公開 repo：任何人拿到它就能簽一個假的「更新」。

## 沒有 iOS

`.ipa` 需要 macOS + Xcode、Apple 開發者帳號（$99/年）和簽章憑證，而且要給別人裝只有 App Store 審核、TestFlight 或 ad-hoc（綁定特定裝置 UDID）三條路。這些都不是這個 repo 能自己產出的。

iPhone 可以改用 Safari 開同一個網址，再「加入主畫面」——沒有 App Store，但拿到的東西差不多。

## 這個 App 沒有在真的手機上跑過

寫它的機器沒有 Android 裝置也沒有模擬器（模擬器和系統映像檔都在連不到的那個網域上）。

**已經驗證**：編得過、`aapt dump badging` 的 manifest 正確（minSdk 23 / targetSdk 34、只要 INTERNET 權限）、v1+v2+v3 簽章通過、配對網址的邏輯有 10 個單元測試。

**沒有驗證**：畫面在真實螢幕上長什麼樣、WebView 實際載入的行為。第一個裝的人就是第一個測的人。
