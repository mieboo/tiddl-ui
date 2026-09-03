// 前端遥测:任意登录账号启用,把运行细节(错误/警告/播放事件/网络/输入)批量上报到
// 后端 /api/telemetry,写入服务器日志,便于排查手机/桌面差异等问题。
(function () {
  "use strict";

  let enabled = false;
  let queue = [];
  let timer = null;
  let seq = 0;

  function send() {
    if (!queue.length) return;
    const batch = queue;
    queue = [];
    const body = JSON.stringify(batch);
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
      ua: nav.userAgent || "",
      platform: nav.platform || "",
      lang: nav.language || "",
      vw: window.innerWidth, vh: window.innerHeight,
      dpr: window.devicePixelRatio || 1,
      isMobile: /Android|iPhone|iPad|iPod|Mobile/i.test(nav.userAgent || ""),
      touch: "ontouchstart" in window,
      maxTouch: nav.maxTouchPoints || 0,
      mem: (performance.memory && performance.memory.usedJSHeapSize) || null,
      href: location.href,
      concurrency: nav.hardwareConcurrency || null,
    };
  }

  function checkEnable() {
    const u = window.ATPAuth && window.ATPAuth.user;
    if (u && !enabled) {
      enabled = true;
      push("telemetry_start", deviceInfo());
    }
  }
  window.addEventListener("atp-auth", checkEnable);
  checkEnable();

  // 暴露给播放器等脚本:任意关键点可主动打点
  window.ATPTrace = (evt, data) => push(evt, data);

  // 全局未捕获错误 / Promise 拒绝
  window.addEventListener("error", (e) => push("window.error", { msg: e.message, src: e.filename, line: e.lineno, col: e.colno }));
  window.addEventListener("unhandledrejection", (e) => push("promise.rejection", { msg: (e.reason && e.reason.message) || String(e.reason) }));

  // 包装 console.error/warn 以捕获代码内部告警(如 v2 回退日志)
  ["error", "warn"].forEach((level) => {
    const orig = console[level].bind(console);
    console[level] = (...args) => {
      try {
        push("console." + level, { msg: args.map((a) => {
          try { return typeof a === "string" ? a : JSON.stringify(a); } catch (_) { return String(a); }
        }).join(" ") });
      } catch (_) {}
      orig(...args);
    };
  });

  // 页面生命周期
  document.addEventListener("visibilitychange", () => push("visibility", { hidden: document.hidden }));

  // ---- 用户输入事件遥测(排查"第一下点击无效"/手势吞点击) ----
  // 采集 pointer/touch/click 序列,记录目标元素、坐标、是否被手势吞掉。
  // 每个事件立即打点,但只记录可区分的信息避免刷屏。
  let lastTap = null; // 用于把 pointerdown/up/click 归组为一次 tap
  function targetDesc(el) {
    if (!el || el === document || el === window) return "document";
    const id = el.id ? "#" + el.id : "";
    const cls = (typeof el.className === "string" && el.className.trim()) ? "." + el.className.trim().split(/\s+/).join(".") : "";
    const tag = el.tagName ? el.tagName.toLowerCase() : "";
    return (tag + id + cls).slice(0, 60);
  }
  function inputPoint(e) {
    return { x: Math.round(e.clientX || 0), y: Math.round(e.clientY || 0), t: e.timeStamp ? Math.round(e.timeStamp) : 0 };
  }
  const INPUT_TYPES = ["pointerdown", "pointerup", "pointercancel", "touchstart", "touchmove", "touchend", "click", "dblclick"];
  INPUT_TYPES.forEach((type) => {
    document.addEventListener(type, (e) => {
      if (!enabled) return;
      const p = (e.pointerType) ? e.pointerType : (e.touches ? "touch" : "");
      const detail = {
        type,
        target: targetDesc(e.target),
        ptr: p,
        pt: inputPoint(e),
        defaultPrevented: e.defaultPrevented,
      };
      // pointercancel 是浏览器吞掉手势的信号,标记为上一次 tap 是否"丢失"
      if (type === "pointercancel") detail.tapLost = true;
      push("input." + type, detail);
    }, true); // capture 阶段,确保即便内层 stopPropagation 也能收到
  });

  // ---- DRM/EME 能力探测(排查 V2 播放) ----
  // 在页面加载时探测浏览器对 Widevine 的支持,尝试多种配置并逐项上报结果。
  // 供 V2 决策与诊断:Chrome/Firefox 手机端差异、配置兼容性等。
  window.ATPEmProbe = function () {
    const out = {
      hasEME: typeof navigator.requestMediaKeySystemAccess === "function",
      hasMSE: typeof MediaSource !== "undefined",
    };
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
    // 串行尝试(避免并发 CDM 冲突)
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
  // 页面加载后执行一次能力探测并上报(与账号无关)
  try {
    Promise.resolve(window.ATPEmProbe()).then((probe) => { window.ATPTrace("eme.probe", probe); });
  } catch (e) {
    window.ATPTrace("eme.probe", { error: String(e) });
  }
})();
