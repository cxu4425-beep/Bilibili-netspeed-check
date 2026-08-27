// ==UserScript==
// @name         Bilibili Latency Monitor Bridge / 哔哩哔哩延迟监视器桥接
// @namespace    https://github.com/cxu4425-beep/Bilibili-netspeed-check
// @version      1.0.0
// @description  Tells the local Bilibili Latency Monitor which room or video you are watching. 把你正在看的直播间/视频告诉本机的延迟监视器。
// @author       Bilibili Latency Monitor contributors
// @license      MIT
// @match        https://live.bilibili.com/*
// @match        https://www.bilibili.com/video/*
// @match        https://m.bilibili.com/video/*
// @run-at       document-idle
// @grant        none
// @noframes
// ==/UserScript==

/*
 * How it works
 * ------------
 * Every few seconds (and on every SPA navigation) this script POSTs the current
 * page address to http://127.0.0.1:23124/report, where the monitor is listening.
 * Nothing else is sent: no cookies, no account data, no page content - and the
 * request never leaves your machine.
 *
 * Setup
 * -----
 * 1. Install Tampermonkey (or Violentmonkey / Greasemonkey).
 * 2. Add this script.
 * 3. In the monitor: Settings -> General -> Auto-detection -> tick
 *    "Accept userscript reports". Keep the port in sync with PORT below.
 */

(function () {
  "use strict";

  const PORT = 23124;                 // must match the monitor's bridge port
  const ENDPOINT = `http://127.0.0.1:${PORT}/report`;
  const HEARTBEAT_MS = 15000;         // keeps the monitor's report from going stale
  const RETRY_BACKOFF_MS = 60000;     // wait this long after a failure

  let lastUrl = "";
  let lastSentAt = 0;
  let mutedUntil = 0;

  function report(force) {
    const now = Date.now();
    if (now < mutedUntil) return;
    const url = location.href;
    if (!force && url === lastUrl && now - lastSentAt < HEARTBEAT_MS) return;

    lastUrl = url;
    lastSentAt = now;
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url, title: document.title || "" }),
      mode: "cors",
      cache: "no-store",
      keepalive: true,
    }).catch(function () {
      // The monitor is not running (or the bridge is off): back off quietly.
      mutedUntil = Date.now() + RETRY_BACKOFF_MS;
    });
  }

  // Bilibili is a single-page app: patch history so tab/part changes are seen.
  const pushState = history.pushState;
  const replaceState = history.replaceState;
  history.pushState = function () {
    pushState.apply(this, arguments);
    setTimeout(function () { report(true); }, 300);
  };
  history.replaceState = function () {
    replaceState.apply(this, arguments);
    setTimeout(function () { report(true); }, 300);
  };
  window.addEventListener("popstate", function () { report(true); });

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") report(true);
  });

  setInterval(function () { report(false); }, 5000);
  report(true);
})();
