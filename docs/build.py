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
