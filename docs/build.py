"""Build docs/index.html from the artifact page: same design, plus the head
a standalone site needs and the artifact host otherwise supplies."""
import pathlib, sys

sp = pathlib.Path(sys.argv[1]); repo = pathlib.Path(sys.argv[2])
body = (sp / "lagscope.html").read_text(encoding="utf-8")
SITE = "https://cxu4425-beep.github.io/LagScope/"
DESC = ("LagScope 是一個桌面延遲監視器：卡的時候，它告訴你是誰的錯。"
        "拆開你到伺服器的每一段，指出問題在哪一段，然後告訴你能做什麼。")

shared = body[body.index("<style>"):]
old = '''  <div class="brandline">
    <span class="brand">Lag<span class="brand-mark">Scope</span></span>'''
new = '''  <div class="brandline">
    <img class="logo" src="icon.png" width="34" height="34" alt="">
    <span class="brand">Lag<span class="brand-mark">Scope</span></span>'''
assert old in shared
shared = shared.replace(old, new, 1)

# The clip of the app actually running. Injected here rather than into the
# artifact source: an artifact is one self-contained file served under a CSP
# that blocks external media, so a <video src="..."> would be a broken box
# there. On the site it is a plain relative file and just works.
CLIP = '''
    <figure class="clip">
      <video poster="demo-poster.jpg" width="1240" height="912"
             autoplay muted loop playsinline preload="metadata"
             aria-label="LagScope 的懸浮視窗疊在一場 B 站直播上，延遲數字每兩秒跳動一次，
                         在 39 到 148 毫秒之間變化，下面同時顯示伺服器位址、連線數和顯示延遲。">
        <source src="demo.webm" type="video/webm">
        <source src="demo.mp4" type="video/mp4">
      </video>
      <figcaption>
        <b>真的在跑</b>：懸浮窗疊在一場 B 站直播上，監視官方客戶端本身。
        數字每兩秒更新一次——中間那次跳到 148 ms 不是剪接，就是當下真的卡了一下。
        <span class="clip-note">畫面裡的彈幕和觀眾名稱已經模糊處理，聲音已移除。</span>
      </figcaption>
    </figure>
'''
CLIP_CSS = '''
.clip { margin: 0 0 30px; }
.clip video {
  display: block; width: 100%; height: auto; border-radius: 16px;
  border: 1px solid var(--line); background: #0A1113;
}
.clip figcaption { margin-top: 14px; font-size: 14.5px; color: var(--ink-soft); }
.clip figcaption b { color: var(--ink); font-weight: 600; }
.clip-note { display: block; margin-top: 6px; font-size: 13px; opacity: .78; }
@media (prefers-reduced-motion: reduce) { .clip video { animation: none; } }
'''
anchor = '    <div class="shots">'
assert anchor in shared
shared = shared.replace(anchor, CLIP + anchor, 1)
shared = shared.replace("<style>", "<style>" + CLIP_CSS, 1)

# Someone who has asked their system not to animate things should not be
# handed a looping video; give them the poster and a play button instead.
# Appended rather than spliced before </body>: that tag lives in the page
# template below, not in the body this script is editing.
shared += '''
<script>
(function () {
  var v = document.querySelector(".clip video");
  if (!v) { return; }
  try {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      v.autoplay = false; v.loop = false; v.controls = true; v.pause();
    }
  } catch (e) { /* an old browser just keeps the loop */ }
})();
</script>
'''

doc = f'''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LagScope · 卡的時候，它告訴你是誰的錯</title>
<meta name="description" content="{DESC}">
<link rel="canonical" href="{SITE}">
<link rel="icon" href="icon.png" type="image/png">
<link rel="apple-touch-icon" href="icon.png">
<meta name="theme-color" content="#F4F7F7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0A1113" media="(prefers-color-scheme: dark)">

<meta property="og:type" content="website">
<meta property="og:site_name" content="LagScope">
<meta property="og:title" content="LagScope · 卡的時候，它告訴你是誰的錯">
<meta property="og:description" content="{DESC}">
<meta property="og:url" content="{SITE}">
<meta property="og:image" content="{SITE}icon.png">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="LagScope · 卡的時候，它告訴你是誰的錯">
<meta name="twitter:description" content="{DESC}">
<meta name="twitter:image" content="{SITE}icon.png">

<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Public+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>img {{ max-width: 100%; }}</style>
{shared}
</body>
</html>
'''
(repo / "docs" / "index.html").write_text(doc, encoding="utf-8")
print("docs/index.html rebuilt:", len(doc), "bytes")
