const $ = (selector) => document.querySelector(selector);

const messages = {
  en: {
    resourceLabel: "Search Tidal or add links",
    searchPlaceholder: "Search tracks and albums, or paste a Tidal link",
    advanced: "Advanced",
    downloadFolder: "Download folder",
    outputTemplate: "Output template",
    concurrentDownloads: "Concurrent downloads",
    skipExisting: "Skip existing files",
    defaultVideos: "Download videos by default",
    defaultHighest: "Use highest quality by default",
    defaultAtmos: "Enable Atmos by default",
    startDownload: "Start download",
    activity: "Activity",
    downloadQueue: "Download queue",
    noDownloads: "No downloads yet",
    emptyHint: "Your active and recent tasks will appear here.",
    tidalAccount: "Tidal accounts",
    connectAccount: "Account group",
    taskDetails: "Task details",
    signIn: "Sign in",
    signedIn: "Signed in",
    signOut: "Sign out",
    localServer: "Local server",
    ffmpegReady: "ffmpeg ready",
    ffmpegMissing: "ffmpeg missing",
    account: "Account",
    storage: "Free",
    folder: "Folder",
    activeTasks: "Active",
    python: "Python",
    loadingPreview: "Loading resource information...",
    item: "item",
    items: "items",
    showingFirst: "Showing the first 100 items.",
    waiting: "Waiting to start",
    viewLog: "View log",
    cancel: "Cancel",
    noOutput: "No output yet.",
    taskAdded: "{count} task added to the download queue.",
    tasksAdded: "{count} tasks added to the download queue.",
    requestFailed: "Request failed",
    connected: "Your Tidal account is connected{country}.",
    approveAccess: "Open Tidal to approve access. This page will update when authentication finishes.",
    continueTidal: "Continue to Tidal",
    loginFailed: "Sign in could not be started. Open the task log for details.",
    preparingLogin: "Preparing a secure Tidal sign-in link...",
    switchTheme: "Switch color theme",
    refreshTasks: "Refresh tasks",
    statusQueued: "Queued",
    statusRunning: "Running",
    statusCompleted: "Completed",
    statusFailed: "Failed",
    statusCancelled: "Cancelled",
    audio: "Audio",
    video: "Video",
    track: "Track",
    album: "Album",
    content: "Content",
    mode: "Mode",
    unavailable: "N/A",
    removeResource: "Remove resource",
    searching: "Searching Tidal...",
    noSearchResults: "No tracks or albums found.",
    added: "Added",
    chooseSearchResult: "Choose a search result to add it first.",
    accounts: "{count} accounts",
    oneAccount: "1 account",
    addAccount: "Add account",
    noAccounts: "No Tidal accounts connected.",
    accountTasks: "{active} active · {assigned} assigned",
    disableAccount: "Enable or disable account",
    totalProgress: "Total progress",
    healthUnknown: "Not checked",
    healthChecking: "Checking",
    healthHealthy: "Healthy",
    healthDegraded: "Unstable",
    healthUnhealthy: "Isolated",
    healthChecked: "checked {time}",
    qrTitle: "Use on your phone",
    qrHint: "Keep your phone on the same network, then scan the code or open a URL below.",
    qrBindWarning: "The server currently listens on 127.0.0.1 only. Start it with TIDDL_HOST=0.0.0.0 so your phone can connect.",
    qrNoAddress: "No LAN address detected.",
  },
  zh: {
    resourceLabel: "搜索 Tidal 或添加链接",
    searchPlaceholder: "搜索歌曲和专辑，或粘贴 Tidal 链接",
    advanced: "高级设置",
    downloadFolder: "下载目录",
    outputTemplate: "输出模板",
    concurrentDownloads: "并发下载数",
    skipExisting: "跳过已有文件",
    defaultVideos: "默认下载视频",
    defaultHighest: "默认下载最高规格",
    defaultAtmos: "默认启用 Atmos",
    startDownload: "开始下载",
    activity: "任务",
    downloadQueue: "下载队列",
    noDownloads: "暂无下载任务",
    emptyHint: "正在运行和最近的任务会显示在这里。",
    tidalAccount: "Tidal 账户",
    connectAccount: "账户组",
    taskDetails: "任务详情",
    signIn: "登录",
    signedIn: "已登录",
    signOut: "退出登录",
    localServer: "本地服务",
    ffmpegReady: "ffmpeg 就绪",
    ffmpegMissing: "缺少 ffmpeg",
    account: "账户",
    storage: "剩余空间",
    folder: "目录",
    activeTasks: "运行任务",
    python: "Python",
    loadingPreview: "正在读取资源信息...",
    item: "项",
    items: "项",
    showingFirst: "仅显示前 100 项。",
    waiting: "等待开始",
    viewLog: "查看日志",
    cancel: "取消",
    noOutput: "暂无输出。",
    taskAdded: "已将 {count} 个任务加入下载队列。",
    tasksAdded: "已将 {count} 个任务加入下载队列。",
    requestFailed: "请求失败",
    connected: "Tidal 账户已连接{country}。",
    approveAccess: "请前往 Tidal 授权。认证完成后此页面会自动更新。",
    continueTidal: "前往 Tidal",
    loginFailed: "无法启动登录，请打开任务日志查看详情。",
    preparingLogin: "正在准备 Tidal 登录链接...",
    switchTheme: "切换颜色主题",
    refreshTasks: "刷新任务",
    statusQueued: "排队中",
    statusRunning: "下载中",
    statusCompleted: "已完成",
    statusFailed: "失败",
    statusCancelled: "已取消",
    audio: "音频",
    video: "视频",
    track: "歌曲",
    album: "专辑",
    content: "内容",
    mode: "模式",
    unavailable: "不适用",
    removeResource: "移除资源",
    searching: "正在搜索 Tidal...",
    noSearchResults: "未找到歌曲或专辑。",
    added: "已添加",
    chooseSearchResult: "请先从搜索结果中选择要添加的内容。",
    accounts: "{count} 个账户",
    oneAccount: "1 个账户",
    addAccount: "添加账户",
    noAccounts: "尚未连接 Tidal 账户。",
    accountTasks: "{active} 个运行中 · 共分配 {assigned} 个",
    disableAccount: "启用或停用账户",
    totalProgress: "总进度",
    healthUnknown: "尚未检查",
    healthChecking: "检查中",
    healthHealthy: "正常",
    healthDegraded: "不稳定",
    healthUnhealthy: "已隔离",
    healthChecked: "{time} 检查",
    qrTitle: "在手机上使用",
    qrHint: "确保手机与电脑在同一局域网，扫码或访问下方地址。",
    qrBindWarning: "当前服务仅监听本机（127.0.0.1）。请以 TIDDL_HOST=0.0.0.0 启动，手机才能访问。",
    qrNoAddress: "未检测到局域网地址。",
  },
};

