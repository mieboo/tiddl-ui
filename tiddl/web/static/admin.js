// 管理端 SPA:平台用户管理 + Tidal 账号池管理。
// 独立于下载器/播放器,仅管理员可访问(后端 /api/users /api/accounts 均 require_admin)。
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
  const icon = () => { if (window.lucide) lucide.createIcons(); };

  const gate = $("adminGate");
  const app = $("adminApp");

  async function api(path, options = {}) {
    const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  }

  function showGate(message) {
    gate.hidden = false;
    app.hidden = true;
    if (message) { $("loginError").textContent = message; $("loginError").hidden = false; }
  }

  function enterApp(user) {
    gate.hidden = true;
    app.hidden = false;
    $("adminWho").textContent = user.is_admin ? `${user.username} · admin` : user.username;
    refreshAll();
    refreshTotpStatus();
  }

  async function bootstrap() {
    try {
      const response = await fetch("/api/user/me");
      if (!response.ok) throw new Error("unauth");
      const user = await response.json();
      if (!user.is_admin) throw new Error("forbidden");
      enterApp(user);
    } catch (_) {
      showGate();
    }
    icon();
  }

  $("adminLoginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const username = $("loginUsername").value.trim();
    const password = $("loginPassword").value;
    const totp = $("loginTotp").value.trim();
    $("loginSubmit").disabled = true;
    $("loginError").hidden = true;
    try {
      const user = await api("/api/user/login", { method: "POST", body: JSON.stringify({ username, password, totp: totp || null }) });
      if (!user.is_admin) { showGate("Administrator access required."); return; }
      $("loginTotp").value = "";
      $("totpField").hidden = true;
      enterApp(user);
    } catch (error) {
      // 若提示 2FA 码,显示 TOTP 输入框
      const msg = String(error.message || "");
      if (/two-factor|2fa|code/i.test(msg)) $("totpField").hidden = false;
      showGate(msg || "Login failed");
    } finally {
      $("loginSubmit").disabled = false;
    }
  });

  $("logoutButton").addEventListener("click", async () => {
    await fetch("/api/user/logout", { method: "POST" });
    showGate();
    icon();
  });

  // ---- 平台用户管理 -------------------------------------------------------
  function fmtBytes(value) {
    const n = Number(value || 0);
    if (n <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0, v = n;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v >= 100 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
  }

  async function refreshUsers() {
    const data = await api("/api/users");
    const list = $("userList");
    list.innerHTML = data.users.map((u) => {
      const tr = (u.traffic || {}).total || { download: 0, play: 0, total: 0 };
      const quota = u.quota || {};
      const quotaUsed = quota.used || 0;
      const quotaLimit = quota.limit || 0;
      return `
      <div class="account-row">
        <span class="account-avatar"><i data-lucide="${u.is_admin ? "shield-check" : "user-round"}"></i></span>
        <span class="account-copy">
          <strong>${esc(u.username)}${u.is_admin ? " · admin" : ""}</strong>
          <span>created ${new Date(u.created_at * 1000).toLocaleString()} · plays ${u.plays} · downloads ${u.downloads}</span>
          <span>traffic: ${fmtBytes(tr.total)} (↓ ${fmtBytes(tr.download)} / ▶ ${fmtBytes(tr.play)}) · quota ${fmtBytes(quotaUsed)}/${fmtBytes(quotaLimit)}</span>
        </span>
        <label class="toggle-field" title="Enabled"><input type="checkbox" data-user-toggle="${esc(u.username)}" ${u.enabled ? "checked" : ""}><span class="toggle"></span></label>
        <button class="icon-button" type="button" data-user-delete="${esc(u.username)}" title="Delete"><i data-lucide="trash-2"></i></button>
      </div>`;
    }).join("");
    icon();
  }

  function showUserMessage(text, ok) {
    const msg = $("userCreateMessage");
    msg.textContent = text || "";
    msg.hidden = !text;
    msg.classList.toggle("ok", !!ok);
    msg.classList.toggle("error", !!text && !ok);
  }

  function validateUserForm() {
    const username = $("newUsername").value.trim();
    const password = $("newPassword").value;
    const confirm = $("newPasswordConfirm").value;
    const unameOk = /^[A-Za-z0-9_.-]+$/.test(username);
    $("usernameHint").classList.toggle("invalid", username.length > 0 && !unameOk);
    const passOk = password.length >= 6;
    $("passwordHint").classList.toggle("invalid", password.length > 0 && !passOk);
    const confOk = confirm.length === 0 || password === confirm;
    $("confirmHint").classList.toggle("invalid", confirm.length > 0 && !confOk);
    return { username, password, confirm, unameOk, passOk, confOk };
  }

  $("userCreateForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const { username, password, confirm, unameOk, passOk, confOk } = validateUserForm();
    if (!unameOk) return showUserMessage("Username may only contain letters, digits, dots, underscores and dashes.", false);
    if (!passOk) return showUserMessage("Password must be at least 6 characters.", false);
    if (!confOk) return showUserMessage("Passwords do not match.", false);
    try {
      await api("/api/users", { method: "POST", body: JSON.stringify({ username, password, is_admin: $("newAdmin").checked }) });
      $("newUsername").value = ""; $("newPassword").value = ""; $("newPasswordConfirm").value = ""; $("newAdmin").checked = false;
      validateUserForm();
      showUserMessage(`User "${username}" created.`, true);
      await refreshUsers();
    } catch (error) {
      const detail = String(error.message || "");
      showUserMessage(detail, false);
    }
  });

  ["newUsername", "newPassword", "newPasswordConfirm"].forEach((id) => $("newPasswordConfirm") && $(id).addEventListener("input", validateUserForm));
  $("toggleNewPassword").addEventListener("click", () => {
    const input = $("newPassword");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    $("toggleNewPassword").innerHTML = `<i data-lucide="${show ? "eye-off" : "eye"}"></i>`;
    icon();
  });

  $("userList").addEventListener("click", async (event) => {
    const del = event.target.closest("[data-user-delete]");
    if (del) {
      if (!confirm(`Delete user "${del.dataset.userDelete}"?`)) return;
      try { await api(`/api/users/${encodeURIComponent(del.dataset.userDelete)}`, { method: "DELETE" }); await refreshUsers(); }
      catch (error) { alert(error.message); }
      return;
    }
  });
  $("userList").addEventListener("change", async (event) => {
    const toggle = event.target.closest("[data-user-toggle]");
    if (!toggle) return;
    try { await api(`/api/users/${encodeURIComponent(toggle.dataset.userToggle)}`, { method: "PATCH", body: JSON.stringify({ enabled: toggle.checked }) }); await refreshUsers(); }
    catch (error) { alert(error.message); toggle.checked = !toggle.checked; }
  });

  // ---- Tidal 账号池管理 ---------------------------------------------------
  async function refreshAccounts() {
    const data = await api("/api/accounts");
    const list = $("accountList");
    list.innerHTML = data.accounts.length ? data.accounts.map((a) => `
      <div class="account-row">
        <span class="account-avatar"><i data-lucide="user-round"></i></span>
        <span class="account-copy">
          <strong><i class="account-health-dot ${esc(a.health_status)}"></i>${esc(a.username || (a.user_id ? `Tidal ${a.user_id.slice(-6)}` : a.id))}</strong>
          <span>${esc(a.health_status)} · ${esc(a.country_code || "Tidal")} · ${a.active_tasks}/${a.assigned_tasks} tasks</span>
          <span>${subscriptionBadge(a)}${a.subscription_checked_at ? " · checked " + new Date(a.subscription_checked_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"}) : ""}</span>
        </span>
        <button class="icon-button" type="button" data-account-check-sub="${esc(a.id)}" title="Check subscription"><i data-lucide="badge-check"></i></button>
        <label class="toggle-field" title="Enabled"><input type="checkbox" data-account-toggle="${esc(a.id)}" ${a.enabled ? "checked" : ""}><span class="toggle"></span></label>
        <button class="icon-button" type="button" data-account-logout="${esc(a.id)}" title="Sign out"><i data-lucide="log-out"></i></button>
      </div>`).join("") : `<div class="account-empty">No Tidal accounts connected.</div>`;
    icon();
  }

  function subscriptionBadge(a) {
    const map = { active: ["ok", "subscribed"], expired: ["warn", "subscription expired"], checking: ["", "checking…"], unknown: ["", "subscription unknown"] };
    const [cls, label] = map[a.subscription] || map.unknown;
    return `<span class="fact ${cls}" style="margin-top:2px"><i data-lucide="${a.subscription === "active" ? "circle-check" : a.subscription === "expired" ? "triangle-alert" : "help-circle"}"></i><strong>${esc(label)}</strong></span>`;
  }

  $("addAccountButton").addEventListener("click", async () => {
    try {
      const job = await api("/api/auth/login", { method: "POST" });
      if (job.login_url) {
        const ok = confirm("Open Tidal authorization link in a new tab?\n" + job.login_url);
        if (ok) window.open(job.login_url, "_blank");
      }
      setTimeout(refreshAccounts, 3000);
    } catch (error) { alert(error.message); }
  });

  $("accountList").addEventListener("click", async (event) => {
    const checkSub = event.target.closest("[data-account-check-sub]");
    if (checkSub) {
      checkSub.disabled = true;
      try {
        await api(`/api/accounts/${checkSub.dataset.accountCheckSub}/check-subscription`, { method: "POST" });
        await refreshAll();
      } catch (error) { alert(error.message); }
      checkSub.disabled = false;
      return;
    }
    const logout = event.target.closest("[data-account-logout]");
    if (!logout) return;
    try { await api(`/api/accounts/${logout.dataset.accountLogout}/logout`, { method: "POST" }); setTimeout(refreshAccounts, 3000); }
    catch (error) { alert(error.message); }
  });
  $("accountList").addEventListener("change", async (event) => {
    const toggle = event.target.closest("[data-account-toggle]");
    if (!toggle) return;
    try { await api(`/api/accounts/${toggle.dataset.accountToggle}?enabled=${toggle.checked}`, { method: "PATCH" }); await refreshAccounts(); }
    catch (error) { alert(error.message); toggle.checked = !toggle.checked; }
  });

  // ---- 服务状态 -----------------------------------------------------------
  async function refreshFacts() {
    const st = await api("/api/status");
    $("adminFacts").innerHTML = `
      <span class="fact ok"><i data-lucide="radio"></i><strong>ATP ${esc(st.version)}</strong></span>
      <span class="fact ${st.tidal_ready ? "ok" : "warn"}"><i data-lucide="user-round"></i><strong>Tidal ${st.tidal_ready ? "ready" : "offline"}</strong></span>
      <span class="fact ${st.ffmpeg ? "ok" : "warn"}"><i data-lucide="circle-check"></i><strong>ffmpeg ${st.ffmpeg ? "ready" : "missing"}</strong></span>
      <span class="fact"><i data-lucide="hard-drive"></i><strong>${st.disk_free >= 0 ? (st.disk_free / 1024 ** 3).toFixed(1) + " GB free" : "n/a"}</strong></span>`;
    icon();
  }

  // ---- TOTP 双因素(二维码由后端 segno 生成) --------------------------------
  async function refreshTotpStatus() {
    try {
      const data = await api("/api/user/totp/setup");
      if (data.enabled) {
        $("totpStatus").textContent = "Two-factor authentication is enabled.";
        $("totpSetupPanel").hidden = true;
        $("totpDisableButton").hidden = false;
      } else {
        $("totpStatus").textContent = "Two-factor authentication is disabled.";
        $("totpDisableButton").hidden = true;
        $("totpSetupPanel").hidden = false;
        if (data.qr) {
          $("totpQr").src = data.qr;
        } else if (data.secret) {
          $("totpStatus").textContent += ` Manual: ${data.secret}`;
        }
      }
    } catch (_) { /* ignore */ }
  }

  $("totpEnableButton").addEventListener("click", async () => {
    const code = $("totpCode").value.trim();
    if (!code) return;
    try {
      await api("/api/user/totp/enable", { method: "POST", body: JSON.stringify({ code }) });
      $("totpCode").value = "";
      await refreshTotpStatus();
    } catch (error) { alert(error.message); }
  });
  $("totpDisableButton").addEventListener("click", async () => {
    if (!confirm("Disable two-factor authentication?")) return;
    try {
      await api("/api/user/totp/disable", { method: "POST" });
      await refreshTotpStatus();
    } catch (error) { alert(error.message); }
  });

  // ---- 修改自己密码 --------------------------------------------------------
  $("changePasswordForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const current = $("cpCurrent").value;
    const next = $("cpNew").value;
    if (!current || !next) return;
    try {
      await api("/api/user/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) });
      $("cpCurrent").value = ""; $("cpNew").value = "";
      alert("Password updated.");
    } catch (error) { alert(error.message); }
  });

  async function refreshAll() {
    try {
      await Promise.all([refreshUsers(), refreshAccounts(), refreshFacts(), refreshMonitor(), refreshBandwidth(), refreshTelemetry()]);
    } catch (error) {
      // 会话失效则退回登录
      if (String(error.message).toLowerCase().includes("sign in") || String(error.message).toLowerCase().includes("not signed")) {
        showGate();
      }
    }
  }

  // ---- 系统监控面板 --------------------------------------------------------
  async function refreshMonitor() {
    const m = await api("/api/admin/monitor");
    const sys = m.system;
    const memPct = sys.mem_used_percent != null ? `${sys.mem_used_percent}%` : "n/a";
    const uptime = sys.uptime_s != null ? formatUptime(sys.uptime_s) : "n/a";
    const cpu = sys.cpu_percent != null ? `${sys.cpu_percent}%` : "n/a";
    const diskFree = sys.disk_free != null ? (sys.disk_free / 1024 ** 3).toFixed(1) + " GB" : "n/a";
    const statsRows = Object.entries(m.request_stats || {}).map(([path, s]) => `
      <tr><td class="mono">${esc(path)}</td><td>${s.hits}</td><td class="${s.errors ? "warn" : ""}">${s.errors}</td><td>${s.avg_ms.toFixed(0)}ms</td></tr>`).join("");
    const routes = (m.routes || []).map((r) => `<span class="route-chip mono">${esc(r)}</span>`).join(" ");
    const live = m.live || {};
    const liveRows = Object.entries(live.by_user || {}).map(([name, bps]) => `
      <tr><td>${esc(name)}</td><td class="num">${fmtBytes(bps)}/s</td></tr>`).join("");
    const totalBps = Number(live.total_bps) || 0;
    $("monitorPanel").innerHTML = `
      <div class="monitor-grid">
        <div class="monitor-card">
          <h4>System</h4>
          <dl>
            <dt>CPU</dt><dd>${cpu}</dd>
            <dt>Memory</dt><dd>${memPct}</dd>
            <dt>Disk free</dt><dd>${diskFree}</dd>
            <dt>Uptime</dt><dd>${uptime}</dd>
            <dt>Processes</dt><dd>${sys.process_count}</dd>
            <dt>ATP</dt><dd>v${esc(sys.version)}</dd>
          </dl>
        </div>
        <div class="monitor-card">
          <h4>Live bandwidth</h4>
          <dl>
            <dt>Total</dt><dd class="num">${fmtBytes(totalBps)}/s</dd>
            <dt>Play</dt><dd class="num">${fmtBytes(Number(live.play_bps) || 0)}/s</dd>
            <dt>Download</dt><dd class="num">${fmtBytes(Number(live.download_bps) || 0)}/s</dd>
            <dt>Active sessions</dt><dd>${(live.sessions || []).length}</dd>
          </dl>
          <table class="monitor-table">
            <thead><tr><th>User</th><th>Live rate</th></tr></thead>
            <tbody>${liveRows || `<tr><td colspan="2">No active playback sessions</td></tr>`}</tbody>
          </table>
        </div>
        <div class="monitor-card">
          <h4>Request stats</h4>
          <table class="monitor-table">
            <thead><tr><th>Endpoint</th><th>Hits</th><th>Errors</th><th>Avg</th></tr></thead>
            <tbody>${statsRows || `<tr><td colspan="4">No requests yet</td></tr>`}</tbody>
          </table>
        </div>
        <div class="monitor-card monitor-wide">
          <h4>API routes</h4>
          <div class="route-list">${routes || "none"}</div>
        </div>
      </div>`;
    icon();
  }

  function formatUptime(seconds) {
    const d = Math.floor(seconds / 86400), h = Math.floor((seconds % 86400) / 3600), m = Math.floor((seconds % 3600) / 60);
    return (d ? d + "d " : "") + h + "h " + m + "m";
  }

  // ---- 限流与带宽管理 ------------------------------------------------------
  async function refreshBandwidth() {
    const data = await api("/api/admin/bandwidth");
    $("bandwidthEnabled").checked = !!data.enabled;
    $("bandwidthCapMbps").value = data.cap_mbps;
    const status = $("bandwidthStatus");
    status.textContent = data.enabled
      ? `on · ${data.cap_mbps} Mbps · ${data.active_users} active user${data.active_users === 1 ? "" : "s"}`
      : "off · unlimited";
    const jobsEl = $("bandwidthJobs");
    if ((data.jobs || []).length) {
      jobsEl.innerHTML = data.jobs.map((job) => `
        <div class="bandwidth-job-row">
          <span class="job-user">${esc(job.username || "anonymous")}</span>
          <span class="job-label" title="${esc(job.label)}">${esc(job.label)}</span>
          <span class="job-rate">${fmtBytes(job.rate_bytes_per_sec)}/s</span>
        </div>`).join("");
    } else {
      jobsEl.innerHTML = `<div class="bandwidth-empty">No active downloads.</div>`;
    }
    const usersEl = $("bandwidthUsers");
    const rows = (data.users || []).map((u) => {
      const t = (u.traffic || {}).total || {};
      const today = ((u.traffic || {}).today || {});
      return `
        <tr>
          <td>${esc(u.username)}</td>
          <td class="num">${fmtBytes(today.total || 0)}</td>
          <td class="num">${fmtBytes(t.total || 0)}</td>
          <td class="num">${fmtBytes(t.download || 0)}</td>
          <td class="num">${fmtBytes(t.play || 0)}</td>
          <td class="num">${fmtBytes(data.per_user && data.per_user[u.username] || 0)}/s</td>
        </tr>`;
    }).join("");
    usersEl.innerHTML = `
      <h4>Per-user traffic (bytes)</h4>
      ${rows ? `
        <table>
          <thead><tr><th>User</th><th>Today</th><th>Total</th><th>Download</th><th>Play</th><th>Share</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>` : `<div class="bandwidth-empty">No platform users yet.</div>`}`;
  }

  $("bandwidthSave").addEventListener("click", async () => {
    const cap = parseInt($("bandwidthCapMbps").value, 10);
    if (!cap || cap < 1 || cap > 10000) { alert("Cap must be between 1 and 10000 Mbps."); return; }
    try {
      await api("/api/admin/bandwidth", { method: "PATCH", body: JSON.stringify({ enabled: $("bandwidthEnabled").checked, cap_mbps: cap }) });
      $("bandwidthStatus").textContent = "saved ✓";
      await refreshBandwidth();
    } catch (error) { alert(error.message); }
  });

  // ---- 遥测面板:账号/设备筛选 + 行为统计 + 事件流 ---------------------------
  function fmtTime(ts) {
    if (!ts) return "—";
    return new Date(Number(ts) * 1000).toLocaleString();
  }

  async function refreshTelemetry() {
    try {
      const acct = $("telemetryAccount").value || "";
      const dev = $("telemetryDevice").value || "";
      const q = new URLSearchParams();
      if (acct) q.set("account", acct);
      if (dev) q.set("device", dev);
      const [statsRes, eventsRes, devicesRes] = await Promise.all([
        api(`/api/admin/telemetry/stats?${q}`),
        api(`/api/admin/telemetry?${q}&limit=100`),
        api("/api/admin/telemetry/devices"),
      ]);

      // 账号/设备下拉(仅首次或列表变化时重建,保留当前选择)
      const acctSel = $("telemetryAccount");
      const devSel = $("telemetryDevice");
      const accounts = [...new Set((devicesRes.devices || []).map((d) => d.account))];
      const accountHtml = `<option value="">All accounts</option>` + accounts.map((a) => `<option value="${esc(a)}" ${a === acct ? "selected" : ""}>${esc(a)}</option>`).join("");
      if (acctSel.innerHTML !== accountHtml) acctSel.innerHTML = accountHtml;
      const devices = (devicesRes.devices || []).filter((d) => !acct || d.account === acct);
      const deviceHtml = `<option value="">All devices</option>` + devices.map((d) => `<option value="${esc(d.device_id)}" ${d.device_id === dev ? "selected" : ""}>${esc((d.device_id || "?").slice(0, 8))}… (${d.count})</option>`).join("");
      if (devSel.innerHTML !== deviceHtml) devSel.innerHTML = deviceHtml;

      // 行为统计:按账号/设备/功能聚合
      const stats = statsRes.stats || [];
      $("telemetryStats").innerHTML = stats.length ? `
        <table class="monitor-table">
          <thead><tr><th>Account</th><th>Device</th><th>Feature</th><th class="num">Count</th><th>Last</th></tr></thead>
          <tbody>${stats.slice(0, 60).map((s) => `
            <tr>
              <td>${esc(s.account)}</td>
              <td class="mono">${esc((s.device_id || "?").slice(0, 8))}…</td>
              <td>${esc(s.label)}</td>
              <td class="num">${s.count}</td>
              <td class="qr-muted">${fmtTime(s.last_ts)}</td>
            </tr>`).join("")}</tbody>
        </table>` : `<div class="bandwidth-empty">No telemetry yet — log in and play on any device.</div>`;

      // 事件流:最近事件(时间/账号/设备/事件/摘要)
      const evts = eventsRes.events || [];
      $("telemetryEvents").innerHTML = evts.length ? `
        <table class="monitor-table">
          <thead><tr><th>Time</th><th>Account</th><th>Device</th><th>Event</th><th>Detail</th></tr></thead>
          <tbody>${evts.slice(0, 100).map((e) => {
            const detail = Object.entries(e.data || {}).filter(([k]) => !["device_id", "session_id"].includes(k)).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join(" ").slice(0, 100);
            return `<tr>
              <td class="qr-muted">${fmtTime(e.ts)}</td>
              <td>${esc(e.account)}</td>
              <td class="mono">${esc((e.device_id || "?").slice(0, 8))}…</td>
              <td>${esc(e.evt)}</td>
              <td class="qr-muted">${esc(detail)}</td>
            </tr>`;
          }).join("")}</tbody>
        </table>` : `<div class="bandwidth-empty">No events for this filter.</div>`;
    } catch (error) {
      if (String(error.message).toLowerCase().includes("sign in") || String(error.message).toLowerCase().includes("not signed")) showGate();
    }
  }

  $("telemetryRefresh").addEventListener("click", refreshTelemetry);
  $("telemetryAccount").addEventListener("change", () => { $("telemetryDevice").value = ""; refreshTelemetry(); });
  $("telemetryDevice").addEventListener("change", refreshTelemetry);

  $("monitorRefresh").addEventListener("click", refreshMonitor);

  bootstrap();
  setInterval(refreshAll, 5000);
})();
