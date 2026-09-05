// 下载视图(SPA):整个脚本包在 IIFE 内,与播放器脚本隔离全局作用域
(function () {
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
    defaultLowest: "Use lowest quality by default (saves data)",
    defaultAtmos: "Enable Atmos by default",
    startDownload: "Download to browser",
    activity: "Activity",
    downloadQueue: "Download queue",
    noDownloads: "No downloads yet",
    emptyHint: "Your active and recent tasks will appear here.",
    tidalAccount: "Tidal accounts",
    tidal: "Tidal",
    connectAccount: "Account group",
    taskDetails: "Task details",
    signIn: "Sign in",
    signedIn: "Signed in",
    signOut: "Sign out",
    changePassword: "Change password",
    currentPassword: "Current password",
    newPassword: "New password",
    confirmNewPassword: "Confirm new password",
    passwordsMismatch: "Passwords do not match.",
    passwordChanged: "Password updated.",
    onboardingTitle: "Welcome to ATP",
    onboardingStep1: "Search tracks and albums, or paste a Tidal link to download.",
    onboardingStep2: "Pick a quality — Hi-Res / FLAC / 320 kbps — and start the download.",
    onboardingStep3: "Play in the browser with V2 DRM for the best audio quality.",
    onboardingStart: "Start listening",
    loginSubtitle: "Sign in to continue",
    getAccount: "No account? Claim one",
    username: "Username",
    password: "Password",
    invalidCredentials: "Invalid username or password.",
    localServer: "Local server",
    ffmpegReady: "ffmpeg ready",
    ffmpegMissing: "ffmpeg missing",
    account: "Account",
    storage: "Free",
    folder: "Folder",
    activeTasks: "Active",
    python: "Python",
    quota: "Download quota",
    quotaLeft: "left",
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
    downloadToBrowserDone: "Download complete, saving to this device…",
    browserDownloadStarted: "Downloading to this device…",
    requestFailed: "Request failed",
    connected: "Your Tidal account is connected{country}.",
    approveAccess: "Open Tidal to approve access. This page will update when authentication finishes.",
    continueTidal: "Continue to Tidal",
    loginFailed: "Sign in could not be started. Open the task log for details.",
    preparingLogin: "Preparing a secure Tidal sign-in link...",
    switchTheme: "Switch color theme",
    downloads: "Downloader",
    player: "Player",
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
    defaultLowest: "默认下载最低规格（省流量）",
    defaultAtmos: "默认启用 Atmos",
    startDownload: "下载到浏览器",
    activity: "任务",
    downloadQueue: "下载队列",
    noDownloads: "暂无下载任务",
    emptyHint: "正在运行和最近的任务会显示在这里。",
    tidalAccount: "Tidal 账户",
    tidal: "Tidal",
    connectAccount: "账户组",
    taskDetails: "任务详情",
    signIn: "登录",
    signedIn: "已登录",
    signOut: "退出登录",
    changePassword: "修改密码",
    currentPassword: "当前密码",
    newPassword: "新密码",
    confirmNewPassword: "确认新密码",
    passwordsMismatch: "两次输入的密码不一致。",
    passwordChanged: "密码已更新。",
    onboardingTitle: "欢迎使用 ATP",
    onboardingStep1: "搜索歌曲和专辑，或粘贴 Tidal 链接进行下载。",
    onboardingStep2: "选择音质 —— Hi-Res / FLAC / 320 kbps，然后开始下载。",
    onboardingStep3: "在浏览器中通过 V2 DRM 播放，享受最佳音质。",
    onboardingStart: "开始使用",
    getAccount: "没有账号？领取一个",
    localServer: "本地服务",
    ffmpegReady: "ffmpeg 就绪",
    ffmpegMissing: "缺少 ffmpeg",
    account: "账户",
    storage: "剩余空间",
    folder: "目录",
    activeTasks: "运行任务",
    python: "Python",
    quota: "下载额度",
    quotaLeft: "剩余",
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
    downloadToBrowserDone: "下载完成，正在保存到本机…",
    browserDownloadStarted: "正在下载到本机…",
    requestFailed: "请求失败",
    connected: "Tidal 账户已连接{country}。",
    approveAccess: "请前往 Tidal 授权。认证完成后此页面会自动更新。",
    continueTidal: "前往 Tidal",
    loginFailed: "无法启动登录，请打开任务日志查看详情。",
    preparingLogin: "正在准备 Tidal 登录链接...",
    switchTheme: "切换颜色主题",
    downloads: "下载器",
    player: "播放器",
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
  },
};