const optionLabels = {
  en: {
    low: "Low · 96 kbps", normal: "Normal · 320 kbps", high: "High · FLAC", max: "Max · Hi-Res",
    sd: "SD · 360p", hd: "HD · 720p", fhd: "FHD · 1080p",
    none_videos: "Audio only", allow_videos: "Audio + video", only_videos: "Video only",
    none_atmos: "Stereo", allow_atmos: "Atmos allowed", only_atmos: "Atmos only",
  },
  zh: {
    low: "低 · 96 kbps", normal: "标准 · 320 kbps", high: "高 · FLAC", max: "最高 · Hi-Res",
    sd: "标清 · 360p", hd: "高清 · 720p", fhd: "全高清 · 1080p",
    none_videos: "仅音频", allow_videos: "音频和视频", only_videos: "仅视频",
    none_atmos: "立体声", allow_atmos: "允许 Atmos", only_atmos: "仅 Atmos",
  },
};

const state = {
  status: null,
  jobs: [],
  accounts: [],
  previews: [],
  previewUrls: [],
  authJobId: null,
  timer: null,
  accountTimer: null,
  previewTimer: null,
  previewRequest: 0,
  searchTimer: null,
  searchRequest: 0,
  searchResults: [],
  lang: localStorage.getItem("tiddl-language") || "en",
  theme: localStorage.getItem("tiddl-theme") || "dark",
  defaults: {
    videos: localStorage.getItem("tiddl-default-videos") === "true",
    highest: localStorage.getItem("tiddl-default-highest") === "true",
    atmos: localStorage.getItem("tiddl-default-atmos") === "true",
  },
};

function t(key, vars = {}) {
  let value = messages[state.lang][key] || messages.en[key] || key;
  for (const [name, replacement] of Object.entries(vars)) value = value.replace(`{${name}}`, replacement);
  return value;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || t("requestFailed"));
  return data;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function optionLabel(key, value) {
  const scoped = key === "videos" || key === "atmos" ? `${value}_${key}` : value;
  return optionLabels[state.lang][scoped] || value;
}

