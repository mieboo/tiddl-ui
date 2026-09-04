// 遥测系统:分账号、分设备、全操作事件采集。
//  - device_id: localStorage 持久化(跨会话稳定),标识"这个浏览器/这台设备"
//  - session_id: 每次页面加载生成,标识"这一次使用会话"
//  - 采集:页面生命周期、输入、播放/音质、搜索、下载、收藏、错误、DRM 探测
//  - 上报:批量(30条 或 5s 定时) -> POST /api/telemetry {device_id, session_id, events}
//  - 后端落盘 telemetry/{account}/{date}.jsonl,可经 /api/admin/telemetry 查询
(function () {
  "use strict";

  let enabled = false;
  let queue = [];
  let timer = null;
  let seq = 0;

  // ---- 设备/会话标识(与后端数据模型对齐) ----
  function getDeviceId() {
    try {
      let d = localStorage.getItem("tiddl-device-id");
      if (!d) {
        d = (crypto.randomUUID ? crypto.randomUUID() : "d" + Date.now() + Math.random().toString(16).slice(2)).replace(/-/g, "");
        localStorage.setItem("tiddl-device-id", d);
      }
      return d;
    } catch (_) { return "web-" + Math.random().toString(16).slice(2); }
  }
  function getSessionId() {
    try {
      let s = sessionStorage.getItem("tiddl-session-id");
      if (!s) { s = Date.now().toString(36) + Math.random().toString(16).slice(2); sessionStorage.setItem("tiddl-session-id", s); }
      return s;
    } catch (_) { return "s" + Math.random().toString(16).slice(2); }
  }
  const DEVICE_ID = getDeviceId();
  const SESSION_ID = getSessionId();

  function send() {
    if (!queue.length) return;
    const batch = queue;
    queue = [];
    const body = JSON.stringify({ device_id: DEVICE_ID, session_id: SESSION_ID, events: batch });
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/api/telemetry", new Blob([body], { type: "application/json" }));
      } else {
        fetch("/api/telemetry", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }).catch(() => {});
      }
    } catch (_) { /* 上报失败不重试,避免递归 */ }
  }

  function push(evt, data) {
    if (!enabled) return;
    queue.push({ seq: ++seq, t: Date.now(), evt, data: data || {} });
    if (queue.length >= 30) send();
    if (!timer) timer = setTimeout(() => { timer = null; send(); }, 5000);
  }

  function deviceInfo() {
    const nav = navigator;
    return {
      ua: nav.userAgent || "", platform: nav.platform || "", lang: nav.language || "",
      vw: window.innerWidth, vh: window.innerHeight, dpr: window.devicePixelRatio || 1,
      isMobile: /Android|iPhone|iPad|iPod|Mobile/i.test(nav.userAgent || ""),
      touch: "ontouchstart" in window, maxTouch: nav.maxTouchPoints || 0,
      mem: (performance.memory && performance.memory.usedJSHeapSize) || null,
      href: location.href, concurrency: nav.hardwareConcurrency || null,
    };
  }

  function checkEnable() {
    const u = window.ATPAuth && window.ATPAuth.user;
    if (u && !enabled) {
      enabled = true;
      push("session.start", { device_id: DEVICE_ID, session_id: SESSION_ID, ...deviceInfo() });
    }
  }
  window.addEventListener("atp-auth", checkEnable);
  checkEnable();

  // 暴露给播放器等脚本:任何关键点可主动打点(自动带 device/session)
  window.ATPTrace = (evt, data) => push(evt, data);

  // ---- 全操作埋点 ----

  // 登录/登出(auth.js 派发 atp-auth 时 detail 有 user 或 null)
  window.addEventListener("atp-auth", (e) => {
    if (!enabled && e.detail) checkEnable();
    push(e.detail ? "auth.login" : "auth.logout", { user: e.detail && e.detail.username });
  });

  // 页面生命周期
  document.addEventListener("visibilitychange", () => push("page.visibility", { hidden: document.hidden }));
  window.addEventListener("pagehide", () => push("page.hide", {}));

  // 全局未捕获错误 / Promise 拒绝
  window.addEventListener("error", (e) => push("error.window", { msg: e.message, src: e.filename, line: e.lineno, col: e.colno }));
  window.addEventListener("unhandledrejection", (e) => push("error.promise", { msg: (e.reason && e.reason.message) || String(e.reason) }));

  // 包装 console.error/warn(捕获内部告警,如 v2 回退日志)
  ["error", "warn"].forEach((level) => {
    const orig = console[level].bind(console);
    console[level] = (...args) => {
      try { push("console." + level, { msg: args.map((a) => { try { return typeof a === "string" ? a : JSON.stringify(a); } catch (_) { return String(a); } }).join(" ") }); } catch (_) {}
      orig(...args);
    };
  });

  // 输入事件(pointer/touch/click),节流 pointermove 之外的事件:
  // pointerdown/up/cancel + click 低频可靠,直接记录;避免刷屏。
  function targetDesc(el) {
    if (!el || el === document || el === window) return "document";
    const id = el.id ? "#" + el.id : "";
    const cls = (typeof el.className === "string" && el.className.trim()) ? "." + el.className.trim().split(/\s+/).join(".") : "";
    return ((el.tagName ? el.tagName.toLowerCase() : "") + id + cls).slice(0, 60);
  }
  const INPUT_TYPES = ["pointerdown", "pointerup", "pointercancel", "click", "dblclick"];
  INPUT_TYPES.forEach((type) => {
    document.addEventListener(type, (e) => {
      if (!enabled) return;
      const p = (e.pointerType) ? e.pointerType : (e.touches ? "touch" : "");
      push("input." + type, {
        type, target: targetDesc(e.target), ptr: p,
        pt: { x: Math.round(e.clientX || 0), y: Math.round(e.clientY || 0) },
        defaultPrevented: e.defaultPrevented,
        tapLost: type === "pointercancel",
      });
    }, true);
  });

  // 键盘(搜索输入等)
  document.addEventListener("keydown", (e) => {
    if (!enabled) return;
    if (e.key === "Enter" || e.key.length === 1) {
      push("input.keydown", { key: e.key, target: targetDesc(e.target) });
    }
  }, true);

  // ---- DRM/EME 能力探测 ----
  window.ATPEmProbe = function () {
    const out = { hasEME: typeof navigator.requestMediaKeySystemAccess === "function", hasMSE: typeof MediaSource !== "undefined" };
    if (!out.hasEME || !out.hasMSE) return out;
    out.isTypeSupported = {};
    ["audio/mp4", "audio/mp4;codecs=\"mp4a.40.2\"", "audio/mp4;codecs=mp4a.40.2", "audio/mp4;codecs=\"flac\""].forEach((c) => {
      try { out.isTypeSupported[c] = MediaSource.isTypeSupported(c); } catch (e) { out.isTypeSupported[c] = "err"; }
    });
    const configs = [
      { label: "aac-plain", initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4;codecs=\"mp4a.40.2\"" }] },
      { label: "mp4-any", initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4" }] },
      { label: "flac-plain", initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4;codecs=\"flac\"" }] },
      { label: "aac-sw-crypto", initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4;codecs=\"mp4a.40.2\"", robustness: "SW_SECURE_CRYPTO" }] },
      { label: "aac-sw-decode", initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4;codecs=\"mp4a.40.2\"", robustness: "SW_SECURE_DECODE" }] },
    ];
    out.results = configs.map((cfg) => ({ label: cfg.label, ok: false, err: null }));
    const attempt = (i) => {
      if (i >= configs.length) return Promise.resolve();
      const cfg = configs[i];
      return navigator.requestMediaKeySystemAccess("com.widevine.alpha", [cfg])
        .then((access) => { out.results[i].ok = true; out.results[i].keySystem = access.keySystem || "com.widevine.alpha"; })
        .catch((err) => { out.results[i].err = String(err && err.message || err); })
        .then(() => attempt(i + 1));
    };
    return attempt(0).then(() => out);
  };
  try {
    Promise.resolve(window.ATPEmProbe()).then((probe) => { window.ATPTrace("eme.probe", probe); });
  } catch (e) {
    window.ATPTrace("eme.probe", { error: String(e) });
  }
})();
