// 平台登录门禁:在 app.js / player.js 之前加载,统一管理登录态。
// 暴露 window.ATPAuth: { ready, user, login, logout }。
// 强制登录:页面加载后先探测 /api/user/me,未登录则显示登录卡片,
// 登录成功后再初始化其余脚本。播放与下载均需登录。
(function () {
  "use strict";

  const gate = document.getElementById("loginGate");
  const form = document.getElementById("loginForm");
  const errorEl = document.getElementById("loginError");
  const submitBtn = document.getElementById("loginSubmit");

  let user = null;
  let _resolveReady = null;
  const ready = new Promise((resolve) => { _resolveReady = resolve; });

  async function login(username, password) {
    const response = await fetch("/api/user/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Login failed");
    return data;
  }

  async function logout() {
    try { await fetch("/api/user/logout", { method: "POST" }); } catch (_) { /* ignore */ }
    user = null;
    showGate();
    window.dispatchEvent(new CustomEvent("atp-auth", { detail: null }));
  }

  function showGate(message) {
    gate.hidden = false;
    document.body.classList.add("login-gated");
    if (message) {
      errorEl.textContent = message;
      errorEl.hidden = false;
    }
  }

  function hideGate() {
    gate.hidden = true;
    document.body.classList.remove("login-gated");
    errorEl.hidden = true;
  }

  async function bootstrap() {
    try {
      const response = await fetch("/api/user/me");
      if (response.ok) {
        user = await response.json();
        hideGate();
      } else {
        showGate();
      }
    } catch (_) {
      showGate();
    }
    _resolveReady();
    window.dispatchEvent(new CustomEvent("atp-auth", { detail: user }));
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;
    submitBtn.disabled = true;
    errorEl.hidden = true;
    try {
      user = await login(username, password);
      hideGate();
      document.getElementById("loginPassword").value = "";
      window.dispatchEvent(new CustomEvent("atp-auth", { detail: user }));
    } catch (error) {
      showGate(error.message || "Login failed");
    } finally {
      submitBtn.disabled = false;
    }
  });

  // 应用初始化后(其它脚本 ready),把用户信息暴露出去并触发刷新
  window.ATPAuth = {
    ready,
    get user() { return user; },
    login,
    logout,
  };

  // 注入 auth.js 后立即探测(保证在 app.js/player.js 初始化前发起,但它们会 await ready)
  bootstrap();
})();