function compactOptionLabel(key, value, label) {
  if (key === "track_quality") return { low: "96 kbps", normal: "320 kbps", high: "44.1 kHz", max: "96-192 kHz" }[value] || label;
  if (key === "video_quality") return { sd: "360p", hd: "720p", fhd: "1080p" }[value] || label;
  return label;
}

function specToneClass(key, value) {
  const tones = {
    track_quality: { low: "white", normal: "green", high: "gold", max: "magenta" },
    video_quality: { sd: "white", hd: "green", fhd: "gold" },
    atmos: { none: "green", allow: "gold", only: "crimson" },
  };
  return `spec-tone-${tones[key]?.[value] || "default"}`;
}

function statusLabel(status) {
  return t(`status${status.charAt(0).toUpperCase()}${status.slice(1)}`);
}

function iconName(job) {
  if (job.kind === "login") return "log-in";
  if (job.kind === "logout") return "log-out";
  return job.status === "completed" ? "circle-check" : "download";
}

function renderSystemFacts() {
  if (!state.status) return;
  const active = state.jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  $("#systemFacts").innerHTML = `
    <span class="fact ok"><i data-lucide="radio"></i><strong>${t("localServer")}</strong></span>
    <span class="fact"><i data-lucide="package"></i><strong>tiddl-ui ${escapeHtml(state.status.version)}</strong></span>
    <span class="fact"><i data-lucide="code-2"></i>${t("python")} <strong>${escapeHtml(state.status.python_version)}</strong></span>
    <span class="fact ${state.status.ffmpeg ? "ok" : "warn"}"><i data-lucide="${state.status.ffmpeg ? "circle-check" : "triangle-alert"}"></i><strong>${state.status.ffmpeg ? t("ffmpegReady") : t("ffmpegMissing")}</strong></span>
    <span class="fact ${state.status.authenticated ? "ok" : "warn"}"><i data-lucide="user-round"></i>${t("account")} <strong>${state.status.authenticated ? `${t("signedIn")}${state.status.country_code ? ` · ${escapeHtml(state.status.country_code)}` : ""}` : t("signIn")}</strong></span>
    <span class="fact"><i data-lucide="hard-drive"></i>${t("storage")} <strong>${formatBytes(state.status.disk_free)}</strong></span>
    <span class="fact"><i data-lucide="activity"></i>${t("activeTasks")} <strong>${active}</strong></span>
    <span class="fact path-fact" title="${escapeHtml(state.status.download_path)}"><i data-lucide="folder"></i>${t("folder")} <strong>${escapeHtml(state.status.download_path)}</strong></span>`;
  lucide.createIcons();
}

function renderJobs() {
  const list = $("#jobList");
  $("#emptyState").hidden = state.jobs.length > 0;
  list.innerHTML = state.jobs.map((job) => `
    <article class="job">
      <div class="job-top">
        ${job.cover ? `<img class="job-cover" src="${escapeHtml(job.cover)}" alt="">` : `<span class="job-icon"><i data-lucide="${iconName(job)}"></i></span>`}
        <div class="job-copy"><strong title="${escapeHtml(job.label)}">${escapeHtml(job.label)}</strong>${job.subtitle ? `<span class="job-subtitle" title="${escapeHtml(job.subtitle)}">${escapeHtml(job.subtitle)}</span>` : ""}<span class="job-meta">${statusLabel(job.status)}${job.account_id ? ` · ${escapeHtml(job.account_id === "default" ? "Default" : job.account_id.slice(-4))}` : ""}</span></div>
        <span class="job-status ${job.status}"></span>
      </div>
      ${job.kind === "download" && ["queued", "running"].includes(job.status) ? `
        ${job.resource_total > 1 ? `<div class="progress-wrap overall-progress">
          <div class="progress-meta"><span>${t("totalProgress")}</span><span>${job.resource_completed} / ${job.resource_total}</span></div>
          <div class="progress-track"><div class="progress-bar" style="width:${Math.round((job.resource_completed / job.resource_total) * 100)}%"></div></div>
        </div>` : ""}
        <div class="progress-wrap">
          <div class="progress-meta"><span title="${escapeHtml(job.current_item || t("waiting"))}">${escapeHtml(job.current_item || t("waiting"))}</span><span>${job.speed > 0 ? `${formatBytes(job.speed)}/s` : `${Math.round((job.progress || 0) * 100)}%`}</span></div>
          <div class="progress-track"><div class="progress-bar" style="width:${Math.max(2, Math.round((job.progress || 0) * 100))}%"></div></div>
          <div class="progress-meta"><span>${formatBytes(job.downloaded)}${job.total ? ` / ${formatBytes(job.total)}` : ""}</span><span>${Math.round((job.progress || 0) * 100)}%</span></div>
        </div>` : ""}
      <div class="job-actions"><button type="button" data-log="${job.id}">${t("viewLog")}</button>${["queued", "running"].includes(job.status) ? `<button type="button" data-cancel="${job.id}">${t("cancel")}</button>` : ""}</div>
    </article>`).join("");
  renderSystemFacts();
  lucide.createIcons();
}