const optionLabels = {
  en: {
    low: "Low · 96 kbps", normal: "Normal · 320 kbps", high: "High · FLAC 44.1kHz", high_atmos: "High · FLAC 44.1kHz · Atmos",
    sd: "SD · 360p", hd: "HD · 720p", fhd: "FHD · 1080p",
    none_videos: "Audio only", allow_videos: "Audio + video", only_videos: "Video only",
    none_atmos: "Stereo", allow_atmos: "Atmos allowed", only_atmos: "Atmos only",
  },
  zh: {
    low: "低 · 96 kbps", normal: "标准 · 320 kbps", high: "高 · FLAC 44.1kHz", high_atmos: "高 · FLAC 44.1kHz · Atmos",
    sd: "标清 · 360p", hd: "高清 · 720p", fhd: "全高清 · 1080p",
    none_videos: "仅音频", allow_videos: "音频和视频", only_videos: "仅视频",
    none_atmos: "立体声", allow_atmos: "允许 Atmos", only_atmos: "仅 Atmos",
  },
};

const state = {
  status: null,
  jobs: [],
  jobFingerprints: {},
  accounts: [],
  // 绿色"下载到浏览器"按钮提交的任务 id:完成后自动打包推送回浏览器
  pendingBrowserDownloads: new Set(),
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
  lang: localStorage.getItem("tiddl-language") || (navigator.language && navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en"),
  theme: localStorage.getItem("tiddl-theme") || "dark",
  defaults: {
    videos: localStorage.getItem("tiddl-default-videos") === "true",
    highest: localStorage.getItem("tiddl-default-highest") === "true",
    lowest: localStorage.getItem("tiddl-default-lowest") === "true",
  },
};

function t(key, vars = {}) {
  let value = messages[state.lang][key] || messages.en[key] || key;
  for (const [name, replacement] of Object.entries(vars)) value = value.replace(`{${name}}`, replacement);
  return value;
}

const noImages = () => localStorage.getItem("tiddl-player-no-images") === "true";
const imgSrc = (url) => (noImages() ? "" : (url || ""));
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

// 惰性缓存已渲染的 SVG 图标:首次用到某个图标时才 lucide 渲染一次,之后直接复用,
// 避免频繁的图标切换/高频重渲染每次都触发 lucide 全文档扫描
const iconSvgCache = {};
function iconSvg(name) {
  if (iconSvgCache[name]) return iconSvgCache[name];
  const host = document.createElement("div");
  host.style.cssText = "position:absolute;width:0;height:0;overflow:hidden;opacity:0;pointer-events:none";
  host.innerHTML = `<i data-lucide="${name}"></i>`;
  document.body.appendChild(host);
  lucide.createIcons();
  iconSvgCache[name] = host.children[0].outerHTML;
  host.remove();
  return iconSvgCache[name];
}

function optionLabel(key, value) {
  const scoped = key === "videos" ? `${value}_${key}` : value;
  return optionLabels[state.lang][scoped] || value;
}

function compactOptionLabel(key, value, label) {
  if (key === "track_quality") return { low: "96 kbps", normal: "320 kbps", high: "44.1 kHz 无损", high_atmos: "44.1 kHz · Atmos" }[value] || label;
  if (key === "video_quality") return { sd: "360p", hd: "720p", fhd: "1080p" }[value] || label;
  return label;
}

function specToneClass(key, value) {
  const tones = {
    track_quality: { low: "white", normal: "green", high: "gold", high_atmos: "crimson" },
    video_quality: { sd: "white", hd: "green", fhd: "gold" },
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
  const quotaLimit = state.status.quota_limit || 0;
  const quotaUsed = state.status.quota_used || 0;
  const quotaPct = quotaLimit > 0 ? Math.min(100, Math.round((quotaUsed / quotaLimit) * 100)) : 0;
  $("#systemFacts").innerHTML = `
    <span class="fact quota-fact" title="${t("quota")}">
      <span class="quota-head">${iconSvg("gauge")}<strong>${t("quota")}</strong><em>${formatBytes(quotaUsed)} / ${formatBytes(quotaLimit)}</em></span>
    </span>
    <span class="fact ${state.status.tidal_ready ? "ok" : "warn"}">${iconSvg("radio")}<strong>${t("tidal")} · ${state.status.tidal_ready ? t("signedIn") : t("signIn")}</strong></span>
    <span class="fact">${iconSvg("hard-drive")}${t("storage")} <strong>${formatBytes(state.status.disk_free)}</strong></span>
    <span class="fact">${iconSvg("activity")}${t("activeTasks")} <strong>${active}</strong></span>
    <span class="fact path-fact" title="${escapeHtml(state.status.download_path)}">${iconSvg("folder")}${t("folder")} <strong>${escapeHtml(state.status.download_path)}</strong></span>`;
}

function jobCardHtml(job) {
  return `<article class="job" data-job-id="${job.id}">
      <div class="job-top">
        ${imgSrc(job.cover) ? `<img class="job-cover" src="${escapeHtml(imgSrc(job.cover))}" alt="">` : `<span class="job-icon">${iconSvg(iconName(job))}</span>`}
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
    </article>`;
}

function jobFingerprint(job) {
  // 影响卡片渲染的字段:任何一项变化才重渲该卡片
  return [job.status, job.kind, job.label, job.subtitle, job.cover, job.account_id,
    job.progress, job.downloaded, job.total, job.speed, job.current_item,
    job.resource_completed, job.resource_total, (job.downloaded_files || []).length].join("|");
}

function renderJobs() {
  const list = $("#jobList");
  $("#emptyState").hidden = state.jobs.length > 0;
  const alive = new Set();
  // 只重建状态变化的卡片;新增/删除做增删,不变的原样保留(不重扫 lucide)
  for (const job of state.jobs) {
    alive.add(job.id);
    const fp = jobFingerprint(job);
    if (state.jobFingerprints[job.id] === fp) continue;
    state.jobFingerprints[job.id] = fp;
    const existing = list.querySelector(`[data-job-id="${job.id}"]`);
    const html = jobCardHtml(job);
    if (existing) existing.outerHTML = html;
    else list.insertAdjacentHTML("beforeend", html);
  }
  list.querySelectorAll("[data-job-id]").forEach((el) => {
    if (!alive.has(el.dataset.jobId)) {
      el.remove();
      delete state.jobFingerprints[el.dataset.jobId];
    }
  });
  renderSystemFacts();
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
  return resource.specs.filter((spec) =>
    spec.choices.length > 0
    && (spec.key !== "videos" || spec.choices.length > 1)
  );
}

function renderPreview(resources, openIndexes = new Set()) {
  const panel = $("#previewPanel");
  panel.innerHTML = resources.map((resource, resourceIndex) => `
    <details class="preview-resource" data-resource-index="${resourceIndex}" ${openIndexes.has(resourceIndex) ? "open" : ""}>
      <summary class="preview-head">
        ${imgSrc(resource.cover) ? `<img class="preview-cover" src="${escapeHtml(imgSrc(resource.cover))}" alt="">` : `<span class="preview-cover preview-cover-placeholder"><i data-lucide="music"></i></span>`}
        <div class="preview-title"><strong>${escapeHtml(resource.title)}</strong><span>${escapeHtml(resource.subtitle || resource.type)}</span></div>
        <div class="preview-specs">${visibleSpecs(resource).map((spec) => specControl(resource, resourceIndex, spec)).join("")}</div>
        <span class="preview-count">${resource.items.length} ${t(resource.items.length === 1 ? "item" : "items")}</span>
        <button class="icon-button preview-remove" type="button" data-remove-resource="${resourceIndex}" title="${t("removeResource")}" aria-label="${t("removeResource")}"><i data-lucide="x"></i></button>
        <i class="preview-chevron" data-lucide="chevron-down"></i>
      </summary>
      <div class="track-list">${resource.items.map((item, index) => `<div class="track-row"><span class="track-number">${index + 1}</span><div class="track-name"><strong>${escapeHtml(item.title)}${item.explicit ? `<span class="explicit-mark">E</span>` : ""}${item.atmos ? `<span class="explicit-mark atmos-mark">Atmos</span>` : ""}</strong><span>${escapeHtml(item.artist || item.type)}</span></div><span class="track-duration">${escapeHtml(item.duration)}</span></div>`).join("")}</div>
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
      ${imgSrc(result.cover) ? `<img class="search-result-cover" src="${escapeHtml(imgSrc(result.cover))}" alt="">` : `<span class="search-result-cover preview-cover-placeholder"><i data-lucide="${result.type === "album" ? "disc-3" : "music"}"></i></span>`}
      <span class="search-result-copy"><strong>${escapeHtml(result.title)}${result.explicit ? `<span class="explicit-mark">E</span>` : ""}${result.atmos ? `<span class="explicit-mark atmos-mark">Atmos</span>` : ""}</strong><span>${escapeHtml(result.subtitle || result.type)}</span></span>
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
    if (window.ATPTrace) window.ATPTrace("search.done", { query, count: (data.results||[]).length });
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
  const lowest = $("#defaultLowest").checked;
  for (const resource of resources) {
    if (!resource.detected_options) resource.detected_options = { ...resource.download_options };
    resource.download_options = { ...resource.detected_options };
    const specs = Object.fromEntries(resource.specs.map((spec) => [spec.key, spec]));
    if (highest) {
      for (const key of ["track_quality", "video_quality"]) {
        const choices = specs[key]?.choices || [];
        if (choices.length) resource.download_options[key] = choices.at(-1);
      }
    } else if (lowest) {
      const choices = specs.track_quality?.choices || [];
      if (choices.length) resource.download_options.track_quality = choices[0];
    }
    const videoChoices = specs.videos?.choices || [];
    if (videoChoices.includes("allow")) resource.download_options.videos = includeVideos ? "allow" : "none";
    for (const spec of resource.specs) spec.value = resource.download_options[spec.key];
  }
}

function updatePreviewDefaults() {
  const highest = $("#defaultHighest").checked;
  const lowest = $("#defaultLowest").checked;
  // 最高/最低音质互斥:勾选一个时自动取消另一个
  if (highest && lowest) {
    if (document.activeElement === $("#defaultLowest")) $("#defaultHighest").checked = false;
    else $("#defaultLowest").checked = false;
  }
  state.defaults = {
    videos: $("#defaultVideos").checked,
    highest: $("#defaultHighest").checked,
    lowest: $("#defaultLowest").checked,
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
    for (const resource of data.resources) state.previewUrls.push(urls[resource.input_index] ?? resource.resource);
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
  const me = window.ATPAuth && window.ATPAuth.user;
  if (!me) {
    $("#authButton").innerHTML = iconSvg("log-in");
    $("#authButton").title = t("signIn");
    $("#authButton").onclick = () => { if (window.ATPAuth) window.ATPAuth.login("", "").catch(() => {}); };
    $("#userMenuName").textContent = "";
    $("#userMenuPanel [data-user-action=accounts]").hidden = true;
    return;
  }
  $("#authButton").innerHTML = iconSvg(me.is_admin ? "shield-check" : "user-round");
  $("#authButton").title = me.username + (me.is_admin ? " · admin" : "");
  $("#userMenuName").textContent = me.username + (me.is_admin ? " · admin" : "");
  $("#userMenuPanel [data-user-action=accounts]").hidden = !me.is_admin;
  // 点击按钮切换下拉菜单;菜单项用事件委托处理
  $("#authButton").onclick = (event) => {
    event.stopPropagation();
    const panel = $("#userMenuPanel");
    panel.hidden = !panel.hidden;
    $("#authButton").setAttribute("aria-expanded", String(!panel.hidden));
  };
  lucide.createIcons();
}

// 用户菜单项:账号池(管理员)/改密码/登出
$("#userMenuPanel").addEventListener("click", async (event) => {
  const item = event.target.closest("[data-user-action]");
  if (!item) return;
  $("#userMenuPanel").hidden = true;
  $("#authButton").setAttribute("aria-expanded", "false");
  if (item.dataset.userAction === "accounts") { await openAuth(); return; }
  if (item.dataset.userAction === "password") { openPasswordDialog(); return; }
  if (item.dataset.userAction === "logout") {
    if (window.ATPAuth) await window.ATPAuth.logout();
    renderAuthButton();
    refreshAll();
  }
});
// 点击页面其它位置关闭用户菜单
document.addEventListener("click", (event) => {
  if (!event.target.closest("#userMenu")) {
    const panel = $("#userMenuPanel");
    if (panel && !panel.hidden) {
      panel.hidden = true;
      $("#authButton").setAttribute("aria-expanded", "false");
    }
  }
});

// ---- 修改密码 ----
function openPasswordDialog() {
  $("#pwError").hidden = true;
  $("#pwCurrent").value = "";
  $("#pwNew").value = "";
  $("#pwConfirm").value = "";
  $("#passwordDialog").showModal();
}
$("#passwordForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const current = $("#pwCurrent").value;
  const next = $("#pwNew").value;
  const confirm = $("#pwConfirm").value;
  const errorEl = $("#pwError");
  errorEl.hidden = true;
  if (next !== confirm) {
    errorEl.textContent = t("passwordsMismatch");
    errorEl.hidden = false;
    return;
  }
  const submitBtn = $("#passwordForm button[type=submit]");
  submitBtn.disabled = true;
  try {
    await api("/api/user/password", {
      method: "POST",
      body: JSON.stringify({ current_password: current, new_password: next }),
    });
    $("#passwordDialog").close();
    showAppToast(t("passwordChanged"));
  } catch (error) {
    errorEl.textContent = error.message || t("requestFailed");
    errorEl.hidden = false;
  } finally {
    submitBtn.disabled = false;
  }
});
$("[data-close-password]").addEventListener("click", () => $("#passwordDialog").close());
$("#passwordDialog").addEventListener("click", (event) => {
  if (event.target === $("#passwordDialog")) $("#passwordDialog").close();
});

function showAppToast(message) {
  const toastEl = $("#toast");
  toastEl.textContent = message;
  toastEl.classList.add("show");
  clearTimeout(window.__appToastTimer);
  window.__appToastTimer = setTimeout(() => toastEl.classList.remove("show"), 2400);
}

// ---- 首次登录操作指引覆盖层 ----
function maybeShowOnboarding() {
  const me = window.ATPAuth && window.ATPAuth.user;
  if (!me) return;
  // 每个用户只看一次,记住在 localStorage
  const key = `tiddl-onboarding-${me.username}`;
  if (localStorage.getItem(key)) return;
  $("#onboardingOverlay").hidden = false;
}
$("#onboardingDone").addEventListener("click", () => {
  const me = window.ATPAuth && window.ATPAuth.user;
  if (me) localStorage.setItem(`tiddl-onboarding-${me.username}`, "1");
  $("#onboardingOverlay").hidden = true;
});

function healthLabel(status) {
  return t(`health${status.charAt(0).toUpperCase()}${status.slice(1)}`);
}

function healthCheckedLabel(value) {
  if (!value) return "";
  const time = new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return t("healthChecked", { time });
}

async function refreshJobs() {
  // 仅在下载器视图(/downloads)轮询任务列表;播放器视图跳过,避免后台狂刷 /api/jobs。
  if (document.body.dataset.route !== "downloads") return;
  if (!(window.ATPAuth && window.ATPAuth.user)) { state.jobs = []; renderJobs(); return; }
  state.jobs = await api("/api/jobs");
  // 绿色"下载到浏览器"自动投递:任务完成且有文件时,把打包好的文件推回浏览器本地
  if (state.pendingBrowserDownloads.size) {
    for (const id of [...state.pendingBrowserDownloads]) {
      const job = state.jobs.find((item) => item.id === id);
      if (!job) continue;
      if (job.status === "completed" && (job.downloaded_files || []).length) {
        state.pendingBrowserDownloads.delete(id);
        const link = document.createElement("a");
        link.href = `/api/jobs/${id}/download`;
        link.download = "";
        document.body.appendChild(link);
        link.click();
        link.remove();
        showToast(t("downloadToBrowserDone"));
      } else if (job.status === "failed" || job.status === "cancelled") {
        state.pendingBrowserDownloads.delete(id);
      }
    }
  }
  // 暴露下载器总网速给 SPA 壳(播放器 topbar 汇总显示)
  window.ATPDownloads = {
    speed: state.jobs.reduce((sum, job) => sum + (job.status === "running" && job.kind === "download" ? Number(job.speed) || 0 : 0), 0),
  };
  renderJobs();
  if (state.authJobId) updateAuthDialog();
}

async function refreshAccounts() {
  // Tidal 账号池仅管理员可见;普通用户/未登录拿到 401/403 时静默忽略
  try {
    const data = await api("/api/accounts");
    state.accounts = data.accounts;
  } catch (_) {
    state.accounts = [];
  }
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
    // 浏览器直连下载:逐曲触发 /api/download/browser/{track_id}(服务器只转发字节,不落盘)
    // 音质与 Atmos 已整合:track_quality 可能为 "high_atmos"(复合档),拆分回 quality + atmos
    const tracks = [];
    for (const res of state.previews) {
      let q = (res.download_options && res.download_options.track_quality) || "high";
      let atmos = "none";
      if (q.endsWith("_atmos")) { q = q.replace("_atmos", ""); atmos = "allow"; }
      for (const item of (res.items || [])) {
        if (item.type === "track" && item.id) tracks.push({ id: item.id, quality: q, atmos });
      }
    }
    if (window.ATPTrace) window.ATPTrace("download.request", {
      urls: urls.length, tracks: tracks.length,
      options: state.previews.map((r) => r.download_options),
    });
    $("#urls").value = "";
    state.previews = [];
    state.previewUrls = [];
    $("#previewPanel").hidden = true;
    // 逐个触发浏览器下载(专辑=逐曲保存);DRM/Atmos 被拒/失败曲目回退服务器任务
    const failed = [];
    for (const t of tracks) {
      try {
        const resp = await fetch(`/api/download/browser/${t.id}?quality=${encodeURIComponent(t.quality)}&atmos=${encodeURIComponent(t.atmos)}`);
        if (!resp.ok) { failed.push(t); continue; }
        const blob = await resp.blob();
        const cd = resp.headers.get("Content-Disposition") || "";
        const match = cd.match(/filename="([^"]+)"/);
        const name = match ? match[1] : `track-${t.id}.m4a`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        await new Promise((r) => setTimeout(r, 300));
      } catch (_) { failed.push(t); }
    }
    if (failed.length) {
      const result = await api("/api/downloads", { method: "POST", body: JSON.stringify({ urls: failed.map((t) => `track/${t.id}`), resource_options: [], resource_metadata: [], threads: Number($("#threads").value), skip_existing: $("#skipExisting").checked, download_path: $("#downloadPath").value, output_template: $("#outputTemplate").value }) });
      for (const job of result.jobs || []) state.pendingBrowserDownloads.add(job.id);
    }
    message.classList.add("success");
    message.textContent = t(tracks.length ? "browserDownloadStarted" : "resourceLabel");
    await refreshJobs();
  } catch (error) {
    message.classList.remove("success");
    message.textContent = error.message;
  } finally { button.disabled = false; }
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
  document.querySelectorAll("#view-downloads [data-i18n], #loginGate [data-i18n], .topbar [data-i18n]").forEach((element) => { element.textContent = t(element.dataset.i18n); });
  $("#themeButton").title = t("switchTheme");
  $("#themeButton").setAttribute("aria-label", t("switchTheme"));
  $("#refreshButton").title = t("refreshTasks");
  $("#refreshButton").setAttribute("aria-label", t("refreshTasks"));
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
  document.documentElement.removeAttribute("data-i18n-pending");
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
  catch (error) {
    console.error("Failed to refresh dashboard:", error);
    $("#systemFacts").innerHTML = `<span class="fact warn"><i data-lucide="cloud-off"></i><strong>${t("requestFailed")}</strong></span>`; lucide.createIcons();
  }
}

$("#downloadForm").addEventListener("submit", submitDownload);
$("#urls").addEventListener("input", scheduleInputAction);
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
["defaultVideos", "defaultHighest", "defaultLowest"].forEach((id) => $(`#${id}`).addEventListener("change", updatePreviewDefaults));
$("#jobList").addEventListener("click", (event) => {
  const log = event.target.closest("[data-log]");
  const cancel = event.target.closest("[data-cancel]");
  if (log) openLog(log.dataset.log);
  if (cancel) cancelJob(cancel.dataset.cancel);
});
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
$("#defaultLowest").checked = state.defaults.lowest;

applyTheme();
applyLocale();

// 登录门禁:等待平台登录后再启动网络初始化(下载器)
let appStarted = false;
function startApp() {
  if (appStarted) return;
  appStarted = true;
  refreshAll();
  // 任务列表轮询仅服务于下载器视图;间隔 3s(不需要 1.2s 那么密)。
  // refreshJobs 内部已按路由判断,播放器视图直接跳过网络请求。
  state.timer = setInterval(refreshJobs, 3000);
  state.accountTimer = setInterval(refreshAccounts, 10000);
  // 切回下载器视图时立即刷新一次,避免等待下一次 tick
  new MutationObserver(() => {
    if (document.body.dataset.route === "downloads") refreshJobs();
  }).observe(document.body, { attributes: true, attributeFilter: ["data-route"] });
}
function onAuth() {
  if (window.ATPAuth && window.ATPAuth.user) { startApp(); maybeShowOnboarding(); }
  renderAuthButton();
}
if (window.ATPAuth && window.ATPAuth.user) { startApp(); renderAuthButton(); maybeShowOnboarding(); }
window.addEventListener("atp-auth", onAuth);
})();