function specControl(resource, resourceIndex, spec) {
  const selected = resource.download_options[spec.key];
  const disabled = spec.choices.length <= 1;
  const label = spec.choices.length
    ? compactOptionLabel(spec.key, selected, optionLabel(spec.key, selected))
    : t("unavailable");
  return `<div class="spec-control">
    <button class="spec-tag ${specToneClass(spec.key, selected)}" type="button" data-spec-toggle="${spec.key}" data-resource-index="${resourceIndex}" ${disabled ? "disabled" : ""}>
      <span>${escapeHtml(label)}</span>${disabled ? "" : `<i data-lucide="chevron-down"></i>`}
    </button>
    <div class="spec-menu" data-spec-menu="${spec.key}" hidden>
      ${spec.choices.map((choice) => `<button type="button" class="${choice === selected ? "selected" : ""}" data-spec-choice="${spec.key}" data-choice="${choice}" data-resource-index="${resourceIndex}"><span>${escapeHtml(optionLabel(spec.key, choice))}</span>${choice === selected ? `<i data-lucide="check"></i>` : ""}</button>`).join("")}
    </div>
  </div>`;
}

function visibleSpecs(resource) {
  const hasAudio = resource.specs.some((spec) => spec.key === "track_quality" && spec.choices.length);
  return resource.specs.filter((spec) =>
    spec.choices.length > 0
    && (spec.key !== "videos" || spec.choices.length > 1)
    && (spec.key !== "atmos" || hasAudio)
  );
}

function renderPreview(resources, openIndexes = new Set()) {
  const panel = $("#previewPanel");
  panel.innerHTML = resources.map((resource, resourceIndex) => `
    <details class="preview-resource" data-resource-index="${resourceIndex}" ${openIndexes.has(resourceIndex) ? "open" : ""}>
      <summary class="preview-head">
        ${resource.cover ? `<img class="preview-cover" src="${escapeHtml(resource.cover)}" alt="">` : `<span class="preview-cover preview-cover-placeholder"><i data-lucide="music"></i></span>`}
        <div class="preview-title"><strong>${escapeHtml(resource.title)}</strong><span>${escapeHtml(resource.subtitle || resource.type)}</span></div>
        <div class="preview-specs">${visibleSpecs(resource).map((spec) => specControl(resource, resourceIndex, spec)).join("")}</div>
        <span class="preview-count">${resource.items.length} ${t(resource.items.length === 1 ? "item" : "items")}</span>
        <button class="icon-button preview-remove" type="button" data-remove-resource="${resourceIndex}" title="${t("removeResource")}" aria-label="${t("removeResource")}"><i data-lucide="x"></i></button>
        <i class="preview-chevron" data-lucide="chevron-down"></i>
      </summary>
      <div class="track-list">${resource.items.map((item, index) => `<div class="track-row"><span class="track-number">${index + 1}</span><div class="track-name"><strong>${escapeHtml(item.title)}${item.explicit ? `<span class="explicit-mark">E</span>` : ""}</strong><span>${escapeHtml(item.artist || item.type)}</span></div><span class="track-duration">${escapeHtml(item.duration)}</span></div>`).join("")}</div>
      ${resource.truncated ? `<div class="preview-note">${t("showingFirst")}</div>` : ""}
    </details>`).join("");
  panel.hidden = false;
  lucide.createIcons();
}

function openPreviewIndexes() {
  return new Set([...document.querySelectorAll(".preview-resource[open]")].map((element) => Number(element.dataset.resourceIndex)));
}

function closeSpecMenus(except = null) {
  document.querySelectorAll(".spec-menu").forEach((menu) => { if (menu !== except) menu.hidden = true; });
}

function isResourceInput(value) {
  const entries = value.split(/\n+/).map((item) => item.trim()).filter(Boolean);
  const pattern = /^(?:https?:\/\/(?:listen\.)?tidal\.com\/)?(?:browse\/)?(?:(?:track|video|album|playlist|artist|mix)\/[A-Za-z0-9-]+|album\/\d+\/track\/\d+)(?:\?.*)?$/;
  return entries.length > 0 && entries.every((entry) => pattern.test(entry));
}

function renderSearchResults(results) {
  const panel = $("#searchResults");
  panel.innerHTML = results.length ? results.map((result) => {
    const added = state.previews.some((resource) => resource.resource === result.resource);
    return `<button class="search-result${added ? " added" : ""}" type="button" data-search-resource="${escapeHtml(result.resource)}" ${added ? "disabled" : ""}>
      ${result.cover ? `<img class="search-result-cover" src="${escapeHtml(result.cover)}" alt="">` : `<span class="search-result-cover preview-cover-placeholder"><i data-lucide="${result.type === "album" ? "disc-3" : "music"}"></i></span>`}
      <span class="search-result-copy"><strong>${escapeHtml(result.title)}${result.explicit ? `<span class="explicit-mark">E</span>` : ""}</strong><span>${escapeHtml(result.subtitle || result.type)}</span></span>
      <span class="search-result-type">${added ? t("added") : t(result.type)}</span>
    </button>`;
  }).join("") : `<div class="search-status">${t("noSearchResults")}</div>`;
  panel.hidden = false;
  lucide.createIcons();
}

async function searchResources() {
  const query = $("#urls").value.trim();
  if (query.length < 2 || isResourceInput(query)) { $("#searchResults").hidden = true; return; }
  const requestId = ++state.searchRequest;
  const panel = $("#searchResults");
  panel.hidden = false;
  panel.innerHTML = `<div class="search-status loading"><i data-lucide="loader-circle"></i>${t("searching")}</div>`;
  lucide.createIcons();
  try {
    const data = await api(`/api/search?query=${encodeURIComponent(query)}`);
    if (requestId !== state.searchRequest) return;
    state.searchResults = data.results;
    renderSearchResults(data.results);
  } catch (error) {
    if (requestId !== state.searchRequest) return;
    panel.hidden = true;
    $("#formMessage").textContent = error.message;
  }
}

function scheduleInputAction() {
  clearTimeout(state.previewTimer);
  clearTimeout(state.searchTimer);
  const value = $("#urls").value.trim();
  if (!value) { $("#searchResults").hidden = true; return; }
  if (isResourceInput(value)) {
    $("#searchResults").hidden = true;
    state.previewTimer = setTimeout(previewResources, 550);
  } else {
    state.searchTimer = setTimeout(searchResources, 350);
  }
}

function applyPreviewDefaults(resources) {
  const includeVideos = $("#defaultVideos").checked;
  const highest = $("#defaultHighest").checked;
  const enableAtmos = $("#defaultAtmos").checked;
  for (const resource of resources) {
    if (!resource.detected_options) resource.detected_options = { ...resource.download_options };
    resource.download_options = { ...resource.detected_options };
    const specs = Object.fromEntries(resource.specs.map((spec) => [spec.key, spec]));
    if (highest) {
      for (const key of ["track_quality", "video_quality"]) {
        const choices = specs[key]?.choices || [];
        if (choices.length) resource.download_options[key] = choices.at(-1);
      }
    }
    const videoChoices = specs.videos?.choices || [];
    if (videoChoices.includes("allow")) resource.download_options.videos = includeVideos ? "allow" : "none";
    resource.download_options.atmos = enableAtmos && specs.atmos?.choices.includes("allow") ? "allow" : "none";
    for (const spec of resource.specs) spec.value = resource.download_options[spec.key];
  }
}

function updatePreviewDefaults() {
  state.defaults = {
    videos: $("#defaultVideos").checked,
    highest: $("#defaultHighest").checked,
    atmos: $("#defaultAtmos").checked,
  };
  for (const [key, value] of Object.entries(state.defaults)) localStorage.setItem(`tiddl-default-${key}`, value);
  if (state.previews.length) {
    applyPreviewDefaults(state.previews);
    renderPreview(state.previews, openPreviewIndexes());
  }
}

async function previewResources() {
  const message = $("#formMessage");
  const inputValue = $("#urls").value;
  const urls = inputValue.split(/\n+/).map((item) => item.trim()).filter(Boolean);
  message.textContent = "";
  const panel = $("#previewPanel");
  if (!urls.length) return state.previews;
  const requestId = ++state.previewRequest;
  panel.hidden = false;
  panel.insertAdjacentHTML("beforeend", `<div class="preview-loading"><i data-lucide="loader-circle"></i>${t("loadingPreview")}</div>`);
  lucide.createIcons();
  try {
    const data = await api("/api/preview", { method: "POST", body: JSON.stringify({ urls }) });
    if (requestId !== state.previewRequest) return;
    applyPreviewDefaults(data.resources);
    state.previews.push(...data.resources);
    state.previewUrls.push(...urls);
    const currentInput = $("#urls").value;
    if (currentInput === inputValue) $("#urls").value = "";
    else if (currentInput.startsWith(inputValue)) $("#urls").value = currentInput.slice(inputValue.length).trimStart();
    renderPreview(state.previews);
    return state.previews;
  } catch (error) {
    if (requestId !== state.previewRequest) return;
    renderPreview(state.previews);
    panel.hidden = state.previews.length === 0;
    message.textContent = error.message;
    return null;
  }
}

async function refreshStatus() {
  state.status = await api("/api/status");
  $("#downloadPath").placeholder = state.status.download_path;
  renderAuthButton();
  renderSystemFacts();
}

function renderAuthButton() {
  const count = state.accounts.length;
  $("#authButton").innerHTML = `<i data-lucide="${count ? "users" : "log-in"}"></i><span>${count ? t(count === 1 ? "oneAccount" : "accounts", { count }) : t("signIn")}</span>`;
  lucide.createIcons();
}

function healthLabel(status) {
  return t(`health${status.charAt(0).toUpperCase()}${status.slice(1)}`);
}

function healthCheckedLabel(value) {
  if (!value) return "";
  const time = new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return t("healthChecked", { time });
}

async function refreshJobs() {
  state.jobs = await api("/api/jobs");
  renderJobs();
  if (state.authJobId) updateAuthDialog();
}

async function refreshAccounts() {
  const data = await api("/api/accounts");
  state.accounts = data.accounts;
  renderAuthButton();
  if ($("#authDialog").open && !state.authJobId) renderAccountGroup();
}

async function openAuth() {
  const dialog = $("#authDialog");
  dialog.showModal();
  renderAccountGroup();
  lucide.createIcons();
}

function renderAccountGroup() {
  $("#authContent").innerHTML = `<div class="account-list">${state.accounts.length ? state.accounts.map((account) => `
    <div class="account-row">
      <span class="account-avatar"><i data-lucide="user-round"></i></span>
      <span class="account-copy"><strong title="${escapeHtml(account.health_error || healthLabel(account.health_status))}"><i class="account-health-dot ${account.health_status}"></i>${escapeHtml(account.username || (account.user_id ? `Tidal ${account.user_id.slice(-6)}` : account.id))}</strong><span>${healthLabel(account.health_status)} · ${account.country_code || "Tidal"} · ${t("accountTasks", { active: account.active_tasks, assigned: account.assigned_tasks })}${account.health_checked_at ? ` · ${healthCheckedLabel(account.health_checked_at)}` : ""}</span></span>
      <label class="toggle-field" title="${t("disableAccount")}"><input type="checkbox" data-account-toggle="${account.id}" ${account.enabled ? "checked" : ""}><span class="toggle"></span></label>
      <button class="icon-button" type="button" data-account-logout="${account.id}" title="${t("signOut")}" aria-label="${t("signOut")}"><i data-lucide="log-out"></i></button>
    </div>`).join("") : `<div class="account-empty">${t("noAccounts")}</div>`}</div>
    <button class="button button-primary add-account-button" type="button" data-add-account><i data-lucide="user-plus"></i>${t("addAccount")}</button>`;
  lucide.createIcons();
}

async function addAccount() {
  const job = await api("/api/auth/login", { method: "POST" });
  state.authJobId = job.id;
  updateAuthDialog(job);
}

function updateAuthDialog(job = null) {
  job = job || state.jobs.find((item) => item.id === state.authJobId);
  if (!job || !$("#authDialog").open) return;
  if (job.login_url) $("#authContent").innerHTML = `<p>${t("approveAccess")}</p><a class="button button-primary auth-link" href="${escapeHtml(job.login_url)}" target="_blank" rel="noopener"><i data-lucide="external-link"></i>${t("continueTidal")}</a>`;
  else if (job.status === "failed") $("#authContent").innerHTML = `<p>${t("loginFailed")}</p>`;
  else $("#authContent").innerHTML = `<p>${t("preparingLogin")}</p>`;
  if (job.status === "completed") { state.authJobId = null; refreshAll().then(renderAccountGroup); }
  lucide.createIcons();
}

async function submitDownload(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button[type=submit]");
  const message = $("#formMessage");
  button.disabled = true;
  message.classList.remove("success");
  message.textContent = "";
  try {
    clearTimeout(state.previewTimer);
    const pendingInput = $("#urls").value.trim();
    if (pendingInput && !isResourceInput(pendingInput)) throw new Error(t("chooseSearchResult"));
    if (pendingInput && await previewResources() === null) throw new Error(message.textContent);
    const urls = [...state.previewUrls];
    if (!urls.length) throw new Error(t("resourceLabel"));
    const result = await api("/api/downloads", { method: "POST", body: JSON.stringify({ urls, resource_options: state.previews.map((resource) => resource.download_options), resource_metadata: state.previews.map((resource) => ({ title: resource.title, subtitle: resource.subtitle || "", cover: resource.cover, type: resource.type })), threads: Number($("#threads").value), skip_existing: $("#skipExisting").checked, download_path: $("#downloadPath").value, output_template: $("#outputTemplate").value }) });
    $("#urls").value = "";
    state.previews = [];
    state.previewUrls = [];
    $("#previewPanel").hidden = true;
    message.classList.add("success");
    message.textContent = t(result.count === 1 ? "taskAdded" : "tasksAdded", { count: result.count });
    await refreshJobs();
  } catch (error) {
    message.classList.remove("success");
    message.textContent = error.message;
  } finally { button.disabled = false; }
}

function openQrDialog() {
  const dialog = $("#qrDialog");
  const status = state.status || {};
  const urls = status.lan_urls || [];
  $("#qrBindWarning").hidden = status.host !== "127.0.0.1";
  $("#qrUrls").innerHTML = urls.length
    ? urls.map((url) => `<li><a href="${escapeHtml(url)}" target="_blank" rel="noopener"><code>${escapeHtml(url)}</code></a></li>`).join("")
    : `<li><span class="qr-muted">${escapeHtml(t("qrNoAddress"))}</span></li>`;
  const canvas = $("#qrCanvas");
  if (urls.length && window.QRCode) {
    QRCode.toCanvas(canvas, urls[0], { width: 180, margin: 1, color: { dark: "#0b0c0e", light: "#ffffff" } }, (error) => { canvas.hidden = Boolean(error); });
  } else {
    canvas.hidden = true;
  }
  dialog.showModal();
  lucide.createIcons();
}

function openLog(jobId) {
  const job = state.jobs.find((item) => item.id === jobId);
  if (!job) return;
  $("#logTitle").textContent = job.label;
  $("#logOutput").textContent = job.logs.length ? job.logs.join("\n") : t("noOutput");
  $("#logDialog").showModal();
}

async function cancelJob(jobId) {
  try { await api(`/api/jobs/${jobId}`, { method: "DELETE" }); } catch (error) { $("#formMessage").textContent = error.message; }
  await refreshJobs();
}

function applyLocale() {
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  $("#languageSelect").value = state.lang;
  document.querySelectorAll("[data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
  $("#themeButton").title = t("switchTheme");
  $("#themeButton").setAttribute("aria-label", t("switchTheme"));
  $("#refreshButton").title = t("refreshTasks");
  $("#refreshButton").setAttribute("aria-label", t("refreshTasks"));
  $("#qrButton").title = t("qrTitle");
  $("#qrButton").setAttribute("aria-label", t("qrTitle"));
  $("#urls").placeholder = t("searchPlaceholder");
  $("#advancedButton").title = t("advanced");
  $("#advancedButton").setAttribute("aria-label", t("advanced"));
  const downloadButton = $("#downloadForm button[type=submit]");
  downloadButton.title = t("startDownload");
  downloadButton.setAttribute("aria-label", t("startDownload"));
  renderAuthButton();
  renderSystemFacts();
  renderJobs();
  if (state.previews.length) renderPreview(state.previews, openPreviewIndexes());
  if (!$("#searchResults").hidden) renderSearchResults(state.searchResults);
  if ($("#authDialog").open) openAuthContentForCurrentState();
}

function openAuthContentForCurrentState() {
  const job = state.jobs.find((item) => item.id === state.authJobId);
  if (job) updateAuthDialog(job);
  else renderAccountGroup();
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  $("#themeButton").innerHTML = `<i data-lucide="${state.theme === "dark" ? "sun" : "moon"}"></i>`;
  lucide.createIcons();
}

async function refreshAll() {
  try { await Promise.all([refreshStatus(), refreshJobs(), refreshAccounts()]); }
  catch { $("#systemFacts").innerHTML = `<span class="fact warn"><i data-lucide="cloud-off"></i><strong>${t("requestFailed")}</strong></span>`; lucide.createIcons(); }
}

$("#downloadForm").addEventListener("submit", submitDownload);
$("#urls").addEventListener("input", scheduleInputAction);
$("#qrButton").addEventListener("click", openQrDialog);
$("[data-close-qr]").addEventListener("click", () => $("#qrDialog").close());
$("#authButton").addEventListener("click", openAuth);
$("#advancedButton").addEventListener("click", () => $("#advancedDialog").showModal());
$("#refreshButton").addEventListener("click", refreshAll);
$("#languageSelect").addEventListener("change", (event) => { state.lang = event.target.value; localStorage.setItem("tiddl-language", state.lang); applyLocale(); });
$("#themeButton").addEventListener("click", () => { state.theme = state.theme === "dark" ? "light" : "dark"; localStorage.setItem("tiddl-theme", state.theme); applyTheme(); });
$("[data-close-dialog]").addEventListener("click", () => $("#authDialog").close());
$("[data-close-advanced]").addEventListener("click", () => $("#advancedDialog").close());
$("[data-close-log]").addEventListener("click", () => $("#logDialog").close());
$("#authContent").addEventListener("click", async (event) => {
  if (event.target.closest("[data-add-account]")) { await addAccount(); return; }
  const logout = event.target.closest("[data-account-logout]");
  if (logout) {
    logout.disabled = true;
    await api(`/api/accounts/${logout.dataset.accountLogout}/logout`, { method: "POST" });
  }
});
$("#authContent").addEventListener("change", async (event) => {
  const toggle = event.target.closest("[data-account-toggle]");
  if (!toggle) return;
  await api(`/api/accounts/${toggle.dataset.accountToggle}?enabled=${toggle.checked}`, { method: "PATCH" });
  await refreshAll();
});
["defaultVideos", "defaultHighest", "defaultAtmos"].forEach((id) => $(`#${id}`).addEventListener("change", updatePreviewDefaults));
$("#jobList").addEventListener("click", (event) => { const log = event.target.closest("[data-log]"); const cancel = event.target.closest("[data-cancel]"); if (log) openLog(log.dataset.log); if (cancel) cancelJob(cancel.dataset.cancel); });
$("#searchResults").addEventListener("click", async (event) => {
  const result = event.target.closest("[data-search-resource]");
  if (!result || result.disabled) return;
  clearTimeout(state.searchTimer);
  $("#urls").value = result.dataset.searchResource;
  $("#searchResults").hidden = true;
  await previewResources();
  $("#urls").focus();
});
$("#previewPanel").addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-spec-toggle]");
  const choice = event.target.closest("[data-spec-choice]");
  const remove = event.target.closest("[data-remove-resource]");
  if (!toggle && !choice && !remove) return;
  event.preventDefault();
  event.stopPropagation();
  if (remove) {
    const index = Number(remove.dataset.removeResource);
    state.previews.splice(index, 1);
    state.previewUrls.splice(index, 1);
    renderPreview(state.previews);
    $("#previewPanel").hidden = state.previews.length === 0;
    $("#urls").focus();
    return;
  }
  if (toggle) {
    const menu = toggle.parentElement.querySelector(".spec-menu");
    const willOpen = menu.hidden;
    closeSpecMenus();
    menu.hidden = !willOpen;
    return;
  }
  const resourceIndex = Number(choice.dataset.resourceIndex);
  const resource = state.previews[resourceIndex];
  resource.download_options[choice.dataset.specChoice] = choice.dataset.choice;
  const spec = resource.specs.find((item) => item.key === choice.dataset.specChoice);
  if (spec) spec.value = choice.dataset.choice;
  renderPreview(state.previews, openPreviewIndexes());
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".spec-control")) closeSpecMenus();
  if (!event.target.closest(".resource-input")) $("#searchResults").hidden = true;
});

$("#defaultVideos").checked = state.defaults.videos;
$("#defaultHighest").checked = state.defaults.highest;
$("#defaultAtmos").checked = state.defaults.atmos;

applyTheme();
applyLocale();
refreshAll();
state.timer = setInterval(refreshJobs, 1200);
state.accountTimer = setInterval(refreshAccounts, 10000);
