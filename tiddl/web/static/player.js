// 播放器视图(SPA):整个脚本包在 IIFE 内,与下载脚本隔离全局作用域
(function () {
const $ = (selector) => document.querySelector(selector);
const audio = $("#audio");

// ---- 实时频谱(右栏标签页):AnalyserNode 读取解码后 PCM 频域,RAF 绘制 ----
// v2 Widevine/MSE 与 v1 直连都适用(分析的是解码后的音频流)。
// 懒加载:仅当用户打开 Spectrum 标签页时才创建 AudioContext/Analyser。
let _spectrumCtx = null;
let _spectrumAnalyser = null;
let _spectrumRaf = 0;
let _spectrumVisible = false; // 标签页是否可见(驱动绘制循环)
let _spectrumPaused = false;  // 播放是否暂停
let _spectrumOffscreens = {}; // 各视图离屏 canvas(滚动历史,坐标轴在 DOM 外)
function spectrumSetup() {
  if (_spectrumAnalyser) return true;
  try {
    if (typeof AudioContext === "undefined" && typeof webkitAudioContext === "undefined") return false;
    const AC = window.AudioContext || window.webkitAudioContext;
    _spectrumCtx = new AC();
    const src = _spectrumCtx.createMediaElementSource(audio);
    _spectrumAnalyser = _spectrumCtx.createAnalyser();
    _spectrumAnalyser.fftSize = 4096;
    _spectrumAnalyser.smoothingTimeConstant = 0.8;
    src.connect(_spectrumAnalyser);
    _spectrumAnalyser.connect(_spectrumCtx.destination);
    return true;
  } catch (e) { if (window.ATPTrace) window.ATPTrace("spectrum.setup", { error: String(e && e.message || e) }); return false; }
}
// audacity 经典频谱色带:黑→深蓝→青→绿→黄→橙→红→白
const SPECTRUM_STOPS = [
  [0.00, 12, 12, 14], [0.12, 16, 24, 80], [0.28, 24, 90, 150],
  [0.45, 40, 170, 120], [0.62, 210, 210, 40], [0.80, 230, 120, 30],
  [0.94, 220, 40, 40], [1.00, 250, 250, 250],
];
function spectrumColor(v) {
  const t = Math.max(0, Math.min(1, v));
  let i = 0;
  while (i < SPECTRUM_STOPS.length - 2 && t > SPECTRUM_STOPS[i + 1][0]) i++;
  const [t0, r0, g0, b0] = SPECTRUM_STOPS[i];
  const [t1, r1, g1, b1] = SPECTRUM_STOPS[i + 1];
  const u = (t - t0) / (t1 - t0 || 1);
  return `rgb(${(r0 + (r1 - r0) * u).toFixed(0)},${(g0 + (g1 - g0) * u).toFixed(0)},${(b0 + (b1 - b0) * u).toFixed(0)})`;
}
// 通用:滚动型可视化(频谱/CQT/色度图共用)。cols: 分帧类型。
function scrollDraw(canvas, offKey, paintCol, w, h) {
  if (!_spectrumOffscreens[offKey] || _spectrumOffscreens[offKey].width !== w || _spectrumOffscreens[offKey].height !== h) {
    _spectrumOffscreens[offKey] = document.createElement("canvas");
    _spectrumOffscreens[offKey].width = w; _spectrumOffscreens[offKey].height = h;
    const oc = _spectrumOffscreens[offKey].getContext("2d");
    oc.fillStyle = "#0c0d10"; oc.fillRect(0, 0, w, h);
  }
  const octx = _spectrumOffscreens[offKey].getContext("2d");
  octx.drawImage(_spectrumOffscreens[offKey], 1, 0, w - 1, h, 0, 0, w - 1, h);
  octx.fillStyle = "#0c0d10";
  octx.fillRect(w - 1, 0, 1, h);
  paintCol(octx, w, h);
  canvas.getContext("2d").drawImage(_spectrumOffscreens[offKey], 0, 0);
}
// 画布尺寸同步(所有频谱相关 canvas 跟随其父容器)
function spectrumSyncSizes() {
  const pairs = [
    ["#spectrumCanvas", ".spectrum-main"],
    ["#cqtCanvas", ".spectrum-part"],
    ["#chromaCanvas", ".spectrum-part"],
  ];
  for (const [sel, parentSel] of pairs) {
    const c = $(sel), parent = document.querySelector(parentSel);
    if (!c || !parent) continue;
    const rect = parent.getBoundingClientRect();
    if (rect.width > 10 && rect.height > 10) {
      const cw = Math.round(rect.width * 2), ch = Math.round(rect.height * 2);
      if (c.width !== cw || c.height !== ch) { c.width = cw; c.height = ch; }
    }
  }
}
// 主频谱图:横轴时间、纵轴频率(对数)、颜色幅度
function spectrumDraw() {
  const canvas = $("#spectrumCanvas");
  if (!canvas || !_spectrumAnalyser) return;
  if (!_spectrumVisible) return;
  spectrumSyncSizes();
  const w = canvas.width, h = canvas.height;
  const sampleRate = _spectrumCtx ? _spectrumCtx.sampleRate : 48000;
  const data = new Float32Array(_spectrumAnalyser.frequencyBinCount);
  _spectrumAnalyser.getFloatFrequencyData(data);
  const fMin = 20, fMax = 20000;
  const DB_MIN = -96, DB_MAX = -10;
  const fftSize = _spectrumAnalyser.fftSize || 4096;
  scrollDraw(canvas, "spec", (octx, W, H) => {
    for (let py = 0; py < H; py++) {
      const t = 1 - py / H;
      const f = fMin * Math.pow(fMax / fMin, t);
      const bin = Math.round(f / (sampleRate / fftSize));
      let v = 0;
      if (bin < data.length) {
        const db = data[bin];
        v = Number.isFinite(db) ? Math.max(0, Math.min(1, (db - DB_MIN) / (DB_MAX - DB_MIN))) : 0;
      }
      octx.fillStyle = spectrumColor(Math.pow(v, 0.72));
      octx.fillRect(W - 1, py, 1, 1);
    }
  }, w, h);
  spectrumDrawCqt();
  spectrumDrawChroma();
  _spectrumRaf = requestAnimationFrame(spectrumDraw);
}
// 常量 Q 变换(CQT):对数频带聚合的频谱能量
function spectrumDrawCqt() {
  const canvas = $("#cqtCanvas");
  if (!canvas || !_spectrumAnalyser) return;
  const w = canvas.width, h = canvas.height;
  const sampleRate = _spectrumCtx ? _spectrumCtx.sampleRate : 48000;
  const data = new Float32Array(_spectrumAnalyser.frequencyBinCount);
  _spectrumAnalyser.getFloatFrequencyData(data);
  const fftSize = _spectrumAnalyser.fftSize || 4096;
  // 60 个对数频带(CQT 风格),y=频带索引
  const bands = 60;
  const fMin = 27.5, fMax = 16000;
  const DB_MIN = -96, DB_MAX = -12;
  scrollDraw(canvas, "cqt", (octx, W, H) => {
    for (let b = 0; b < bands; b++) {
      const f0 = fMin * Math.pow(fMax / fMin, b / bands);
      const f1 = fMin * Math.pow(fMax / fMin, (b + 1) / bands);
      const bin0 = Math.round(f0 / (sampleRate / fftSize));
      const bin1 = Math.max(bin0 + 1, Math.round(f1 / (sampleRate / fftSize)));
      // 频带内能量聚合(RMS)
      let sum = 0, n = 0;
      for (let i = bin0; i < bin1 && i < data.length; i++) {
        if (Number.isFinite(data[i])) { sum += Math.pow(10, data[i] / 10); n++; }
      }
      const db = n ? 10 * Math.log10(sum / n) : DB_MIN;
      const v = Math.max(0, Math.min(1, (db - DB_MIN) / (DB_MAX - DB_MIN)));
      const bandH = H / bands;
      const y = H - (b + 1) / bands * H;
      octx.fillStyle = spectrumColor(Math.pow(v, 0.7));
      octx.fillRect(W - 1, y, 1, Math.max(1, Math.ceil(bandH)));
    }
  }, w, h);
}
// 色度图(Chromagram):12 音高类能量,横轴时间、纵轴音名
function spectrumDrawChroma() {
  const canvas = $("#chromaCanvas");
  if (!canvas || !_spectrumAnalyser) return;
  const w = canvas.width, h = canvas.height;
  const sampleRate = _spectrumCtx ? _spectrumCtx.sampleRate : 48000;
  const data = new Float32Array(_spectrumAnalyser.frequencyBinCount);
  _spectrumAnalyser.getFloatFrequencyData(data);
  const fftSize = _spectrumAnalyser.fftSize || 4096;
  const fMin = 55, fMax = 9000; // 覆盖多八度
  scrollDraw(canvas, "chroma", (octx, W, H) => {
    // 每个频点归属最近的音高类(按 MIDI 音高 mod 12)
    const chroma = new Array(12).fill(0);
    const counts = new Array(12).fill(0);
    const bin0 = Math.round(fMin / (sampleRate / fftSize));
    const bin1 = Math.min(data.length, Math.round(fMax / (sampleRate / fftSize)));
    for (let i = bin0; i < bin1; i++) {
      if (!Number.isFinite(data[i])) continue;
      const f = i * (sampleRate / fftSize);
      const midi = 69 + 12 * Math.log2(f / 440);
      const pc = ((Math.round(midi) % 12) + 12) % 12;
      chroma[pc] += Math.pow(10, data[i] / 10);
      counts[pc]++;
    }
    // 帧内相对归一化:取 12 类中最大能量,其余按相对 dB 衰减——
    // 避免真实音乐所有音高类都过阈值(全亮看不出音符)
    const dbs = new Array(12).fill(-120);
    let frameMax = -120;
    for (let pc = 0; pc < 12; pc++) {
      if (counts[pc]) {
        dbs[pc] = 10 * Math.log10(chroma[pc] / counts[pc]);
        if (dbs[pc] > frameMax) frameMax = dbs[pc];
      }
    }
    const RANGE = 14; // 相对最强音符的 dB 窗口:超出即暗
    for (let pc = 0; pc < 12; pc++) {
      const rel = dbs[pc] - frameMax; // <=0
      const v = Math.max(0, Math.min(1, (rel + RANGE) / RANGE));
      const rowH = H / 12;
      const y = H - (pc + 1) / 12 * H;
      octx.fillStyle = spectrumColor(Math.pow(v, 1.8)); // gamma 增强对比
      octx.fillRect(W - 1, y, 1, Math.max(1, Math.ceil(rowH)));
    }
  }, w, h);
  // 左侧音名标签覆盖层(绘制在可见 canvas,不参与滚动)
  const NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];
  const ctx2 = canvas.getContext("2d");
  const labelW = 22;
  ctx2.fillStyle = "rgba(12,13,16,0.85)";
  ctx2.fillRect(0, 0, labelW, h);
  ctx2.fillStyle = "rgba(255,255,255,0.5)";
  ctx2.font = "9px ui-monospace, monospace";
  ctx2.textAlign = "left";
  for (let pc = 0; pc < 12; pc++) {
    const y = h - (pc + 0.5) / 12 * h;
    ctx2.fillText(NOTES[pc], 3, y + 3);
  }
}
// 填充坐标轴 DOM:左频率轴、顶/底时间轴、右 dB 轴、色度图音名
function spectrumRenderAxes() {
  const fMin = 20, fMax = 20000;
  const yAxis = document.querySelector(".spectrum-yaxis");
  if (yAxis && !yAxis.dataset.built) {
    yAxis.dataset.built = "1";
    for (const f of [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]) {
      const t = Math.log10(f / fMin) / Math.log10(fMax / fMin);
      const span = document.createElement("span");
      span.textContent = f >= 1000 ? `${f / 1000}k` : String(f);
      span.style.bottom = `${(t * 100).toFixed(1)}%`;
      yAxis.appendChild(span);
    }
  }
  const rawAxis = document.querySelector(".spectrum-rawaxis");
  if (rawAxis && !rawAxis.dataset.built) {
    rawAxis.dataset.built = "1";
    rawAxis.textContent = "0dB ~ -96dB";
  }
  // 顶/底时间轴已内联 now;补充 -10s/-5s
  for (const sel of [".spectrum-topaxis", ".spectrum-xaxis"]) {
    const el = document.querySelector(sel);
    if (!el || el.dataset.built) continue;
    el.dataset.built = "1";
    const frag = document.createDocumentFragment();
    for (const sec of [-10, -5]) {
      const span = document.createElement("span");
      span.textContent = `${sec}s`;
      frag.appendChild(span);
    }
    // now 已在 HTML,插到 now 前
    el.insertBefore(frag, el.firstChild);
  }
  // 色度图音名覆盖层:用 canvas 右侧文字(不占 DOM 轴)
  const chroma = $("#chromaCanvas");
  if (chroma && !chroma.dataset.notes) {
    chroma.dataset.notes = "1";
    // 在 canvas 上叠加音名(右上角区域)
  }
}
function spectrumSetVisible(on) {
  _spectrumVisible = on;
  if (on) {
    if (!spectrumSetup()) return;
    spectrumSyncSizes();
    spectrumRenderAxes();
    if (_spectrumCtx && _spectrumCtx.state === "suspended") _spectrumCtx.resume().catch(() => {});
    if (!_spectrumRaf) _spectrumRaf = requestAnimationFrame(spectrumDraw);
  } else {
    if (_spectrumRaf) { cancelAnimationFrame(_spectrumRaf); _spectrumRaf = 0; }
  }
}
function spectrumSetPaused(p) { _spectrumPaused = p; }

window.__spectrumTest = {
  show: (on) => spectrumSetVisible(on),
  state: () => ({ visible: _spectrumVisible, hasAnalyser: !!_spectrumAnalyser, raf: _spectrumRaf, ctxState: _spectrumCtx ? _spectrumCtx.state : null }),
};

const copy = {
  en: { downloads:"Downloader", signIn:"Sign in", loginSubtitle:"Sign in to continue", username:"Username", password:"Password", getAccount:"No account? Claim one", player:"Player",playlist:"Playlist", clear:"Clear playlist", empty:"Search or paste a track or album link", nothingPlaying:"Nothing playing", lyrics:"Lyrics", noLyrics:"Lyrics will appear here", searchPlaceholder:"Search tracks and albums, or paste a Tidal link", track:"Track", album:"Album", add:"Add to playlist", play:"Play", pause:"Pause", previous:"Previous", next:"Next", shuffle:"Shuffle", repeat:"Repeat", mute:"Mute", settings:"Player settings", defaultHighest:"Play the highest quality by default", defaultLowest:"Play the lowest quality by default (96 kbps, saves data)", noImages:"Disable images (saves data)", unsupportedAtmos:"This browser cannot decode this Dolby Atmos stream (E-AC-3/AC-4). This track has no stereo stream on Tidal.", requestFailed:"Request failed", loading:"Opening stream...", loadingTracks:"Loading tracks...", loadingArtist:"Loading artist...", loadingInfo:"Loading details...", retryingStream:"Retrying stream...", noResults:"No tracks or albums found", searchFavorites:"Search your favorites", favorites:"Favorites", favorite:"Favorite", unfavorite:"Unfavorite", remove:"Remove", download:"Download", favEmpty:"Tracks you favorite will appear here", addedToQueue:"Added to playlist", alreadyInQueue:"Already in the playlist", partiallyInQueue:"Some tracks are in the playlist", downloadQueued:"Added to download queue", defaultHighestToast:"Default highest quality is enabled", defaultLowestToast:"Default lowest quality is enabled (96 kbps)", streamFailed:"This stream could not be played. The playback session may have expired or the format is not supported.", favViaAlbum:"Already favorited with its album.", artistTab:"Artist", following:"Following", followEmpty:"Artists you follow will appear here", followSearchPlaceholder:"Filter followed artists", unfollow:"Unfollow", follow:"Follow", following_:"Following" , artistEmpty:"Play a track, then click the artist name to open their page.", artistAlbums:"Albums", artistSingles:"Singles & EPs", artistTracks:"Featured", artistSearchPlaceholder:"Search artists on Tidal", artistSearchNone:"No artists found", infoTab:"Info", infoEmpty:"Play a track to see its details here.", infoType:"Type", infoArtist:"Artist", infoAlbum:"Album", infoTrackId:"Track", infoAlbumId:"Album", infoDuration:"Duration", infoQuality:"Quality", infoDepth:"Bit depth / Rate", infoCodec:"Codec", infoMode:"Mode", spectrum:"Spectrum", spectrumHint:"Spectrogram · time × frequency · color = amplitude", spectrumCqt:"CQT (Constant-Q)", spectrumChroma:"Chromagram", apiV2:"v2 · DRM", apiV1:"v1 · direct", apiFallbackV1:"v2 failed, fell back to v1", tapToPlay:"Tap to play" },
  zh: { downloads:"下载器", signIn:"登录", loginSubtitle:"登录以继续", username:"用户名", password:"密码", getAccount:"没有账号？领取一个", player:"播放器", playlist:"播放列表", clear:"清空播放列表", empty:"搜索或粘贴歌曲、专辑链接", nothingPlaying:"尚未播放", lyrics:"歌词", noLyrics:"歌词将在这里显示", searchPlaceholder:"搜索歌曲和专辑，或粘贴 Tidal 链接", track:"歌曲", album:"专辑", add:"加入播放列表", play:"播放", pause:"暂停", previous:"上一首", next:"下一首", shuffle:"随机播放", repeat:"循环模式", mute:"静音", settings:"播放器设置", defaultHighest:"默认播放最高音质", defaultLowest:"默认播放最低音质（96 kbps，节省流量）", noImages:"禁止图片（节省流量）", unsupportedAtmos:"当前浏览器无法解码这条 Dolby Atmos 音频流（E-AC-3/AC-4），且该歌曲在 Tidal 没有立体声版本。", requestFailed:"请求失败", loading:"正在打开音频流...", loadingTracks:"正在加载歌曲...", loadingArtist:"正在加载艺术家...", loadingInfo:"正在加载信息...", retryingStream:"正在重试播放...", noResults:"未找到歌曲或专辑", searchFavorites:"搜索收藏夹内的歌曲", favorites:"收藏夹", favorite:"收藏", unfavorite:"取消收藏", remove:"移除", download:"下载", favEmpty:"点击播放页的 ♥，收藏的歌曲会显示在这里", addedToQueue:"已加入播放列表", alreadyInQueue:"已在播放列表中", partiallyInQueue:"部分歌曲已在播放列表", downloadQueued:"已加入下载队列", defaultHighestToast:"您已启用默认播放最高音质", defaultLowestToast:"您已启用默认播放最低音质（96 kbps）", streamFailed:"无法播放此音频流，播放会话可能已过期或格式不受支持", favViaAlbum:"该歌曲已随专辑收藏", artistTab:"艺术家", following:"关注", followEmpty:"你关注的艺术家会显示在这里", followSearchPlaceholder:"搜索已关注的艺术家", unfollow:"取消关注", follow:"关注", following_:"已关注" , artistEmpty:"播放歌曲后，点击艺术家名字查看主页", artistAlbums:"专辑", artistSingles:"单曲 & EP", artistTracks:"参与作品", artistSearchPlaceholder:"搜索 Tidal 上的艺术家", artistSearchNone:"未找到艺术家", infoTab:"信息", infoEmpty:"播放歌曲后，这里会显示歌曲和专辑信息", infoType:"类型", infoArtist:"艺术家", infoAlbum:"专辑", infoTrackId:"歌曲", infoAlbumId:"专辑", infoDuration:"时长", infoQuality:"音质", infoDepth:"位深 / 采样率", infoCodec:"编码", infoMode:"模式", spectrum:"频谱", spectrumHint:"频谱图 · 横轴时间 × 纵轴频率 · 颜色=幅度", spectrumCqt:"CQT 恒Q频谱", spectrumChroma:"色度图", apiV2:"v2 · DRM", apiV1:"v1 · 直连", apiFallbackV1:"v2 失败，已回退 v1" }
};
function loadFavorites() { try { const value=JSON.parse(localStorage.getItem("tiddl-player-favorites")||"[]"); return Array.isArray(value)?value.filter(entry=>entry&&entry.id).map(entry=>entry.kind==="album"?{...entry,_excluded:new Set(Array.isArray(entry.excluded)?entry.excluded:[])}:{...entry,kind:entry.kind||"track"}):[]; } catch { return []; } }
function loadFollows() { try { const value=JSON.parse(localStorage.getItem("tiddl-player-follows")||"[]"); return Array.isArray(value)?value.filter(a=>a&&a.id&&a.id!=="undefined"):[]; } catch { return []; } }
function readStore(key) { try { return JSON.parse(localStorage.getItem(key)||"null"); } catch { return null; } }
function loadQueueSession() { const saved=readStore("tiddl-player-queue"); if(!Array.isArray(saved&&saved.queue))return {queue:[],current:-1,shuffle:false,repeat:0,openAlbums:[]}; const queue=saved.queue.filter(track=>track&&track.id).map(track=>({...plainTrack(track),_sourceType:track._sourceType==="album"?"album":"track",_sourceKey:track._sourceKey||(track._sourceType==="album"?`album/${track.album_id}`:`track/${track.id}`)})); return { queue, current: saved.current>=0&&saved.current<queue.length?saved.current:(queue.length?0:-1), shuffle: Boolean(saved.shuffle), repeat: Number(saved.repeat)||0, openAlbums: Array.isArray(saved.openAlbums)?saved.openAlbums:[] }; }
function saveQueueSession() { writeStore("tiddl-player-queue",{queue:state.queue.map(({_sourceType,_sourceKey,...rest})=>({...rest,_sourceType:_sourceType||"track",_sourceKey:_sourceKey||`track/${rest.id}`})),current:state.current,shuffle:state.shuffle,repeat:state.repeat,openAlbums:[...state.openAlbums]}); }
function writeStore(key,value) { try { localStorage.setItem(key,JSON.stringify(value)); } catch {} }
const state = { queue:[], current:-1, openAlbums:new Set(), openFavAlbums:new Set(), searchTimer:null, searchId:0, lang:localStorage.getItem("tiddl-language") || (navigator.language && navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en"), theme:localStorage.getItem("tiddl-theme") || "dark", shuffle:false, repeat:0, quality:"HIGH", selectedQuality:null, availableQualities:["LOW","HIGH"], actualQuality:null, _menuCalibrated:false, formatBandwidths:null, defaultHighest:localStorage.getItem("tiddl-player-default-highest")==="true", defaultLowest:localStorage.getItem("tiddl-player-default-highest")==="true" ? false : localStorage.getItem("tiddl-player-default-lowest")!=="false", noImages:localStorage.getItem("tiddl-player-no-images")==="true", lyrics:[], activeLyric:-1, resolving:0, selectedTrackId:null, selectedInfo:null, coverLyrics:false, favorites:loadFavorites(), follows:loadFollows(), libraryTab:"playlist", favFilter:null, followFilter:null, toastTimer:null, downloadPending:false, panelTab:"artist", artistView:null, artistSearchTimer:null, artistSearchId:0, currentInfo:null, preload:null, preloadPending:false, currentIsDirect:false, currentStreamUrl:null, currentSessionId:null, speedSession:null, speedBytes:0, speedTime:0, speedRate:0, drmBroken:localStorage.getItem("tiddl-player-drm-broken")==="true", tapToPlay:false, ...(({queue,current,shuffle,repeat,openAlbums})=>({queue,current,shuffle,repeat,openAlbums:new Set(openAlbums)}))(loadQueueSession()) };
const t = (key) => copy[state.lang][key] || copy.en[key] || key;
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const imgSrc = (url) => (state.noImages ? "" : (url || ""));
async function api(path, options={}) {
  // 给请求加超时:手机网络波动/后端慢时避免永久挂起("Opening stream..."卡死)
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  const t0 = performance.now();
  let response;
  let ok = false;
  try { response = await fetch(path, { headers: { "Content-Type": "application/json" }, signal: ctrl.signal, ...options }); ok = response.ok; }
  catch (err) { clearTimeout(timer); if (window.ATPTrace && /player|search/i.test(path)) window.ATPTrace("api.request", { path, method: (options.method || "GET").toUpperCase(), ok: false, error: err && err.name === "AbortError" ? "timeout" : "network", ms: Math.round(performance.now() - t0) }); throw new Error(err && err.name === "AbortError" ? "Request timed out" : (t("requestFailed"))); }
  clearTimeout(timer);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || t("requestFailed"));
  // 遥测:记录客户端关键请求(播放/搜索),带请求参数与耗时,便于排查音质切换等问题
  if (window.ATPTrace && /player|search/i.test(path)) {
    let params = null;
    try {
      const body = JSON.parse(options.body || "{}");
      params = { quality: body.quality, atmos: body.atmos, drm: body.drm, aac_only: body.aac_only, track_id: body.track_id, resource: body.resource };
    } catch (_) { /* GET 或无 body */ }
    window.ATPTrace("api.request", { path, method: (options.method || "GET").toUpperCase(), ok, params, ms: Math.round(performance.now() - t0) });
  }
  return data;
}
const icon = () => lucide.createIcons();
function formatTime(value) { if(!Number.isFinite(value)) return "0:00"; const m=Math.floor(value/60), s=Math.floor(value%60); return `${m}:${String(s).padStart(2,"0")}`; }
function paintRange(el) { const min=Number(el.min)||0, max=Number(el.max)||1; const pct=(Number(el.value)-min)/(max-min)*100; el.style.setProperty("--range-fill",`${pct}%`); }
function markOverflowTitles() { requestAnimationFrame(()=>{document.querySelectorAll("[data-tscroll]").forEach(box=>{const text=box.querySelector(".scroll-title-text"); if(!text){box.classList.remove("overflowing");return;} const textW=text.offsetWidth; const over=textW>box.clientWidth+2; box.classList.toggle("overflowing",over); if(over){const px=box.clientWidth-textW; box.style.setProperty("--scroll-distance",`${px}px`); const seconds=Math.min(24,Math.max(1.2,Math.abs(px)/30)); box.style.setProperty("--scroll-duration",`${seconds.toFixed(2)}s`);} });}); }
function tScroll(text,tag="span",attrs="") { return `<${tag} class="tscroll" data-tscroll ${attrs}><span class="scroll-title-text">${esc(text)}</span></${tag}>`; }
// 歌曲标题 + Explicit E 徽标(卡片标题用;explicit=true 时内联在标题后)
function explicitTitle(text,explicit,tag="strong") { return `<${tag} class="tscroll" data-tscroll><span class="scroll-title-text">${esc(text)}${explicit?`<span class="explicit-badge">E</span>`:""}</span></${tag}>`; }
// 歌曲标题 + Atmos 徽标(卡片标题用;atmos=true 时显示"Atmos",风格与 explicit 徽标一致)
function atmosTitle(text,atmos,tag="strong") { return `<${tag} class="tscroll" data-tscroll><span class="scroll-title-text">${esc(text)}${atmos?`<span class="explicit-badge atmos-badge">Atmos</span>`:""}</span></${tag}>`; }
// 组合:歌曲标题 + Explicit E 徽标 + Atmos 徽标(两标并存时都显示)
function trackTitleBadges(text, explicit, atmos, tag="strong") {
  const badges = (explicit ? `<span class="explicit-badge">E</span>` : "") + (atmos ? `<span class="explicit-badge atmos-badge">Atmos</span>` : "");
  return `<${tag} class="tscroll" data-tscroll><span class="scroll-title-text">${esc(text)}${badges}</span></${tag}>`;
}
// 专辑卡艺人:优先专辑主艺人(album_artists,后端加载专辑时附带),回退到曲目单数主艺人,
// 最后才回退到曲目复数艺人(可能含演唱者,如 HOYO-MIX 专辑的 Mika Kobayashi)
function albumArtistsOf(track) {
  if (track && Array.isArray(track.album_artists) && track.album_artists.length) {
    return track.album_artists.map(a => ({ id: String(a.id), name: String(a.name) })).filter(a => a.id);
  }
  if (track && track.track_artist && track.track_artist.id) {
    return [{ id: String(track.track_artist.id), name: String(track.track_artist.name || "") }];
  }
  return artistsOf(track);
}
function albumArtistLink(track, extraAttrs = "") {
  return artistLink({ ...(track || {}), artists: albumArtistsOf(track), artist: albumArtistsOf(track).map(a => a.name).join(", ") }, extraAttrs);
}
// 归一化艺术家数组:优先用带 id+name 的数组,回退到 artist_id/artist,也支持 DOM 元素上的 data-artists
function artistsOf(entry) {
  if (entry && entry.dataset && entry.dataset.artists) {
    try {
      const list = JSON.parse(entry.dataset.artists);
      return list.map(a => ({ id: String(a.id), name: String(a.name) })).filter(a => a.id);
    } catch { /* fall through */ }
  }
  if (entry && Array.isArray(entry.artists) && entry.artists.length) {
    return entry.artists.map(a => ({ id: String(a.id), name: String(a.name) })).filter(a => a.id);
  }
  if (entry && entry.artist_id) return [{ id: String(entry.artist_id), name: String(entry.artist || "") }];
  return [];
}
// 渲染可点击艺术家名(带 data-artists 供多艺术家弹出选择):
// 单个直接 data-artist-open;多个把完整列表序列化到 data-artists,点击时弹选择菜单
function artistLink(entry, extraAttrs = "") {
  const list = artistsOf(entry);
  if (!list.length) {
    // 无 id(不可点)但有名字:回退显示名字,保证所有歌曲/专辑都显艺术家
    const label = String((entry && entry.artist) || "");
    return label ? tScroll(label, "span", `data-artist-link ${extraAttrs}`) : "";
  }
  const label = list.map(a => a.name).join(", ");
  if (list.length === 1) {
    return tScroll(label, "span", `data-artist-link data-artist-open="${esc(list[0].id)}" ${extraAttrs}`);
  }
  const payload = esc(JSON.stringify(list));
  return tScroll(label, "span", `data-artist-link data-artist-open="${esc(list[0].id)}" data-artists="${payload}" ${extraAttrs}`);
}
// 多艺术家选择菜单:点开一个浮层列出所有艺术家,选中后打开对应艺术家页
let chooserEl = null;
function showArtistChooser(anchor, artists) {
  hideArtistChooser();
  const menu = document.createElement("div");
  menu.className = "artist-chooser";
  menu.innerHTML = artists.map(a => `<button type="button" data-artist-chooser-id="${esc(a.id)}">${esc(a.name)}</button>`).join("");
  document.body.appendChild(menu);
  const rect = anchor.getBoundingClientRect();
  menu.style.left = `${Math.min(rect.left, window.innerWidth - 180)}px`;
  menu.style.top = `${rect.bottom + 4}px`;
  chooserEl = menu;
  menu.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-artist-chooser-id]");
    if (!btn) return;
    openArtistPage(btn.dataset.artistChooserId);
    hideArtistChooser();
  });
}
function hideArtistChooser() { if (chooserEl) { chooserEl.remove(); chooserEl = null; } }
function applyTheme() { document.documentElement.dataset.theme=state.theme; $("#themeButton").innerHTML=`<i data-lucide="${state.theme === "dark" ? "sun" : "moon"}"></i>`; icon(); }
function applyLocale() { document.documentElement.lang=state.lang === "zh" ? "zh-CN" : "en"; $("#languageSelect").value=state.lang; document.querySelectorAll("#view-player [data-i18n], #loginGate [data-i18n], .topbar [data-i18n]").forEach(el=>el.textContent=t(el.dataset.i18n)); document.querySelectorAll("#view-player [data-placeholder]").forEach(el=>el.placeholder=t(el.dataset.placeholder)); $("#playerSearch").placeholder=t(state.libraryTab==="favorites"?"searchFavorites":"searchPlaceholder"); document.querySelectorAll("#view-player [data-title]").forEach(el=>{el.title=t(el.dataset.title);el.setAttribute("aria-label",t(el.dataset.title));}); renderQueue(); renderFavorites(); renderQualityControl(); if(state.artistView&&!state.artistView.loading&&!state.artistView.error)renderArtistView(); renderFollowing(); renderFollowButton(); document.documentElement.removeAttribute("data-i18n-pending"); }
function singleTrackRow(track,index) { return `<button class="queue-item ${index===state.current?"active":""}${String(track.id)===String(state.selectedTrackId)?" selected":""}" type="button" data-play="${index}" data-track-id="${esc(String(track.id))}">${imgSrc(track.cover)?`<img src="${esc(imgSrc(track.cover))}" alt="">`:`<span class="queue-cover-placeholder"><i data-lucide="music"></i></span>`}<span class="queue-copy">${trackTitleBadges(track.title,track.explicit,track.atmos,"strong")}${artistLink(track)}</span><span class="queue-duration">${formatTime(track.duration)}</span><span class="queue-remove queue-fav icon-button${isTrackFavorited(track)?" fav-on":""}" data-fav-track="${index}" title="Favorite"><i data-lucide="heart"></i></span><span class="queue-remove icon-button" data-remove="${index}" title="Remove"><i data-lucide="x"></i></span></button>`; }
function renderQueue() {
  $("#queueCount").textContent=state.queue.length;
  $("#queueEmpty").hidden=state.libraryTab!=="playlist"||state.queue.length>0;
  if(state.libraryTab==="playlist"){
    const groups=[];
    state.queue.forEach((track,index)=>{const key=track._sourceType==="album"?track._sourceKey:`track:${track.id}`;let group=groups.find(item=>item.key===key);if(!group){group={key,type:track._sourceType,tracks:[]};groups.push(group);}group.tracks.push({track,index});});
    $("#playerQueue").innerHTML=groups.map(group=>{if(group.type!=="album")return group.tracks.map(({track,index})=>singleTrackRow(track,index)).join("");const first=group.tracks[0].track;const encoded=encodeURIComponent(group.key);return `<details class="playlist-album preview-resource" data-album-key="${esc(encoded)}" ${state.openAlbums.has(group.key)?"open":""}><summary class="playlist-album-head preview-head">${imgSrc(first.cover)?`<img class="preview-cover" src="${esc(imgSrc(first.cover))}" alt="">`:`<span class="preview-cover preview-cover-placeholder"><i data-lucide="disc-3"></i></span>`}<span class="preview-title">${tScroll(first.album,"strong")}${albumArtistLink(first)}</span><span class="preview-count">${group.tracks.length}</span><span class="queue-remove queue-fav icon-button${isFavorite("album",first.album_id)?" fav-on":""}" data-fav-album-id="${esc(String(first.album_id||""))}" title="Favorite"><i data-lucide="heart"></i></span><span class="queue-remove icon-button" data-remove-group="${esc(encoded)}" title="Remove"><i data-lucide="x"></i></span></summary><div class="playlist-album-tracks">${group.tracks.map(({track,index},trackIndex)=>`<button class="playlist-track-row queue-inner-row ${index===state.current?"active":""}" type="button" data-play="${index}"><span class="track-number">${track.track_number||trackIndex+1}</span><span class="track-name">${trackTitleBadges(track.title,track.explicit,track.atmos,"strong")}${artistLink(track)}</span><span class="track-duration">${formatTime(track.duration)}</span><span class="queue-remove queue-fav icon-button${isTrackFavorited(track)?" fav-on":""}" data-fav-track="${index}" title="${t(isTrackFavorited(track)?"unfavorite":"favorite")}"><i data-lucide="heart"></i></span><span class="queue-remove icon-button" data-remove="${index}" title="${t("remove")}"><i data-lucide="x"></i></span></button>`).join("")}</div></details>`;}).join("");
    markOverflowTitles();
    icon();
  }
  saveQueueSession();
  syncAddedIcons();
}
// 队列成员变化后,同步收藏夹/艺术家列表里加号↔对勾(仅替换图标,不整体重渲染)
// 惰性缓存 plus/check 两个 SVG,切换时直接替换,避免每点一次都 lucide 全文档扫描
let addIconCache=null;
function cachedAddIcon(name) {
  if(!addIconCache){
    const host=document.createElement("div");
    host.style.cssText="position:absolute;width:0;height:0;overflow:hidden;opacity:0;pointer-events:none";
    host.innerHTML='<i data-lucide="plus"></i><i data-lucide="check"></i>';
    document.body.appendChild(host);
    lucide.createIcons();
    addIconCache={plus:host.children[0].outerHTML, check:host.children[1].outerHTML};
    host.remove();
  }
  return addIconCache[name]||`<i data-lucide="${name}"></i>`;
}
function applyAddIcon(el,state) {
  const cls=state==="full"?"added":state==="partial"?"partial":"";
  const icon=state==="none"?"plus":"check";
  const tip=state==="full"?t("addedToQueue"):state==="partial"?t("partiallyInQueue"):t("add");
  if(el.dataset.addState===state)return false;
  el.dataset.addState=state;
  el.classList.remove("added","partial");
  if(cls)el.classList.add(cls);
  el.title=tip;
  el.innerHTML=cachedAddIcon(icon);
  return true;
}
function syncAddedIcons() {
  // 单曲图标(收藏单曲/专辑内单曲/艺术家专辑内单曲/艺术家参与作品):一律按自身 id 是否在队列
  document.querySelectorAll("[data-fav-add-btn],[data-inner-add],[data-artist-inner-add],[data-artist-track-add]").forEach(el=>{
    const track=favInnerTrack(el)??(el.dataset.favAddBtn!==undefined?state.favorites[Number(el.dataset.favAddBtn)]:null)??((el.dataset.artistTrackAdd!==undefined&&state.artistView)?state.artistView.tracks[Number(el.dataset.artistTrackAdd)]:null);
    if(track)applyAddIcon(el,trackInQueue(track.id)?"full":"none");
  });
  // 专辑头(收藏/艺术家):三态
  document.querySelectorAll("[data-album-fav-add],[data-artist-add]").forEach(el=>{
    const entry=el.dataset.albumFavAdd!==undefined?state.favorites[Number(el.dataset.albumFavAdd)]:artistEntries()[Number(el.dataset.artistAdd)];
    if(entry)applyAddIcon(el,albumQueueState(entry));
  });
}
function renderResults(results) { const panel=$("#playerSearchResults"); panel.innerHTML=results.length?results.map(result=>{const[rk,rid]=result.resource.split("/");const artists=artistsOf(result);const artistsAttr=artists.length?` data-artists="${esc(JSON.stringify(artists))}"`:"";return `<button class="player-result" type="button" data-resource="${esc(result.resource)}"${artistsAttr}>${imgSrc(result.cover)?`<img src="${esc(imgSrc(result.cover))}" alt="">`:`<span></span>`}<span class="player-result-copy">${trackTitleBadges(result.title,result.explicit,result.atmos,"strong")}${artistLink(result)||tScroll(result.subtitle,"span")}</span><span class="result-fav icon-button${isFavorite(rk,rid)?" fav-on":""}" data-result-fav="${rk}:${rid}" title="Favorite"><i data-lucide="heart"></i></span><span class="result-type">${t(result.type)}</span></button>`;}).join(""):`<div class="player-empty">${t("noResults")}</div>`; panel.hidden=false; markOverflowTitles(); }
function plainTrack(track) { const artists=artistsOf(track); return {kind:"track",id:String(track.id),artist_id:artists[0]?artists[0].id:"",artists,title:track.title,artist:artists.map(a=>a.name).join(", "),album:track.album,album_id:track.album_id?String(track.album_id):"",album_artists:track.album_artists,track_artist:track.track_artist?{id:String(track.track_artist.id),name:String(track.track_artist.name)}:undefined,cover:track.cover,duration:track.duration,track_number:Number(track.track_number)||0,explicit:track.explicit,qualities:track.qualities?[...track.qualities]:["LOW","HIGH"],atmos:Boolean(track.atmos)}; }
function saveFavorites() { localStorage.setItem("tiddl-player-favorites",JSON.stringify(state.favorites.filter(entry=>!entry._pendingRemove).map(entry=>entry.kind==="album"?{...entry,excluded:[...(entry._excluded||[])]}:entry),(key,value)=>key.startsWith("_")?undefined:value)); }
// 软删除:取消收藏先打 _pendingRemove 标记,条目仍在列表可点回;离开收藏夹页时真正清理
function flushPendingRemoves() { const before=state.favorites.length; state.favorites=state.favorites.filter(entry=>!entry._pendingRemove); if(state.favorites.length!==before){saveFavorites();renderQueue();renderFavorites();refreshTrackActions();} }
function saveFollows() { localStorage.setItem("tiddl-player-follows",JSON.stringify(state.follows)); }
function isFollowing(id) { return state.follows.some(a=>String(a.id)===String(id)); }
function toggleFollowArtist(id,name,picture) { const index=state.follows.findIndex(a=>String(a.id)===String(id)); if(index>=0)state.follows.splice(index,1); else state.follows.push({id:String(id),name:name||"",picture:picture||""}); saveFollows(); renderFollowing(); renderFollowButton(); }
function isFavorite(kind,id) { return state.favorites.some(entry=>!entry._pendingRemove&&entry.kind===kind&&String(entry.id)===String(id)); }
function isAlbumCovered(entry) { return Boolean(entry.album_id)&&state.favorites.some(item=>!item._pendingRemove&&item.kind==="album"&&String(item.id)===String(entry.album_id)); }
// 队列成员判断:单曲按 id,专辑按"队列中任一曲目属于该专辑"(album_id 或 _sourceKey 匹配)
function trackInQueue(id) { return state.queue.some(item=>String(item.id)===String(id)); }
// 专辑入列三态:full=整张都在;partial=部分在;none=都不在(或无曲目缓存)。
// entry._tracks 是展开时缓存的专辑曲目清单。
function albumQueueState(entry) {
  const albumKey=`album/${entry.id}`;
  // 有曲目缓存时用曲目精确判定三态(含被移除/排除的曲目)
  if(entry._tracks&&entry._tracks.length){
    const excluded=entry._excluded||new Set();
    const total=entry._tracks.filter(track=>!excluded.has(String(track.id)));
    if(!total.length)return "none";
    const ids=new Set(state.queue.map(item=>String(item.id)));
    const hits=total.filter(track=>ids.has(String(track.id))).length;
    return hits===total.length?"full":hits?"partial":"none";
  }
  // 未加载曲目缓存时,按专辑单位是否在列判定(整张=full,否则 none)
  return state.queue.some(item=>item._sourceType==="album"&&item._sourceKey===albumKey)?"full":"none";
}
function addIcon(state,attrs) {
  const cls=state==="full"?" added":state==="partial"?" partial":"";
  const icon=state==="none"?"plus":"check";
  const tip=state==="full"?t("addedToQueue"):state==="partial"?t("partiallyInQueue"):t("add");
  return `<span class="queue-remove icon-button${cls}" ${attrs} title="${tip}" data-add-state="${state}"><i data-lucide="${icon}"></i></span>`;
}
function isTrackExcluded(track) { const album=state.favorites.find(item=>!item._pendingRemove&&item.kind==="album"&&String(item.id)===String(track.album_id)); return Boolean(album&&album._excluded&&album._excluded.has(String(track.id))); }
function isTrackFavorited(track) { return isFavorite("track",track.id)||(isAlbumCovered(track)&&!isTrackExcluded(track)); }
function addAlbumFavorite(entry) { state.favorites=state.favorites.filter(item=>!(item.kind==="track"&&String(item.album_id||"")===String(entry.id))); const artists=albumArtistsOf(entry); state.favorites.push({...entry,album_artists:entry.album_artists,artist_id:artists[0]?artists[0].id:(entry.artist_id||""),artists:artists.length?artists:undefined}); }
function toggleAlbumFavorite(entry) { const index=state.favorites.findIndex(item=>item.kind==="album"&&String(item.id)===String(entry.id)); if(index>=0){const fav=state.favorites[index]; if(fav._pendingRemove)delete fav._pendingRemove; else fav._pendingRemove=true; saveFavorites(); renderQueue(); renderFavorites(); refreshTrackActions(); return;} addAlbumFavorite(entry); saveFavorites(); renderQueue(); renderFavorites(); refreshTrackActions(); }
function toggleTrackFavorite(entry) {
  const index=state.favorites.findIndex(item=>item.kind==="track"&&String(item.id)===String(entry.id));
  if(index>=0){const fav=state.favorites[index]; if(fav._pendingRemove)delete fav._pendingRemove; else fav._pendingRemove=true; saveFavorites(); renderQueue(); renderFavorites(); refreshTrackActions(); return;}
  const album=state.favorites.find(item=>item.kind==="album"&&String(item.id)===String(entry.album_id));
  if(album){
    // 专辑已收藏:点击心形 = 切换"从专辑收藏中排除/恢复该曲"
    album._excluded??=new Set();
    const id=String(entry.id);
    if(album._excluded.has(id))album._excluded.delete(id); else album._excluded.add(id);
    saveFavorites(); renderQueue(); renderFavorites(); refreshTrackActions();
    return;
  }
  state.favorites.push(entry);saveFavorites();renderQueue();renderFavorites();refreshTrackActions();
}
function toggleFavoriteEntry(entry) { if((entry.kind||"track")==="album")return toggleAlbumFavorite(entry); toggleTrackFavorite(entry); }
function toggleQueueTrackFavorite(index) { const track=state.queue[index]; if(track)toggleTrackFavorite(plainTrack(track)); }
function toggleQueueAlbumFavorite(albumId) { const first=state.queue.find(track=>String(track.album_id)===String(albumId)); if(!first)return; const artists=albumArtistsOf(first); toggleAlbumFavorite({kind:"album",id:String(albumId),album_id:String(albumId),title:first.album,artist:artists.map(a=>a.name).join(", "),artists,cover:first.cover}); }
function favoriteRow(entry,index) {
  const album=(entry.kind||"track")==="album";
  const pending=Boolean(entry._pendingRemove);
  const heart=`<span class="queue-remove queue-fav icon-button${pending?"":" fav-on"}" data-remove-fav="${index}" title="${t(pending?"favorite":"unfavorite")}"><i data-lucide="heart"></i></span>`;
  const add=album?addIcon(albumQueueState(entry),`data-album-fav-add="${index}"`):addIcon(trackInQueue(entry.id)?"full":"none",`data-fav-add-btn="${index}"`);
  if(album){
    const cover=imgSrc(entry.cover)?`<img class="preview-cover" src="${esc(imgSrc(entry.cover))}" alt="">`:`<span class="preview-cover preview-cover-placeholder"><i data-lucide="disc-3"></i></span>`;
    const count=(()=>{const total=entry.track_count||(entry._tracks||[]).length;const removed=entry._excluded?entry._excluded.size:0;return total&&removed?`${total-removed}/${total}`:(total-removed)||"";})();
    return `<details class="playlist-album preview-resource fav-album${pending?" pending":""}" data-fav-card="${index}" ${state.openFavAlbums.has(entry.id)?"open":""}><summary class="playlist-album-head preview-head fav-album-head">${cover}<span class="preview-title">${tScroll(entry.title,"strong")}${albumArtistLink(entry)||tScroll(entry.artist||"Tidal","span")}</span><span class="preview-count">${count}</span>${heart}${add}</summary><div class="playlist-album-tracks" data-fav-album-tracks="${index}">${entry._tracks?entry._tracks.map((track,i)=>innerFavTrack(track,i,entry)).join(""):`<div class="fav-album-loading">${t("loadingTracks")}</div>`}</div></details>`;
  }
  const cover=imgSrc(entry.cover)?`<img src="${esc(imgSrc(entry.cover))}" alt="">`:`<span class="queue-cover-placeholder"><i data-lucide="music"></i></span>`;
  return `<button class="queue-item fav-item${pending?" pending":""}" type="button" data-fav-play="${index}">${cover}<span class="queue-copy">${trackTitleBadges(entry.title,entry.explicit,entry.atmos,"strong")}${artistLink(entry)}</span><span class="queue-duration">${formatTime(entry.duration)}</span>${heart}${add}</button>`;
}
function innerFavTrack(track,i,entry) {
  const excluded=Boolean(entry&&entry._excluded&&entry._excluded.has(String(track.id)));
  const covered=isFavorite("track",track.id)||(!excluded&&isAlbumCovered(track));
  return `<button class="playlist-track-row fav-track-row${excluded?" excluded":""}" type="button" data-fav-inner-row="${i}"><span class="track-number">${track.track_number||i+1}</span><span class="track-name">${trackTitleBadges(track.title,track.explicit,track.atmos,"strong")}${artistLink(track)}</span><span class="track-duration">${formatTime(track.duration)}</span><span class="queue-remove queue-fav icon-button${covered?" fav-on":""}" data-inner-fav title="${excluded?t("favorite"):t("unfavorite")}"><i data-lucide="heart"></i></span>${addIcon(trackInQueue(track.id)?"full":"none",`data-inner-add="${i}"`)}</button>`;
}
function renderFollowButton() { const button=$("#followButton"); if(!button||!state.artistView)return; const on=isFollowing(state.artistView.id); button.classList.toggle("following",on); button.innerHTML=`<i data-lucide="${on?"user-round-check":"user-round-plus"}"></i><span>${on?t("following_"):t("follow")}</span>`; icon(); }
function renderFollowing() { $("#followCount").textContent=state.follows.length; const terms=(state.followFilter||"").trim().toLowerCase().split(/\s+/).filter(Boolean); const pairs=state.follows.map((artist,index)=>({artist,index})).filter(({artist})=>{ if(!terms.length)return true; const hay=`${artist.name||""}`.toLowerCase(); return terms.every(term=>hay.includes(term)); });
  const rowsHtml=pairs.map(({artist,index})=>`<button class="queue-item follow-item" type="button" data-follow-open="${index}">${imgSrc(artist.picture)?`<img src="${esc(imgSrc(artist.picture))}" alt="">`:`<span class="queue-cover-placeholder"><i data-lucide="user-round"></i></span>`}<span class="queue-copy">${tScroll(artist.name||"Tidal","strong")}</span><span class="queue-remove queue-fav icon-button fav-on" data-follow-remove="${index}" title="${t("unfollow")}"><i data-lucide="user-round-x"></i></span></button>`).join("");
  $("#playerFollowing").innerHTML=rowsHtml||(terms.length?`<div class="player-empty"><i data-lucide="search-x"></i><span>${esc(t("noResults"))}</span></div>`:""); icon(); }
function renderFavorites() { const terms=(state.favFilter||"").trim().toLowerCase().split(/\s+/).filter(Boolean); const pairs=state.favorites.map((track,index)=>({track,index})).filter(({track})=>{if(!terms.length)return true; const haystack=`${track.title} ${track.artist} ${track.album}`.toLowerCase(); return terms.every(term=>haystack.includes(term));}); const noMatch=terms.length&&state.favorites.length&&!pairs.length; $("#favCount").textContent=state.favorites.filter(entry=>!entry._pendingRemove).length; $("#favEmpty").hidden=state.libraryTab!=="favorites"||state.favorites.length>0; $("#playerFavorites").innerHTML=noMatch?`<div class="player-empty"><i data-lucide="search-x"></i><span>${esc(t("noResults"))}</span></div>`:pairs.map(({track,index})=>favoriteRow(track,index)).join(""); markOverflowTitles(); icon(); }
function showTab(tab) { if(state.libraryTab==="favorites"&&tab!=="favorites")flushPendingRemoves(); state.libraryTab=tab; state.favFilter=null; state.followFilter=null; $("#playerSearch").value=""; $("#playerSearchResults").hidden=true; $("#searchClear").hidden=true; $("#playerSearch").placeholder=t(tab==="favorites"?"searchFavorites":tab==="following"?"followSearchPlaceholder":"searchPlaceholder"); document.querySelectorAll("[data-library-tab]").forEach(button=>button.classList.toggle("active",button.dataset.libraryTab===tab)); $("#playerQueue").hidden=tab!=="playlist"; $("#playerFavorites").hidden=tab!=="favorites"; $("#playerFollowing").hidden=tab!=="following"; $("#followEmpty").hidden=tab!=="following"||state.follows.length>0; $("#clearQueue").hidden=tab!=="playlist"; renderQueue(); renderFavorites(); if(tab==="following")renderFollowing(); }
// 搜索输入非空时显示灰色 × 清除按钮,为空隐藏
function syncSearchClear() {
  const v=$("#playerSearch").value.trim();
  $("#searchClear").hidden=!v;
  const av=$("#artistSearch");
  if(av){const clear=$("#artistSearchClear");if(clear)clear.hidden=!av.value.trim();}
}
function showPanelTab(tab) { state.panelTab=tab; document.querySelectorAll("[data-panel-tab]").forEach(button=>button.classList.toggle("active",button.dataset.panelTab===tab)); $("#lyrics").hidden=tab!=="lyrics"; $("#artistView").hidden=tab!=="artist"; $("#infoView").hidden=tab!=="info"; $("#spectrumView").hidden=tab!=="spectrum"; if(tab==="info")renderInfo(); if(tab==="artist")renderArtistView(); spectrumSetVisible(tab==="spectrum"); }
function renderInfo() {
  const view=$("#infoView");
  const row=(label,valueHtml)=>valueHtml?`<div class="info-row"><span>${esc(label)}</span><strong>${valueHtml}</strong></div>`:"";
  const heart=(active,spec)=>`<span class="queue-remove queue-fav icon-button info-action${active?" fav-on":""}" data-info-fav="${esc(spec)}" title="${t(active?"unfavorite":"favorite")}"><i data-lucide="heart"></i></span>`;
  const coverActions=(coverHtml,favActive,addState,addSpec)=>`<div class="info-cover-wrap"><div class="info-cover">${coverHtml}</div><div class="info-actions">${heart(favActive,addSpec)}${addIcon(addState,`data-info-add="${esc(addSpec)}"`)}</div></div>`;
  if(state.albumInfo){
    const a=state.albumInfo; const id=String(a.album_id||"");
    const entry={kind:"album",id,album_id:id,title:a.title,artist:a.artist,artists:[],cover:a.cover,_tracks:null};
    const coverHtml=imgSrc(a.cover)?`<img src="${esc(imgSrc(a.cover))}" alt="">`:"";
    view.innerHTML=`${coverActions(coverHtml,isFavorite("album",id),albumQueueState(entry),`album:${id}`)}${row(t("infoTitle"),esc(a.title))}${row(t("infoArtist"),a.artist?esc(a.artist):"")}${row(t("infoDuration"),formatTime(a.duration))}${row("Tracks",a.trackCount||"")}${row(t("infoAlbumId"),`album/${a.album_id}`)}`; icon(); return;
  }
  const info=state.selectedInfo||state.currentInfo;
  if(!info){view.innerHTML=`<div class="player-empty"><i data-lucide="info"></i><span>${esc(t("infoEmpty"))}</span></div>`;icon();return;}
  const rate=info.sample_rate?`${(info.sample_rate/1000).toFixed(1)} kHz`:"";
  const id=String(info.id||"");
  const coverHtml=imgSrc(info.cover)?`<img src="${esc(imgSrc(info.cover))}" alt="">`:"";
  const artistHtml=artistLink(info)||esc(String(info.artist||""));
  const albumHtml=info.album_id?`<span class="info-link info-album-link" data-info-album-open="${esc(String(info.album_id))}">${esc(String(info.album||""))}</span>`:esc(String(info.album||""));
  view.innerHTML=`${coverActions(coverHtml,isTrackFavorited(info),trackInQueue(id)?"full":"none",`track:${id}`)}${row(t("infoTitle"),esc(info.title))}${row(t("infoArtist"),artistHtml)}${row(t("infoAlbum"),albumHtml)}${row(t("infoDuration"),formatTime(info.duration))}${row(t("infoQuality"),info.quality)}${row(t("infoDepth"),[info.bit_depth?`${info.bit_depth} bit`:"",rate,info.bitrate?`${info.bitrate} kbps`:""].filter(Boolean).join(" / "))}${row(t("infoCodec"),String(info.codec||"").toUpperCase())}${row(t("infoMode"),info.audio_mode==="DOLBY_ATMOS"?"Dolby Atmos":info.audio_mode&&info.audio_mode!=="STEREO"?info.audio_mode:"Stereo")}${row(t("infoTrackId"),`track/${id}`)}${row(t("infoAlbumId"),info.album_id?`album/${info.album_id}`:"")}`; icon(); }
function infoActionSpec(spec) {
  const sep=spec.indexOf(":"), kind=spec.slice(0,sep), id=spec.slice(sep+1);
  if(kind==="album"){
    const a=state.albumInfo; const artists=albumArtistsOf(a||{});
    return {kind:"album",id,album_id:id,title:a?a.title:"",artist:artists.map(x=>x.name).join(", "),artists,cover:a?a.cover:""};
  }
  const info=state.selectedInfo||state.currentInfo;
  return info?{...plainTrack(info),id}:null;
}
function toggleInfoFavorite(spec) {
  const entry=infoActionSpec(spec);
  if(!entry)return;
  if(entry.kind==="album")toggleAlbumFavorite(entry); else toggleTrackFavorite(entry);
  renderInfo();
}
function toggleInfoAdd(spec) {
  const entry=infoActionSpec(spec);
  if(!entry)return;
  if(entry.kind==="album")toggleAlbumInQueue(entry); else toggleTrackInQueue(entry);
  renderInfo();
}
// 信息页专辑点击:跳到艺术家列表内打开该专辑(展开),而非加入播放列表
async function openAlbumInArtistList(albumId) {
  const info=state.selectedInfo||state.currentInfo;
  const artists=albumArtistsOf(info||{});
  const artistId=artists.length?artists[0].id:(info&&info.artist_id?String(info.artist_id):"");
  if(!artistId){showToast(t("requestFailed"));return;}
  showPanelTab("artist");
  await openArtistPage(artistId,false);
  const entries=artistEntries();
  const idx=entries.findIndex(e=>String(e.id)===String(albumId));
  if(idx>=0){
    const details=document.querySelector(`[data-artist-album="${idx}"]`);
    if(details){ details.open=true; loadArtistAlbumBox(details.querySelector(".playlist-album-head")); scrollArtistViewTo(details); }
  }
}
// 只滚动右侧艺术家视图内部定位专辑,避免 scrollIntoView 把整页拉起留下底部空缺
function scrollArtistViewTo(details) {
  const view=document.querySelector("#artistView");
  if(!view||!details)return;
  const vr=view.getBoundingClientRect(), er=details.getBoundingClientRect();
  const target=view.scrollTop+(er.top-vr.top)-(vr.height/2-er.height/2);
  view.scrollTo({top:Math.max(0,target),behavior:"smooth"});
}
function artistEntries() { return state.artistView?[...(state.artistView.albums||[]),...(state.artistView.singles||[])]:[]; }
function artistRow(entry,index) {
  const cover=imgSrc(entry.cover)?`<img class="preview-cover" src="${esc(imgSrc(entry.cover))}" alt="">`:`<span class="preview-cover preview-cover-placeholder"><i data-lucide="disc-3"></i></span>`;
  const heart=`<span class="queue-remove queue-fav icon-button${isFavorite("album",entry.id)?" fav-on":""}" data-artist-fav="${index}" title="${t("favorite")}"><i data-lucide="heart"></i></span>`;
  const add=addIcon(albumQueueState(entry),`data-artist-add="${index}"`);
  const tracks=entry._tracks?entry._tracks.map((track,i)=>`<button class="playlist-track-row" type="button" data-artist-track="${i}" data-album-index="${index}"><span class="track-number">${track.track_number||i+1}</span><span class="track-name">${trackTitleBadges(track.title,track.explicit,track.atmos,"strong")}${artistLink(track)}</span><span class="track-duration">${formatTime(track.duration)}</span>${addIcon(trackInQueue(track.id)?"full":"none",`data-artist-inner-add="${i}" data-album-index="${index}"`)}</button>`).join(""):`<div class="fav-album-loading">${t("loadingTracks")}</div>`;
  return `<details class="playlist-album artist-album${String(entry.id)===String(state.selectedTrackId)?" selected":""}" data-artist-album="${index}"><summary class="playlist-album-head preview-head">${cover}<span class="preview-title">${tScroll(entry.title,"strong")}${entry.year?`${tScroll(entry.year,"span")} `:""}${albumArtistLink(entry)||tScroll(entry.artist||"","span")}</span><span class="preview-count">${entry.track_count||""}</span>${heart}${add}</summary><div class="playlist-album-tracks">${tracks}</div></details>`;
}
function artistTrackRow(track,index) {
  const cover=imgSrc(track.cover)?`<img src="${esc(imgSrc(track.cover))}" alt="">`:`<span class="queue-cover-placeholder"><i data-lucide="music"></i></span>`;
  const heart=`<span class="queue-remove queue-fav icon-button${isTrackFavorited(track)?" fav-on":""}" data-artist-track-fav="${index}" title="${t(isTrackFavorited(track)?"unfavorite":"favorite")}"><i data-lucide="heart"></i></span>`;
  const add=addIcon(trackInQueue(track.id)?"full":"none",`data-artist-track-add="${index}"`);
  return `<button class="queue-item" type="button" data-artist-track-play="${index}">${cover}<span class="queue-copy">${trackTitleBadges(track.title,track.explicit,track.atmos,"strong")}${artistLink(track)}${track.album?tScroll(track.album,"span"):""}</span><span class="queue-duration">${formatTime(track.duration)}</span>${heart}${add}</button>`;
}
function renderArtistSearchResults(artists) { const panel=$("#artistSearchResults"); if(!panel)return; panel.innerHTML=artists.length?artists.map((artist,i)=>`<button class="player-result" type="button" data-artist-goto="${esc(String(artist.id))}">${imgSrc(artist.picture)?`<img src="${esc(imgSrc(artist.picture))}" alt="">`:`<span class="queue-cover-placeholder"><i data-lucide="user-round"></i></span>`}<span class="player-result-copy">${tScroll(artist.name,"strong")}</span></button>`).join(""):`<div class="player-empty">${esc(t("artistSearchNone"))}</div>`; panel.hidden=false; icon(); markOverflowTitles(); }
async function searchTidalArtists(query) { const id=++state.artistSearchId; try { const data=await api(`/api/player/search-artists?query=${encodeURIComponent(query)}`); if(id===state.artistSearchId)renderArtistSearchResults(data.artists||[]); } catch(error) { if(id===state.artistSearchId)renderArtistSearchResults([]); } }
function renderArtistList() { const data=state.artistView; if(!data||data.loading||data.error)return; const list=$("#artistList"); if(!list)return; const albums=data.albums||[], singles=data.singles||[], tracks=data.tracks||[]; const terms=state.artistFilter.query.trim().toLowerCase().split(/\s+/).filter(Boolean); if(state.artistFilter.section==="tracks"){const pairs=tracks.map((track,index)=>({track,index})).filter(({track})=>{ if(!terms.length)return true; const haystack=`${track.title} ${track.artist} ${track.album||""}`.toLowerCase(); return terms.every(term=>haystack.includes(term)); }); list.innerHTML=pairs.map(({track,index})=>artistTrackRow(track,index)).join("")||`<div class="player-empty"><i data-lucide="search-x"></i><span>${esc(t("noResults"))}</span></div>`; markOverflowTitles(); icon(); return; } const src=state.artistFilter.section==="albums"?albums:singles; const offset=state.artistFilter.section==="albums"?0:albums.length; const pairs=src.map((entry,i)=>({entry,index:i+offset})).filter(({entry})=>{ if(!terms.length)return true; const haystack=`${entry.title} ${entry.year||""}`.toLowerCase(); return terms.every(term=>haystack.includes(term)); }); list.innerHTML=pairs.map(({entry,index})=>artistRow(entry,index)).join("")||`<div class="player-empty"><i data-lucide="search-x"></i><span>${esc(t("noResults"))}</span></div>`; renderArtistSelection(); markOverflowTitles(); icon(); }
function renderArtistView() {
  const view=$("#artistView"); const data=state.artistView;
  // 搜索框始终显示(即使尚无艺术家),方便直接搜 Tidal 艺术家
  const searchHtml=`<div class="artist-search"><i data-lucide="search"></i><input id="artistSearch" type="search" autocomplete="off" placeholder="${esc(t("artistSearchPlaceholder"))}"><span class="search-clear icon-button" id="artistSearchClear" data-search-clear="artistSearch" hidden><i data-lucide="x"></i></span></div><div id="artistSearchResults" class="artist-search-results" hidden></div>`;
  if(!data){view.innerHTML=searchHtml+`<div class="player-empty"><i data-lucide="user-round"></i><span>${esc(t("artistEmpty"))}</span></div>`;icon();return;}
  if(data.loading){view.innerHTML=searchHtml+`<div class="player-empty"><i data-lucide="loader-circle" class="spin"></i><span>${esc(t("loadingArtist"))}</span></div>`;icon();return;}
  if(data.error){view.innerHTML=searchHtml+`<div class="player-empty"><i data-lucide="triangle-alert"></i><span>${esc(data.error)}</span></div>`;icon();return;}
  const albums=data.albums||[], singles=data.singles||[], tracks=data.tracks||[];
  view.innerHTML=`<div class="artist-hero">${data.picture?`<img src="${esc(imgSrc(data.picture))}" alt="" onerror="this.style.display='none'">`:`<span class="queue-cover-placeholder"><i data-lucide="user-round"></i></span>`}<h3>${esc(data.name)}</h3><button id="followButton" class="follow-button${isFollowing(data.id)?" following":""}" type="button" data-artist-id="${esc(String(data.id))}"><i data-lucide="${isFollowing(data.id)?"user-round-check":"user-round-plus"}"></i><span>${isFollowing(data.id)?t("following_"):t("follow")}</span></button></div>
  ${searchHtml}
  <div class="artist-filter">
    <button class="artist-chip${state.artistFilter.section==="albums"?" active":""}" type="button" data-artist-section="albums"><span>${esc(t("artistAlbums"))}</span><span>${albums.length}</span></button>
    <button class="artist-chip${state.artistFilter.section==="singles"?" active":""}" type="button" data-artist-section="singles"><span>${esc(t("artistSingles"))}</span><span>${singles.length}</span></button>
    <button class="artist-chip${state.artistFilter.section==="tracks"?" active":""}" type="button" data-artist-section="tracks"><span>${esc(t("artistTracks"))}</span><span>${tracks.length}</span></button>
  </div>
  <div id="artistList" class="artist-list"></div>`;
  icon(); renderArtistList();
}
function showPanelArtistError(message) { state.artistView={error:message}; renderArtistView(); }
async function openArtistPage(artistId,switchTab=true) {
  // 同一艺术家已在展示:仅在需要切换面板时切换,不重新请求也不重渲染(避免刷新闪动)
  const current=state.artistView;
  if(current&&!current.loading&&!current.error&&String(current.id)===String(artistId)){
    if(switchTab&&state.panelTab!=="artist")showPanelTab("artist");
    renderArtistSelection();
    return;
  }
  if(switchTab)showPanelTab("artist");
  state.artistView={loading:true}; state.artistFilter={section:"albums",query:""}; renderArtistView(); try { const data=await api(`/api/player/artist/${artistId}`); const dedupe=(list)=>{const seen=new Set();return (list||[]).filter(entry=>{const key=`${entry.title.toLowerCase()}|${entry.year||""}`;if(seen.has(key))return false;seen.add(key);return true;});};data.albums=dedupe(data.albums);data.singles=dedupe(data.singles);state.artistView=data; } catch(error) { state.artistView={error:error.message}; } renderArtistView(); renderArtistSelection(); }
async function addArtistAlbum(entry) { await addResource(`album/${entry.id}`); showToast(t("addedToQueue")); }
function showToast(message) { const toast=$("#toast"); toast.textContent=message; toast.classList.add("show"); clearTimeout(state.toastTimer); state.toastTimer=setTimeout(()=>toast.classList.remove("show"),2400); }
async function loadFavoriteAlbumTracks(entry) { if(entry._tracks)return entry._tracks; try { const data=await api("/api/player/resource",{method:"POST",body:JSON.stringify({resource:`album/${entry.id}`})}); entry._tracks=data.tracks; return entry._tracks; } catch(error) { showToast(error.message); return null; } }
async function appendFavoriteAlbum(entry) { const tracks=await loadFavoriteAlbumTracks(entry); if(!tracks)return; const known=new Set(state.queue.map(track=>String(track.id))); const excluded=entry._excluded||new Set(); const fresh=tracks.filter(track=>!known.has(String(track.id))&&!excluded.has(String(track.id))).map(track=>({...plainTrack(track),_sourceType:"album",_sourceKey:`album/${entry.id}`})); if(!fresh.length)return showToast(t("alreadyInQueue")); state.queue.push(...fresh); renderQueue(); showToast(t("addedToQueue")); if(state.current<0)playIndex(state.queue.length-fresh.length); }
function toggleAlbumInQueue(entry) { if(albumQueueState(entry)==="full"){const albumKey=`album/${entry.id}`;state.queue=state.queue.filter(item=>item._sourceKey!==albumKey);if(state.current>=state.queue.length)state.current=state.queue.length-1;renderQueue();}else appendFavoriteAlbum(entry); }
function insertAfterCurrent(track, sourceType="track", sourceKey="") { const item={...plainTrack(track),_sourceType:sourceType,_sourceKey:sourceKey||`track/${track.id}`}; if(state.current<0){state.queue.push(item);renderQueue();if(state.queue.length===1)playIndex(0);return;} state.queue.splice(state.current+1,0,item); renderQueue(); }
// 把曲目按 track 位序插回已存在的专辑组内(如 track1 回到首位);专辑组不在队列时退回 insertAfterCurrent
function insertInAlbumOrder(track, albumKey) {
  const item={...plainTrack(track),_sourceType:"album",_sourceKey:albumKey};
  const idxs=[];
  state.queue.forEach((t,i)=>{ if(t._sourceType==="album"&&t._sourceKey===albumKey) idxs.push(i); });
  if(!idxs.length){ insertAfterCurrent(track,"album",albumKey); return; }
  const tn=Number(track.track_number)||0;
  let insertAt=idxs[idxs.length-1]+1; // 默认插到组尾
  for(const i of idxs){
    const otherTn=Number(state.queue[i].track_number)||0;
    // 新曲 track_number 小于等于某已存在曲目时,插到它前面(保持升序)
    if(tn>0 && (otherTn===0 || tn<otherTn)){ insertAt=i; break; }
  }
  state.queue.splice(insertAt,0,item);
  if(state.current>=insertAt) state.current++;
  renderQueue();
}
// 通用添加:若该曲所属专辑组已在播放列表中,按 track 位序插回;否则按普通曲目插入
function addTrackBack(entry) {
  const albumKey=entry&&entry.album_id?`album/${entry.album_id}`:null;
  const groupExists=albumKey&&state.queue.some(t=>t._sourceType==="album"&&t._sourceKey===albumKey);
  if(groupExists) insertInAlbumOrder(entry,albumKey);
  else insertAfterCurrent(entry);
}
// 点击歌曲卡片空白区域:唯一作用 = 加入播放列表并立即播放(不在列表则插入,在则直接播放)
function addAndPlay(entry) {
  if(!entry)return;
  // 移动端:从抽屉点播后收起抽屉,露出播放器
  if(window.ATPCloseDrawers)window.ATPCloseDrawers();
  const id=String(entry.id);
  let index=state.queue.findIndex(item=>String(item.id)===id);
  if(index<0){
    addTrackBack(entry);
    index=state.queue.findIndex(item=>String(item.id)===id);
  }
  if(index>=0)playIndex(index);
}
function selectTrack(track) { state.selectedTrackId=track?String(track.id):null; if(track){state.selectedInfo={...plainTrack(track)};state.albumInfo=null;} renderQueue(); renderArtistSelection(); showPanelForSelection(track); }
function showPanelForSelection(track) { if(!track)return; if(track.artist_id)openArtistPage(track.artist_id,false); if(state.panelTab==="info")renderInfo(); }
async function openAlbumInfo(albumId,albumTitle="",albumArtist="",albumArtistId="") {
  showPanelTab("info");
  const view=$("#infoView"); view.innerHTML=`<div class="player-empty"><i data-lucide="loader-circle" class="spin"></i><span>${esc(t("loadingInfo"))}</span></div>`; icon();
  let kind="";
  try {
    const preview=await api("/api/preview",{method:"POST",body:JSON.stringify({urls:[`album/${albumId}`]})});
    const card=(preview.resources||[])[0]||{};
    kind=String(card.kind||"").toUpperCase();
    const tracks=card.items||[];
    const total=tracks.reduce((sum,t)=>{const p=String(t.duration||"0:00").split(":").map(Number);return sum+(p.length===3?p[0]*3600+p[1]*60+p[2]:p[0]*60+p[1]);},0);
    state.albumInfo={album_id:String(albumId),kind,title:card.title||albumTitle,artist:card.subtitle||albumArtist,cover:card.cover||"",duration:total,trackCount:tracks.length};
  } catch(error) { state.albumInfo={album_id:String(albumId),kind:"",title:albumTitle||error.message,artist:albumArtist,cover:"",duration:0,trackCount:0}; }
  renderInfo();
  addResource(`album/${albumId}`);
}
function renderArtistSelection() { document.querySelectorAll("[data-artist-album]").forEach(el=>el.classList.remove("selected")); if(!state.artistView)return; const items=artistEntries(); items.forEach((entry,i)=>{ if(String(entry.id)===String(state.selectedTrackId))document.querySelector(`[data-artist-album="${i}"]`)?.classList.add("selected"); }); }function toggleFavorite() { const track=state.queue[state.current]; if(track)toggleFavoriteEntry(plainTrack(track)); }
function updateFavoriteButton() { const track=state.queue[state.current]; const active=Boolean(track&&isTrackFavorited(track)); const button=$("#favoriteButton"); button.disabled=!track; button.classList.toggle("fav-active",active); button.dataset.title=active?"unfavorite":"favorite"; button.title=t(active?"unfavorite":"favorite"); button.setAttribute("aria-label",button.title); button.innerHTML=`<i data-lucide="heart"></i>`; icon(); }
function updateDownloadButton() { const button=$("#downloadButton"); button.disabled=state.current<0||state.downloadPending; }
function refreshTrackActions() { updateFavoriteButton(); updateDownloadButton(); syncArtistFavIcons(); }
// 收藏状态变化后原位同步艺术家页的心形(参与作品行 + 专辑卡),不整页重渲染
function syncArtistFavIcons() {
  if(!state.artistView||state.artistView.loading||state.artistView.error)return;
  const tracks=state.artistView.tracks||[];
  document.querySelectorAll("[data-artist-track-fav]").forEach(el=>{
    const track=tracks[Number(el.dataset.artistTrackFav)];
    if(track)el.classList.toggle("fav-on",isTrackFavorited(track));
  });
  const entries=artistEntries();
  document.querySelectorAll("[data-artist-fav]").forEach(el=>{
    const entry=entries[Number(el.dataset.artistFav)];
    if(entry)el.classList.toggle("fav-on",isFavorite("album",entry.id));
  });
}
function formatBytes(value) { value=Number(value); if(!Number.isFinite(value)||value<=0)return"0 B"; const units=["B","KB","MB","GB","TB"]; const index=Math.max(0,Math.min(Math.floor(Math.log(value)/Math.log(1024)),units.length-1)); return`${Math.max(1,Math.round(value/1024**index))} ${units[index]}`; }
function showSpeed(rate) { rate=Number(rate); if(!Number.isFinite(rate)||rate<0)rate=0; const dl=(window.ATPDownloads&&Number(window.ATPDownloads.speed))||0; const box=$("#playSpeed"); box.hidden=false; $("#playSpeedValue").textContent=`${formatBytes(rate+dl)}/s`; }
async function pollSpeed() {
  // v2 DRM 直连播放:服务端不追踪字节(session_id=None),改用客户端 feed 下载计数
  if (!state.speedSession && drmPlayback) {
    const now = performance.now(), dt = (now - (state._drmSpeedT || now)) / 1000;
    if (dt >= 0.9 && state._drmBytes != null) {
      const total = state._drmBytes;
      state.speedRate = Math.max(0, (total - (state._drmSpeedB || 0)) / dt);
      state._drmSpeedB = total; state._drmSpeedT = now;
    }
    showSpeed(state.speedRate); return;
  }
  if (!state.speedSession) { showSpeed(0); return; }
  try { const data=await api(`/api/player/speed/${state.speedSession}`); const now=performance.now(),dt=(now-state.speedTime)/1000; if(dt>=0.9){const total=Number(data&&data.bytes)||0;state.speedRate=Math.max(0,(total-state.speedBytes)/dt);state.speedBytes=total;state.speedTime=now;} showSpeed(state.speedRate); } catch(error) { state.speedSession=null; showSpeed(0); } }
// 播放器档位 → 下载接口档位:播放用大写 LOSSLESS/复合 Atmos 档,下载接口用 low/normal/high/max。
// 用 selectedQuality(用户选择/默认偏好,不被 resolve 实际档覆盖)推导;
// 若尚未选择则回退到 state.quality(如默认 HIGH)。
function downloadQualityOf(track) {
  const dlLowest = state.defaultLowest || localStorage.getItem("tiddl-default-lowest") === "true";
  if (dlLowest) return { quality: "low", atmos: "none" };
  const chosen = (state.selectedQuality && qualitySpecs[state.selectedQuality]) ? state.selectedQuality : (state.quality && qualitySpecs[state.quality] ? state.quality : (track.qualities && track.qualities.includes("LOSSLESS") ? "LOSSLESS" : "HIGH"));
  const { quality, atmos } = splitQuality(chosen);
  return { quality: { LOW: "low", HIGH: "normal", LOSSLESS: "high", HI_RES_LOSSLESS: "max" }[quality] || "high", atmos: atmos ? "allow" : "none" };
}
async function downloadCurrent() { const track=state.queue[state.current]; if(!track||state.downloadPending)return; state.downloadPending=true; updateDownloadButton(); try { const { quality: trackQuality, atmos: trackAtmos } = downloadQualityOf(track); await api("/api/downloads",{method:"POST",body:JSON.stringify({urls:[`track/${track.id}`],track_quality:trackQuality,atmos:trackAtmos,resource_metadata:[{title:track.title,subtitle:track.artist,cover:imgSrc(track.cover),type:"track"}]})}); showToast(t("downloadQueued")); } catch(error) { showToast(error.message); } finally { state.downloadPending=false; refreshTrackActions(); } }
function isResource(value) { return /^(?:https?:\/\/(?:listen\.)?tidal\.com\/)?(?:browse\/)?(?:(?:track|album)\/\d+|album\/\d+\/track\/\d+)(?:\?.*)?$/.test(value.trim()); }
async function addResource(resource) { $("#playerSearchResults").hidden=true; $("#searchSpinner").hidden=false; try { const data=await api("/api/player/resource",{method:"POST",body:JSON.stringify({resource})}); const known=new Set(state.queue.map(track=>String(track.id))); const path=resource.replace(/^https?:\/\/(?:listen\.)?tidal\.com\/(?:browse\/)?/,"").split("?")[0]; const trackMatch=path.match(/(?:^|\/)track\/(\d+)$/); const sourceType=trackMatch?"track":"album"; const sourceKey=trackMatch?`track/${trackMatch[1]}`:path; state.queue.push(...data.tracks.filter(track=>!known.has(String(track.id))).map(track=>({...plainTrack(track),_sourceType:sourceType,_sourceKey:sourceKey}))); renderQueue(); $("#playerSearch").value=""; if(state.current<0 && state.queue.length) playIndex(0); } catch(error) { showError(error.message); } finally { $("#searchSpinner").hidden=true; } }
function applyFavoriteFilter() { state.favFilter=$("#playerSearch").value.trim(); renderFavorites(); }
async function search() { if(state.libraryTab==="favorites")return applyFavoriteFilter(); const query=$("#playerSearch").value.trim(); if(query.length<2)return; if(isResource(query)){await addResource(query);return;} const id=++state.searchId; $("#searchSpinner").hidden=false; try { const data=await api(`/api/search?query=${encodeURIComponent(query)}`); if(id===state.searchId){ if(window.ATPTrace)window.ATPTrace("search.done",{query,count:(data.results||[]).length}); renderResults(data.results); } } catch(error){showError(error.message);} finally { if(id===state.searchId)$("#searchSpinner").hidden=true; } }
// ---- 播放状态行:API 信息(如 v2/v1/回退)与错误提示共用一行,互不覆盖 ----
let statusError = "", statusApi = "", statusApiPending = "";
function renderStatusLine() {
  const el = $("#playerError");
  if (window.ATPTrace) window.ATPTrace("status", { text: el.textContent, error: statusError, api: statusApi, tap: state.tapToPlay });
  if (statusError) { el.textContent = statusError; el.classList.remove("api-info"); }
  else if (statusApi) { el.textContent = statusApi; el.classList.add("api-info"); }
  else { el.textContent = ""; el.classList.remove("api-info"); }
}
// 带参数=显示错误(覆盖 API 信息);无参=清空错误(恢复显示 API 信息)
function showError(message) { if (message) { statusError = message; statusApi = ""; } else { statusError = ""; } renderStatusLine(); }
// 记录并显示 API 信息;若当前正显示"点击播放"提示(移动端自动播放被拦),则只记住待恢复信息,
// 不覆盖提示——待用户点击播放真正开始后由 play 事件恢复。
function showApiInfo(message) {
  statusError = "";
  statusApiPending = message || "";
  if (statusApi !== t("tapToPlay")) statusApi = statusApiPending;
  renderStatusLine();
}
// 播放被移动端自动播放策略拦截:显示"点击播放",并把真实 API 信息留作恢复。
function promptTapToPlay() {
  if (statusApi && statusApi !== t("tapToPlay")) statusApiPending = statusApi;
  statusApi = t("tapToPlay");
  renderStatusLine();
}
// ---- Atmos-only 曲目:浏览器 EME(Widevine) + 后端 license 代理,零带宽解密播放 ----
let drmPlayback = null;
function canPlayDrm() { return typeof MediaSource!=="undefined" && typeof navigator.requestMediaKeySystemAccess==="function"; }
// 浏览器能否通过 MSE 解码 FLAC-in-MP4(决定 v2 是否请求 FLAC/FLAC_HIRES)。
// Chrome/Edge 支持;Firefox 的 MP4 parser 对高采样率 FLAC 分片有 bug(append 失败),
// 且 Widevine CDM 对 FLAC 受保护音频支持不可靠 → 需降级 AAC-LC。
function flacMseSupported() {
  try { return typeof MediaSource!=="undefined" && MediaSource.isTypeSupported('audio/mp4;codecs="flac"'); } catch (_) { return false; }
}function cleanupDrm() {
  if (drmPlayback) {
    try { drmPlayback.onSeeked && audio.removeEventListener("seeked", drmPlayback.onSeeked); } catch(_) {}
    try { drmPlayback.session && drmPlayback.session.close(); } catch(_) {}
    try { drmPlayback.ms && drmPlayback.ms.endOfStream(); } catch(_) {}
    drmPlayback = null;
  }
  if (state._drmUrl) { try { URL.revokeObjectURL(state._drmUrl); } catch(_) {} state._drmUrl=null; }
  if (audio.src && audio.src.startsWith("blob:")) { audio.removeAttribute("src"); audio.load(); }
}
function base64ToArrayBuffer(b64) { const bin=atob(b64); const u8=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i); return u8.buffer; }
// 串行 append 一个 ArrayBuffer 到 SourceBuffer(等 updateend)
function appendOne(sb, buf) {
  return new Promise((resolve, reject) => {
    const onEnd = () => { sb.removeEventListener("updateend", onEnd); resolve(); };
    sb.addEventListener("updateend", onEnd);
    try { sb.appendBuffer(buf); } catch (e) { sb.removeEventListener("updateend", onEnd); reject(e); }
  });
}
// 给 Promise 加超时:超时后 reject(用于 playDrm 各 await,防止永久卡在"Opening stream...")
function withTimeout(promise, ms, label) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error((label || "timeout") + " timed out")), ms);
    promise.then((v) => { clearTimeout(timer); resolve(v); }, (e) => { clearTimeout(timer); reject(e); });
  });
}
// Atmos-only 曲目:Widevine EME 解密 + MSE 渐进播放(音频字节浏览器直连 CDN,零带宽;
// license 通过我们后端 /api/player/drm-license 用账号池转发,不暴露账号)
// 缓存复用 MediaKeys:手机端硬件 CDM 每次重建会话极易挂起(遥测卡在 createMediaKeys),
// 首次创建后复用,仅切歌新建 session/MSE。
let _cachedMediaKeys = null;
// 候选 Widevine 配置:不同浏览器/设备兼容性不同,逐个尝试并缓存首个成功的。
const DRM_CONFIGS = [
  { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4;codecs=\"mp4a.40.2\"" }] },
  { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4;codecs=\"flac\"" }] },
  { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4" }] },
  { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4;codecs=\"mp4a.40.2\"", robustness: "SW_SECURE_CRYPTO" }] },
  { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4;codecs=\"mp4a.40.2\"", robustness: "SW_SECURE_DECODE" }] },
];
async function requestWidevineAccess(mime) {
  // 先用精确 mime,不行再退化到 mp4-any,再试 robustness 变体
  const candidates = [
    { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: mime }] },
    { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: "audio/mp4" }] },
    { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: mime, robustness: "SW_SECURE_CRYPTO" }] },
    { initDataTypes: ["cenc"], audioCapabilities: [{ contentType: mime, robustness: "SW_SECURE_DECODE" }] },
  ];
  let lastErr = null;
  for (let i = 0; i < candidates.length; i++) {
    try {
      const access = await withTimeout(navigator.requestMediaKeySystemAccess("com.widevine.alpha", [candidates[i]]), 8000, "EME cfg" + i);
      if (window.ATPTrace) window.ATPTrace("eme.cfg", { i, ok: true, contentType: candidates[i].audioCapabilities[0].contentType, rb: candidates[i].audioCapabilities[0].robustness || "" });
      return access;
    } catch (e) {
      lastErr = e;
      if (window.ATPTrace) window.ATPTrace("eme.cfg", { i, ok: false, contentType: candidates[i].audioCapabilities[0].contentType, rb: candidates[i].audioCapabilities[0].robustness || "", msg: String(e && e.message || e) });
    }
  }
  throw lastErr || new Error("EME unsupported");
}
async function getMediaKeys(mime) {
  if (_cachedMediaKeys) return _cachedMediaKeys;
  const access = await requestWidevineAccess(mime);
  const keys = await withTimeout(access.createMediaKeys(), 15000, "createMediaKeys");
  _cachedMediaKeys = keys;
  return keys;
}
let _serverCertSet = false; // 服务证书已设置(手机 CDM 严格要求;桌面 CDM 自动处理)
// 简单 protobuf varint 解码
function _readVarint(u8, i) { let v = 0, shift = 0; while (i < u8.length) { const b = u8[i++]; v |= (b & 0x7f) << shift; if (!(b & 0x80)) return [v, i]; shift += 7; } return [v, i]; }
// Tidal 返回的证书是 SignedMessage(type=5) 包裹 SignedDrmCertificate,不能直接传给
// setServerCertificate(Shaka 证实 wrapped 响应会被 CDM 拒绝)。需解包提取内层证书。
function unwrapWidevineCert(u8) {
  // 外层 SignedMessage: field1(type)=5, field2(msg)=SignedDrmCertificate
  if (u8.length >= 2 && u8[0] === 0x08 && u8[1] === 0x05) {
    let i = 2;
    while (i < u8.length) {
      const tag = u8[i++]; const field = tag >> 3; const wire = tag & 7;
      if (wire === 2) {
        const [ln, ni] = _readVarint(u8, i); i = ni;
        const payload = u8.slice(i, i + ln);
        if (field === 2) return { cert: payload, wrapped: true, total: u8.length }; // 内层 SignedDrmCertificate
        i += ln;
      } else if (wire === 0) { const [, ni] = _readVarint(u8, i); i = ni; }
      else break;
    }
  }
  return { cert: u8, wrapped: false, total: u8.length };
}
// 手机 CDM 在未设置服务证书时,generateRequest 只产出 2 字节证书请求(08 04)而非 license challenge。
// 先把证书请求转发给后端 → Tidal /v2/widevine 返回服务证书 → 解包 → setServerCertificate → 再 generateRequest。
async function ensureServerCertificate(keys, accountId) {
  if (_serverCertSet || !keys || typeof keys.setServerCertificate !== "function") return;
  try {
    const resp = await withTimeout(fetch("/api/player/drm-license" + (accountId ? `?account_id=${encodeURIComponent(accountId)}` : ""), { method:"POST", headers:{ "Content-Type":"application/octet-stream" }, body: new Uint8Array([0x08, 0x04]) }), 20000, "cert request");
    if (!resp.ok) throw new Error(`cert HTTP ${resp.status}`);
    const raw = await resp.arrayBuffer();
    const u8 = new Uint8Array(raw);
    const { cert, wrapped } = unwrapWidevineCert(u8);
    if (!cert || cert.byteLength < 16) throw new Error("cert too short");
    await keys.setServerCertificate(cert);
    _serverCertSet = true;
    if (window.ATPTrace) window.ATPTrace("eme.cert", { ok: true, wrapped, rawLen: u8.byteLength, certLen: cert.byteLength, head: Array.from(cert.slice(0, 8)).map(b => b.toString(16).padStart(2, "0")).join(" ") });
  } catch (e) {
    if (window.ATPTrace) window.ATPTrace("eme.cert", { ok: false, msg: String(e && e.message || e) });
    // 证书失败不致命:桌面 CDM 无证书也能走,继续尝试 generateRequest
  }
}
let _drmGen = 0; // playDrm 代际计数:快速连点/切歌时旧 playDrm 检测到被取代即静默退出,避免竞态
async function playDrm(bundle) {
  const gen = ++_drmGen;
  cleanupDrm();
  if (!canPlayDrm()) throw new Error("This browser cannot play protected Atmos streams (Widevine/EME unavailable).");
  const mime = `${bundle.mime_type};codecs="${bundle.codec}"`;
  if (!MediaSource.isTypeSupported(mime)) throw new Error(`Unsupported media type: ${mime}`);
  const tpl = bundle.media_template || bundle.media_url;
  const count = Number(bundle.segment_count) || 1;
  // EME:首次创建 MediaKeys 并缓存复用;切歌不重建(手机硬件 CDM 重建会挂起)
  if(window.ATPTrace)window.ATPTrace("drm.stage",{s:"eme"}); const keys = await getMediaKeys(mime);
  if (gen !== _drmGen) throw new Error("superseded");
  if(window.ATPTrace)window.ATPTrace("drm.stage",{s:"setkeys"}); await withTimeout(audio.setMediaKeys(keys), 15000, "setMediaKeys");
  // 服务证书:手机 CDM 严格要求,未设置时 generateRequest 只产出 2 字节证书请求(08 04),
  // 导致 license challenge 缺失 → 后端 400。设置后 CDM 才能产出真正的 license 请求。
  await ensureServerCertificate(keys, bundle.account_id);
  if (gen !== _drmGen) throw new Error("superseded");
  const session = keys.createSession();
  // EME session 事件打点:捕获 CDM 是否产出 license 挑战、是否报错、key 状态变化
  const traceSess = (evt, extra) => { if (window.ATPTrace) window.ATPTrace("eme.session." + evt, extra || {}); };
  session.addEventListener("message", () => traceSess("message", { len: 0 }));
  session.addEventListener("error", (e) => traceSess("error", { code: e && e.errorCode, msg: String(e && e.message || e) }));
  session.addEventListener("keystatuseschange", () => {
    try { traceSess("keystatuses", session.keyStatuses ? Array.from(session.keyStatuses).map(([k, v]) => v) : []); } catch (_) {}
  });
  session.addEventListener("expiration", () => traceSess("expiration", { t: session.expiration }));
  // 先拿 license(否则加密样本无法解码)。注意:generateRequest 必须在本轮 EME 中执行,
  // 不能在 MSE 就绪/play() 之后才调用——手机 CDM 对已进入 media 流程的 session 会返回 2 字节错误。
  const licenseReady = new Promise((resolve, reject) => {
    const done = (fn) => (...a) => { session.removeEventListener("message", onMsg); session.removeEventListener("error", onErr); fn(...a); };
    const onMsg = async (e) => {
      const len = e.message ? e.message.byteLength : 0;
      let hex = "";
      try { if (len > 0 && len <= 32) hex = Array.from(new Uint8Array(e.message)).map((b) => b.toString(16).padStart(2, "0")).join(" "); } catch (_) {}
      traceSess("challenge", { len, hex });
      try {
        const resp = await withTimeout(fetch("/api/player/drm-license" + (bundle.account_id ? `?account_id=${encodeURIComponent(bundle.account_id)}` : ""), { method:"POST", headers:{ "Content-Type":"application/octet-stream" }, body: e.message }), 20000, "license fetch");
        const statusText = await resp.clone().text().catch(() => "");
        traceSess("license.http", { status: resp.status, detail: statusText.slice(0, 200) });
        if (!resp.ok) throw new Error(`license HTTP ${resp.status}`);
        const license = await resp.arrayBuffer();
        await session.update(license);
        done(resolve)();
      } catch (err) { done(reject)(err); }
    };
    const onErr = (err) => done(reject)(new Error("EME session error"));
    session.addEventListener("message", onMsg);
    session.addEventListener("error", onErr);
  });
  if(window.ATPTrace)window.ATPTrace("drm.stage",{s:"genreq",pssh: bundle.pssh ? bundle.pssh.slice(0,24) : ""}); await withTimeout(session.generateRequest("cenc", base64ToArrayBuffer(bundle.pssh)), 15000, "generateRequest");
  await withTimeout(licenseReady, 30000, "license"); if(window.ATPTrace)window.ATPTrace("drm.stage",{s:"licensed"});
  if (gen !== _drmGen) throw new Error("superseded");
  // license 就绪后再挂 MSE(标准 EME 流程,避免 CDM 受 media 状态干扰)
  const ms = new MediaSource();
  state._drmUrl = URL.createObjectURL(ms);
  audio.src = state._drmUrl;
  await withTimeout(new Promise((res, rej) => { ms.addEventListener("sourceopen", res, { once:true }); ms.addEventListener("error", () => rej(new Error("MediaSource error")), { once:true }); }), 10000, "sourceopen");
  if(window.ATPTrace)window.ATPTrace("drm.stage",{s:"mse",mime}); const sb = ms.addSourceBuffer(mime);
  drmPlayback = { ms, sb, session, keys };
  // 在 sourceopen + addSourceBuffer 之后、有数据前调用 play():
  // 移动端对空 MSE 过早 play() 会让元素停在 waiting,导致 sourceopen 永不触发(遥测卡点)。
  // 自动播放被拦截时由 tapToPlay 提示兜底。
  safePlay();
  // 拉 init + 前 4 段,立即开播(此后有 license,解密播放)
  if(window.ATPTrace)window.ATPTrace("drm.stage",{s:"init"}); const init = await (await withTimeout(fetch(bundle.init_url), 20000, "init fetch")).arrayBuffer();
  if (gen !== _drmGen) throw new Error("superseded");
  // 客户端网速统计:v2 DRM 直连不经过服务端,用 feed 下载字节数估算
  state._drmBytes = init.byteLength; state._drmSpeedB = init.byteLength; state._drmSpeedT = performance.now();
  await withTimeout(appendOne(sb, init), 10000, "append init");
  if (gen !== _drmGen) throw new Error("superseded");
  let nextSeg = 1;
  const BURST = 4;
  for (; nextSeg <= count && nextSeg <= BURST; nextSeg++) {
    const r = await withTimeout(fetch(tpl.replace("$Number$", String(nextSeg))), 20000, `segment ${nextSeg}`);
    if (!r.ok) throw new Error(`segment HTTP ${r.status}`);
    const buf = await r.arrayBuffer();
    state._drmBytes += buf.byteLength;
    await withTimeout(appendOne(sb, buf), 10000, `append seg ${nextSeg}`);
  }
  // 播放中按需追加剩余段(缓冲快耗尽时补拉)
  const segDur = bundle.duration_s && count ? bundle.duration_s / count : 6; // 每段秒数,用于 seek 定位
  let feedWake = null; // seek 时立即唤醒 feed,不等 500ms 轮询
  let feedAlive = true; // feed 是否仍在运行(seek 到未缓冲区时若已退出则重启)
  const feed = async () => {
    feedAlive = true;
    // 预取阈值:手机网络慢,FLAC 段下载耗时;阈值太小(8s)拉取追不上播放 → 51s 处缓冲耗尽卡死。
    // 保持至少 ~30s 前瞻缓冲,并用并行拉取补足。
    const PREFETCH_AHEAD = 30;
    // 熔断:连续拉取失败达阈值(如 CDN 拒绝/CORS 拦截)就停止 feed,避免无限重试刷遥测。
    // 仅「连续」失败才熔断——单段成功即清零(网络抖动恢复后能继续)。
    let consecutiveFails = 0;
    const MAX_CONSECUTIVE_FAILS = 8;
    try {
      while (drmPlayback && nextSeg <= count) {
        const end = sb.buffered.length ? sb.buffered.end(sb.buffered.length - 1) : 0;
        const ahead = end - audio.currentTime;
        if (ahead < PREFETCH_AHEAD) {
          // 并行拉取下一段(一次拉足够多,减少串行等待)
          const toFetch = [];
          let i = nextSeg;
          while (i <= count && i < nextSeg + 6) { toFetch.push(i); i++; }
          const results = await Promise.all(toFetch.map(async (seg) => {
            for (let attempt = 0; attempt < 3; attempt++) {
              try {
                const r = await withTimeout(fetch(tpl.replace("$Number$", String(seg))), 20000, `segment ${seg}`);
                if (r.ok) { const buf = await r.arrayBuffer(); state._drmBytes += buf.byteLength; return { seg, buf }; }
              } catch (_) {}
              await new Promise((res) => setTimeout(res, 400 * (attempt + 1)));
            }
            return { seg, buf: null };
          }));
          let roundFailed = 0;
          for (const item of results) {
            if (!drmPlayback) break;
            if (item.buf) {
              try {
                await withTimeout(appendOne(sb, item.buf), 10000, `append seg ${item.seg}`);
                nextSeg = Math.max(nextSeg, item.seg + 1);
                consecutiveFails = 0; // 有成功段 → 复位熔断计数
              } catch (e) { if(window.ATPTrace)window.ATPTrace("feed.appendfail",{seg:item.seg,msg:String(e&&e.message||e)}); }
            } else {
              roundFailed++;
              if(window.ATPTrace)window.ATPTrace("feed.fetchfail",{seg:item.seg});
            }
          }
          // 熔断:本轮有失败段就累计,连续失败超阈值停止拉流并报错(避免 CDN 拒绝时无限重试)。
          // 有成功段时已在上方复位计数;全部失败则整轮计入。
          if (roundFailed > 0) {
            consecutiveFails += roundFailed;
            if (consecutiveFails >= MAX_CONSECUTIVE_FAILS) {
              if(window.ATPTrace)window.ATPTrace("feed.stalled",{consecutiveFails, nextSeg});
              drmPlayback = false;
              showError(t("streamFailed"));
              try { audio.pause(); } catch(_) {}
              break;
            }
          }
          if (feedWake) { feedWake(); feedWake = null; }
        } else {
          // 缓冲充足时轮询等待;页面切后台后 Chrome 会节流定时器(~1次/分钟),
          // 导致缓冲耗尽卡死(Game of Love 2:15 卡顿根因)。监听 visibilitychange:
          // 回到前台立即唤醒,不等节流的 500ms 轮询。
          await new Promise((res) => {
            feedWake = res;
            const wakeOnVisible = () => {
              if (!document.hidden) { feedWake(); feedWake = null; }
            };
            document.addEventListener("visibilitychange", wakeOnVisible);
            setTimeout(() => {
              document.removeEventListener("visibilitychange", wakeOnVisible);
              res();
            }, 500);
          });
        }
      }
      try { if (drmPlayback && nextSeg > count) ms.endOfStream(); } catch(_) {}
    } finally { feedAlive = false; }
  };
  // seek 到未缓冲区域时:立即跳到目标段并唤醒 feed 拉取,而不是等 500ms 轮询(拖进度条慢的根因)
  const onSeeked = () => {
    if (!drmPlayback || !Number.isFinite(audio.currentTime)) return;
    const end = sb.buffered.length ? sb.buffered.end(sb.buffered.length - 1) : 0;
    if (audio.currentTime + 2 <= end) return; // 目标仍在缓冲内,无需处理
    const target = Math.min(count, Math.max(1, Math.floor(audio.currentTime / segDur) + 1));
    if (target > nextSeg) nextSeg = target;
    try { if (sb.buffered.length && audio.currentTime > 4) sb.remove(0, audio.currentTime - 2); } catch(_) {}
    if (feedWake) { feedWake(); feedWake = null; } // 立即拉取目标段
    else if (!feedAlive && nextSeg <= count) feed(); // feed 已退出(如缓冲拉满后),seek 后重启
  };
  audio.addEventListener("seeked", onSeeked);
  drmPlayback.onSeeked = onSeeked;
  if(window.ATPTrace)window.ATPTrace("drm.stage",{s:"feed"}); feed();
  safePlay();
  showError();
}

const qualitySpecs={LOW:{label:"96 kbps",tone:"white"},HIGH:{label:"320 kbps",tone:"green"},LOSSLESS:{label:"Lossless",tone:"gold"},HI_RES_LOSSLESS:{label:"Hi-Res",tone:"magenta"},LOSSLESS_ATMOS:{label:"Lossless · Atmos",tone:"crimson"},HI_RES_LOSSLESS_ATMOS:{label:"Hi-Res · Atmos",tone:"crimson"}};
// 菜单选项标签:静态 label + 真实码率(v2 format_bandwidths,无损也有如 FLAC≈900kbps)
function qualityMenuLabel(q) { const base=qualitySpecs[q]?qualitySpecs[q].label:String(q||""); const bw=state.formatBandwidths; if(!bw)return base; const fmt={LOSSLESS:"FLAC",HI_RES_LOSSLESS:"FLAC_HIRES",LOSSLESS_ATMOS:"FLAC",HI_RES_LOSSLESS_ATMOS:"FLAC_HIRES",HIGH:"AACLC",LOW:"HEAACV1"}[q]; if(!fmt||!bw[fmt])return base; const kbps=`${bw[fmt]} kbps`; return base.endsWith("kbps")?kbps:`${base} · ${kbps}`; }
// 复合档位拆分:把 "LOSSLESS_ATMOS" 还原成后端需要的 quality + allow_atmos
function splitQuality(q){ if(q==="LOSSLESS_ATMOS")return {quality:"LOSSLESS",atmos:true}; if(q==="HI_RES_LOSSLESS_ATMOS")return {quality:"HI_RES_LOSSLESS",atmos:true}; return {quality:q,atmos:false}; }
function joinQuality(quality, atmos){ return atmos ? `${quality}_ATMOS` : quality; }
function actualSpecText() { const info=state.currentInfo; if(!info)return ""; const parts=[]; if(info.bitrate)parts.push(`${info.bitrate} kbps`); return parts.join(" · "); }
function renderQualityControl() { const actual=state.actualQuality; const spec=actualSpecText(); const selSpec=qualitySpecs[state.quality]||{label:String(state.quality||""),tone:"default"}; const label=spec?(selSpec.label.endsWith("kbps")?spec:`${selSpec.label} · ${spec}`):selSpec.label; const selected=actual?.audioMode==="DOLBY_ATMOS"?{label:`Dolby Atmos${actual.transcoded?" (stereo)":""} · ${actual.codec||"immersive"}`,tone:"crimson"}:{label,tone:selSpec.tone}; const choices=state.availableQualities.filter(value=>qualitySpecs[value]); const locked=state.defaultHighest||state.defaultLowest; const disabled=state.current<0&&!locked; const lockTitle=locked?t(state.defaultLowest?"defaultLowestToast":"defaultHighestToast"):""; const menuOpen=!($("#qualityMenu")||{hidden:true}).hidden; $("#qualityControl").innerHTML=`<div class="spec-control"><button id="qualityButton" class="spec-tag spec-tone-${selected.tone}${locked?" locked":""}" type="button" ${disabled?"disabled":""} title="${esc(lockTitle)}"><span>${esc(selected.label)}</span><i data-lucide="${locked?"lock":"chevron-down"}"></i></button><div id="qualityMenu" class="spec-menu" ${menuOpen?"":"hidden"}>${choices.map(value=>`<button type="button" class="${value===state.quality?"selected":""}" data-quality-choice="${value}"><span>${esc(qualityMenuLabel(value))}</span>${value===state.quality?`<i data-lucide="check"></i>`:""}</button>`).join("")}</div></div>`; icon(); }
function chooseQuality(track) { if(state.defaultLowest)return state.availableQualities[0]||"LOW"; const pick=state.availableQualities.find(v=>v===state.quality); if(pick)return pick; const lossless=state.availableQualities.find(v=>v==="LOSSLESS"||v==="LOSSLESS_ATMOS"); return lossless||state.availableQualities[0]||"HIGH"; }
function updateQualityOptions(track) { if(state.availableQualities && state.availableQualities.length && state._menuCalibrated){ if(state.defaultLowest)state.quality=state.availableQualities[0]; else if(state.defaultHighest)state.quality=state.availableQualities.at(-1); else if(!state.availableQualities.includes(state.quality))state.quality=chooseQuality({qualities:state.availableQualities}); return renderQualityControl(); } state.availableQualities=[...(track.qualities||[])]; state.actualQuality=null; state._menuCalibrated=false; if(state.defaultLowest)state.quality=state.availableQualities[0]||"LOW";else if(state.defaultHighest)state.quality=state.availableQualities.at(-1);else if(!track.qualities.includes(state.quality))state.quality=chooseQuality(track); if(!state.selectedQuality||!state.availableQualities.includes(state.selectedQuality))state.selectedQuality=state.quality; renderQualityControl(); }
function showActualQuality(data) {
  // 用 resolve 返回的真实支持音质刷新菜单(搜索/预览数据可能只带 LOW/HIGH;
  // v2/v1 后端校准后的 available_qualities 优先——如 Atmos 版无 Hi-Res 会在这里隐藏)。
  const real = Array.isArray(data.available_qualities)
    ? data.available_qualities
    : (data && data.track && Array.isArray(data.track.qualities) ? data.track.qualities : null);
  const realFiltered = real ? real.filter((q) => qualitySpecs[q]) : null;
  if (realFiltered && realFiltered.length) {
    state.availableQualities = realFiltered;
    state._menuCalibrated = true; // 菜单已按 resolve 真实能力校准,updateQualityOptions 不再覆盖
    if (state.defaultLowest) state.quality = realFiltered[0];
    else if (state.defaultHighest) state.quality = realFiltered.at(-1);
    else if (!realFiltered.includes(state.quality)) state.quality = chooseQuality({ qualities: realFiltered });
  }
  if(data.transcoded){state.actualQuality={audioMode:"DOLBY_ATMOS",codec:data.codec,transcoded:true};} else if(data.audio_mode==="DOLBY_ATMOS"){state.actualQuality={audioMode:data.audio_mode,codec:data.codec};} else {state.actualQuality=null;state.quality=data.audio_mode==="DOLBY_ATMOS"?joinQuality(data.quality,true):data.quality;}
  // 保存每档真实码率(format→kbps),菜单选项据此显示实际码率(无损也有,如 FLAC≈900kbps)
  if (data && data.format_bandwidths) state.formatBandwidths = data.format_bandwidths;
  renderQualityControl(); }
function supportsPlayerStream(data) { if(data.transcoded)return true; if(data.audio_mode!=="DOLBY_ATMOS")return true; const codec={eac3:"ec-3",ac4:"ac-4"}[String(data.codec).toLowerCase()]||data.codec; return Boolean(audio.canPlayType(`${data.mime_type}; codecs="${codec}"`)); }
function parseLyrics(data) { if(!data)return[]; const lines=[]; for(const line of (data.subtitles||"").split(/\r?\n/)){ const match=line.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/); if(match)lines.push({time:Number(match[1])*60+Number(match[2]),text:match[3].trim()}); } return lines; }
function renderLyrics(data) { state.lyrics=parseLyrics(data); state.activeLyric=-1; const box=$("#lyrics"); box.scrollTop=0; box.dir=data?.rtl?"rtl":"ltr"; const linesHtml=state.lyrics.length?state.lyrics.map((line,index)=>`<span class="lyrics-line" data-lyric="${index}">${esc(line.text||" ")}</span>`).join(""):""; if(linesHtml)box.innerHTML=linesHtml; else box.textContent=data?.text||t("noLyrics"); renderCoverLyrics(data, linesHtml); }
function renderCoverLyrics(data, linesHtml) { const box=$("#coverLyrics"); box.dir=data?.rtl?"rtl":"ltr"; if(linesHtml)box.innerHTML=linesHtml; else box.textContent=data?.text||t("noLyrics"); if(state.coverLyrics)box.hidden=false; }
function applyArtBackdrop() { const shell=$(".player-shell"), cover=$("#nowCover"); const url=cover&&cover.src; if(url){shell.classList.add("art-backdrop");shell.style.setProperty("--backdrop",`url("${url}")`);}else{shell.classList.remove("art-backdrop");shell.style.removeProperty("--backdrop");} }
function setCoverLyricsMode(on) { const art=$("#nowArt"), box=$("#coverLyrics"), cover=$("#nowCover"); state.coverLyrics=on; art.classList.toggle("lyrics-mode",on); cover.classList.toggle("blurred",on); box.hidden=!on; $(".player-shell").classList.toggle("lyrics-open",on); }function applyCoverBrightness() { $(".player-shell").classList.toggle("cover-bright",Boolean(state.coverBright)); }
function updateNowCopy() { const track=state.queue[state.current]; const artistSpan=$("#nowArtistName"), albumSpan=$("#nowAlbumName"), sep=$("#nowArtist .copy-sep"); artistSpan.removeAttribute("data-artist-open");artistSpan.removeAttribute("data-artists"); if(!track){artistSpan.innerHTML=tScroll(t("nothingPlaying"),"span");albumSpan.textContent="";albumSpan.removeAttribute("data-album-info");sep.hidden=true;$("#nowArtist").classList.remove("artist-link");artistSpan.classList.remove("artist-link");albumSpan.classList.remove("album-link");return;} const artists=artistsOf(track); const label=artists.length?artists.map(a=>a.name).join(", "):String(track.artist||""); albumSpan.textContent=track.album; sep.hidden=false; if(artists.length){const attrs=`data-artist-link data-artist-open="${esc(artists[0].id)}"`+(artists.length>1?` data-artists="${esc(JSON.stringify(artists))}"`:"");artistSpan.innerHTML=tScroll(label,"span",attrs);}else{artistSpan.innerHTML=tScroll(label,"span");} albumSpan.setAttribute("data-album-info",String(track.album_id||"")); artistSpan.classList.toggle("artist-link",artists.length>0); albumSpan.classList.toggle("album-link",Boolean(track.album_id)); markOverflowTitles(); }
async function playIndex(index, cached=null) { if(!state.queue.length)return; if(index<0)index=state.queue.length-1; if(index>=state.queue.length)index=0; state.current=index; const track=state.queue[index], request=++state.resolving; let aacRetried=false; renderQueue(); $("#nowTitle").innerHTML=trackTitleBadges(esc(track.title), track.explicit, track.atmos, "span"); updateNowCopy(); $("#nowCover").src=imgSrc(track.cover); $("#coverPlaceholder").hidden=Boolean(imgSrc(track.cover)); setCoverLyricsMode(false); renderLyrics([]); state.coverBright=false; applyCoverBrightness(); $("#nowCover").onload=applyArtBackdrop; applyArtBackdrop(); refreshTrackActions(); updateQualityOptions(track); showError(t("loading")); if(window.ATPTrace)window.ATPTrace("play.start",{index, track_id:track.id, title:track.title, cached:!!cached, drm:canPlayDrm()&&!state.drmBroken, aacOnly:!flacMseSupported()}); let usedApi=""; try { let data=cached||(await api("/api/player/resolve",{method:"POST",body:JSON.stringify({track_id:track.id,...splitQuality(chooseQuality(track)),drm:canPlayDrm()&&!state.drmBroken,aac_only:!flacMseSupported(),no_images:state.noImages})})); if(request!==state.resolving)return; state.speedSession=null; state.speedBytes=0; state.speedTime=performance.now(); state.speedRate=0; state.currentInfo={...data.track,quality:data.quality,audio_mode:data.audio_mode,bit_depth:data.bit_depth,sample_rate:data.sample_rate,bitrate:data.bitrate,codec:data.codec}; state.selectedTrackId=null; state.selectedInfo=null; state.albumInfo=null; state.coverBright=Boolean(data.cover_bright); applyCoverBrightness(); showActualQuality(data); if(window.ATPTrace)window.ATPTrace("resolve.ok",{drm:!!data.drm,audio_mode:data.audio_mode,quality:data.quality,bitrate:data.bitrate,codec:data.codec,format:data.drm&&data.drm.format,has_url:!!(data.direct_url||data.stream_url),drmBroken:state.drmBroken});
  // v2 优先:后端在浏览器支持 EME(drm) 时返回 data.drm(AAC-LC DASH + Widevine,MSE 播放,seek 流畅)。
  // 普通曲目也走 v2;失败则锁存 drmBroken,本会话后续曲目直接走 v1(避免每首都反复 license 失败)。
  if (data.drm && canPlayDrm()) { if(window.ATPTrace)window.ATPTrace("v2.attempt",{drm:true});
    try {
      await playDrm(data.drm); if(window.ATPTrace)window.ATPTrace("v2.ok");
      renderLyrics(data.lyrics); showApiInfo(t("apiV2")); updateMediaSession(track); preloadNext(); return;
    } catch(drmError) {
      if ((drmError && drmError.message) === "superseded") { if(window.ATPTrace)window.ATPTrace("v2.superseded"); return; }
      if(window.ATPTrace)window.ATPTrace("v2.fail",{msg:(drmError&&drmError.message)||String(drmError)}); console.warn("v2 MSE playback failed:", drmError);
      cleanupDrm();
      // 只在 EME/CDM 层失败(设备确实不支持/配置不可用)时锁 drmBroken;
      // 音质切换、MSE append、超时等瞬时问题不锁,否则切换音质后本会话全走 v1。
      const emeOnlyFail = /EME|createMediaKeys|keySystem|setMediaKeys|setServerCertificate|license/i.test(String((drmError && drmError.message) || ""));
      if (emeOnlyFail) { state.drmBroken = true; localStorage.setItem("tiddl-player-drm-broken","true"); }
      // 浏览器无法解码 FLAC-in-MSE(Firefox MP4 parser bug / Widevine CDM 不支持 FLAC):
      // 用 aac_only 重新 resolve 一次(AAC-LC),成功则继续 v2;仍失败才回退 v1。
      // 正则含 Firefox 实际错误: "object not usable"(SourceBuffer 失效/audio error 3)、
      // "Operation is not supported"(EME 拒绝 HE-AAC)、decode/InvalidStateError。
      const flacFail = !emeOnlyFail && /Unsupported media type|isTypeSupported|SourceBuffer|append|flac|codec|usable|Operation is not supported|decode|InvalidStateError|MEDIA_ERR_DECODE/i.test(String((drmError && drmError.message) || ""));
      if (flacFail && !aacRetried) {
        aacRetried = true;
        if(window.ATPTrace)window.ATPTrace("v2.aac.retry",{msg:(drmError&&drmError.message)||String(drmError)});
        const retry = await api("/api/player/resolve",{method:"POST",body:JSON.stringify({track_id:track.id,...splitQuality(chooseQuality(track)),drm:true,aac_only:true,no_images:state.noImages})});
        if(request!==state.resolving)return;
        if (retry.drm && canPlayDrm()) {
          try {
            await playDrm(retry.drm); if(window.ATPTrace)window.ATPTrace("v2.aac.ok",{codec:retry.drm.codec});
            renderLyrics(retry.lyrics); showApiInfo(t("apiV2")); updateMediaSession(track); preloadNext(); return;
          } catch(retryErr) {
            if ((retryErr && retryErr.message) === "superseded") return;
            if(window.ATPTrace)window.ATPTrace("v2.aac.fail",{msg:(retryErr&&retryErr.message)||String(retryErr)});
            cleanupDrm();
            const retryEmeFail = /EME|createMediaKeys|keySystem|setMediaKeys|setServerCertificate|license/i.test(String((retryErr && retryErr.message) || ""));
            if (retryEmeFail) { state.drmBroken = true; localStorage.setItem("tiddl-player-drm-broken","true"); }
          }
        }
      }
      const v1=await api("/api/player/resolve",{method:"POST",body:JSON.stringify({track_id:track.id,...splitQuality(chooseQuality(track)),drm:false,no_images:state.noImages})});
      if(request!==state.resolving)return;
      data=v1;
      state.currentInfo={...data.track,quality:data.quality,audio_mode:data.audio_mode,bit_depth:data.bit_depth,sample_rate:data.sample_rate,bitrate:data.bitrate,codec:data.codec};
      showActualQuality(data);
      showApiInfo(t("apiFallbackV1"));
    }
  }
  if(!supportsPlayerStream(data))throw new Error(t("unsupportedAtmos"));
  // 记录本次流的直连/代理信息,供失败时回退到代理流(服务器端拉取,无跨域 Origin 限制)
  if(window.ATPTrace)window.ATPTrace("v1.attempt",{direct:!!data.direct_url,proxy:!!data.stream_url,transcoded:data.transcoded}); state.currentIsDirect = Boolean(data.direct_url);
  state.currentStreamUrl = data.stream_url || null;
  state.currentSessionId = data.session_id || null;
  cleanupDrm(); audio.src=data.direct_url||data.stream_url; if(data.direct_url)state.speedSession=null; else state.speedSession=data.session_id; renderLyrics(data.lyrics); safePlay(); if(!statusApi)showApiInfo(t("apiV1")); updateMediaSession(track); preloadNext(); } catch(error){ if(request===state.resolving)showError(error.message); } }
function safePlay() {
  const pending = audio.play();
  if (!pending || !pending.catch) return;
  pending.then(()=>{ if(window.ATPTrace)window.ATPTrace("play.resolved"); }).catch(()=>{}); pending.catch((err) => {
    // 移动端自动播放策略:用户在 EME/license/分段等 await 后点击播放,
    // 手势激活已过期导致 play() 被 Chrome 拒绝(NotAllowedError)。
    // 不再静默吞掉——提示"点击播放",用户再次点击播放按钮(新手势)即可恢复。
    if (err && err.name === "NotAllowedError") {
      state.tapToPlay = true;
      promptTapToPlay();
    }
  });
}function updateMediaSession(track) { if(!("mediaSession" in navigator))return; navigator.mediaSession.metadata=new MediaMetadata({title:track.title,artist:track.artist,album:track.album,artwork:imgSrc(track.cover)?[{src:track.cover,sizes:"640x640",type:"image/jpeg"}]:[]}); }
// ---- 无缝连播:预解析下一首,接近结尾/结束时直接复用缓存,跳过网络等待 ----
// Tidal 流 URL 签名约 1 小时有效,预加载缓存超过 PRELOAD_MAX_AGE 视为过期,丢弃重新解析
const PRELOAD_MAX_AGE = 5 * 60 * 1000;
function nextIndex() { if(state.repeat===2)return state.current; if(state.shuffle && state.queue.length>1){let next;do{next=Math.floor(Math.random()*state.queue.length)}while(next===state.current);return next;} if(state.current+1<state.queue.length||state.repeat===1)return state.current+1; return -1; }
function queueKey() { return state.queue.map(item=>item&&item.id).join(","); }
function preloadFresh() { return state.preload && state.preload.data && (Date.now() - (state.preload.ts||0)) < PRELOAD_MAX_AGE; }
async function preloadNext() {
  if(state.preloadPending)return;
  const next=nextIndex();
  if(next<0||next===state.current)return;
  const track=state.queue[next];
  if(!track)return;
  const qkey=queueKey();
  const q=chooseQuality(track);
  if(state.preload&&state.preload.qkey===qkey&&state.preload.index===next&&state.preload.quality===q&&preloadFresh())return;
  state.preloadPending=true;
  try {
    const data=await api("/api/player/resolve",{method:"POST",body:JSON.stringify({track_id:track.id,...splitQuality(q),drm:canPlayDrm()&&!state.drmBroken,aac_only:!flacMseSupported()})});
    state.preload={index:next,qkey,quality:q,data,ts:Date.now()};
  } catch(_) { state.preload=null; }
  finally { state.preloadPending=false; }
}
function nextTrack() {
  const next=nextIndex();
  if(next<0){audio.pause();return;}
  let cached=null;
  const q=next>=0&&state.queue[next]?chooseQuality(state.queue[next]):null;
  if(state.preload&&state.preload.qkey===queueKey()&&state.preload.index===next&&state.preload.quality===q&&preloadFresh()) cached=state.preload.data;
  playIndex(next,cached);
}
function updatePlayButton() { $("#play").innerHTML=`<i data-lucide="${audio.paused?"play":"pause"}"></i>`; $("#play").dataset.title=audio.paused?"play":"pause"; $("#play").title=t(audio.paused?"play":"pause"); icon(); }
function highlightLyrics() { if(!state.lyrics.length)return; let active=-1; for(let i=0;i<state.lyrics.length;i++){if(state.lyrics[i].time<=audio.currentTime)active=i;else break;} if(active===state.activeLyric)return; state.activeLyric=active; document.querySelectorAll(".lyrics-line").forEach((line,index)=>line.classList.toggle("active",index===active)); const line=document.querySelector(`[data-lyric="${active}"]`), box=$("#lyrics"), cbox=$("#coverLyrics"); if(cbox&&!cbox.hidden){const cline=cbox.querySelector(`[data-lyric="${active}"]`); if(cline){const cr=cline.getBoundingClientRect(),cb=cbox.getBoundingClientRect();cbox.scrollTo({top:cbox.scrollTop+cr.top-cb.top-(cbox.clientHeight-cline.offsetHeight)/2,behavior:"smooth"});}} if(line){const lineRect=line.getBoundingClientRect(),boxRect=box.getBoundingClientRect();box.scrollTo({top:box.scrollTop+lineRect.top-boxRect.top-(box.clientHeight-line.offsetHeight)/2,behavior:"smooth"});} }
$("#playerSearch").addEventListener("input",()=>{syncSearchClear();if(state.libraryTab==="favorites")return applyFavoriteFilter();if(state.libraryTab==="following"){state.followFilter=$("#playerSearch").value;renderFollowing();return;}clearTimeout(state.searchTimer);state.searchTimer=setTimeout(search,350)});
$("#playerSearch").addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();if(state.libraryTab==="favorites")return applyFavoriteFilter();if(state.libraryTab==="following"){state.followFilter=$("#playerSearch").value;renderFollowing();return;}clearTimeout(state.searchTimer);search();}});
// 自定义灰色 × :清空搜索输入(替代被禁用的原生 search 取消按钮)
$("#searchClear").addEventListener("click",()=>{state.searchTimer&&clearTimeout(state.searchTimer);$("#playerSearch").value="";$("#searchClear").hidden=true;$("#playerSearchResults").hidden=true;if(state.libraryTab==="favorites")renderFavorites();else if(state.libraryTab==="following")renderFollowing();$("#playerSearch").focus();});
$("#playerSearchResults").addEventListener("click",event=>{const fav=event.target.closest("[data-result-fav]");if(fav){event.stopPropagation();toggleResultFavorite(fav);return;}const result=event.target.closest("[data-resource]");if(result)addSearchResult(result.dataset.resource);});
// 搜索结果:track 加入播放列表并立即播放;album 保持加入列表(不自动播放)
async function addSearchResult(resource) {
  const trackMatch=String(resource).match(/(?:^|\/)track\/(\d+)$/);
  if(!trackMatch)return addResource(resource);
  if(window.ATPCloseDrawers)window.ATPCloseDrawers(); // 移动端:点播后收起抽屉
  await addResource(resource);
  const id=trackMatch[1];
  const index=state.queue.findIndex(item=>String(item.id)===id);
  if(index>=0)playIndex(index);
}
async function toggleResultFavorite(span) { const [kind,id]=span.dataset.resultFav.split(":"); const existing=state.favorites.findIndex(entry=>entry.kind===kind&&String(entry.id)===String(id)); if(existing>=0){const fav=state.favorites[existing]; if(fav._pendingRemove)delete fav._pendingRemove; else fav._pendingRemove=true; saveFavorites(); span.classList.toggle("fav-on",!fav._pendingRemove); renderQueue(); renderFavorites(); refreshTrackActions(); return; } if(kind==="album") { const card=span.closest("[data-resource]"); const title=(card.querySelector(".player-result-copy strong")||{}).textContent||""; const artists=artistsOf(card); const cover=card.querySelector("img")?card.querySelector("img").src:""; addAlbumFavorite({kind:"album",id:String(id),album_id:String(id),title,artist:artists.map(a=>a.name).join(", "),artists,cover}); } else { try { const data=await api("/api/player/resource",{method:"POST",body:JSON.stringify({resource:`track/${id}`})}); const track=plainTrack(data.tracks[0]); if(isAlbumCovered(track))return showToast(t("favViaAlbum")); state.favorites.push(track); } catch(error) { return showToast(error.message); } } saveFavorites(); span.classList.add("fav-on"); renderQueue(); renderFavorites(); refreshTrackActions(); }
document.addEventListener("click",event=>{
  const link=event.target.closest("[data-info-track],[data-artist-open],[data-album-info]");
  if(!link)return;
  event.stopPropagation();event.preventDefault();
  if(link.dataset.infoTrack){const t=state.queue.find(x=>String(x.id)===link.dataset.infoTrack);if(t)selectTrack(t);else{state.selectedTrackId=link.dataset.infoTrack;state.selectedInfo={id:link.dataset.infoTrack};}if(state.panelTab==="info")renderInfo();return;}
  if(link.dataset.artistOpen){
    if(link.dataset.artists){
      const artists=JSON.parse(link.dataset.artists);
      if(artists.length>1){showArtistChooser(link,artists);return;}
    }
    openArtistPage(link.dataset.artistOpen);return;
  }
  if(link.dataset.albumInfo){openAlbumInfo(link.dataset.albumInfo,link.dataset.albumTitle||"",link.dataset.albumArtist||"",link.dataset.albumArtistId||"");return;}
},true);
$("#playerQueue").addEventListener("click",event=>{const qfTrack=event.target.closest("[data-fav-track]");if(qfTrack){event.stopPropagation();event.preventDefault();toggleQueueTrackFavorite(Number(qfTrack.dataset.favTrack));return;}const qfAlbum=event.target.closest("[data-fav-album-id]");if(qfAlbum){event.stopPropagation();event.preventDefault();toggleQueueAlbumFavorite(qfAlbum.dataset.favAlbumId);return;}const removeGroup=event.target.closest("[data-remove-group]");if(removeGroup){event.preventDefault();event.stopPropagation();const key=decodeURIComponent(removeGroup.dataset.removeGroup);const currentTrack=state.queue[state.current];state.queue=state.queue.filter(track=>track._sourceKey!==key);state.openAlbums.delete(key);state.current=currentTrack?state.queue.findIndex(track=>track.id===currentTrack.id):-1;if(state.current<0&&currentTrack){audio.pause();cleanupDrm();audio.removeAttribute("src");}renderQueue();renderQualityControl();refreshTrackActions();return;}const remove=event.target.closest("[data-remove]");if(remove){event.stopPropagation();const index=Number(remove.dataset.remove);state.queue.splice(index,1);if(index<state.current)state.current--;else if(index===state.current){audio.pause();cleanupDrm();audio.removeAttribute("src");state.current=-1;}renderQueue();renderQualityControl();refreshTrackActions();return;}const row=event.target.closest("[data-play]");if(row){const index=Number(row.dataset.play);const track=state.queue[index];if(track)addAndPlay(track);return;}});
$("#playerQueue").addEventListener("toggle",event=>{const album=event.target.closest("[data-album-key]");if(!album)return;const key=decodeURIComponent(album.dataset.albumKey);album.open?state.openAlbums.add(key):state.openAlbums.delete(key);},true);
$("#clearQueue").addEventListener("click",()=>{
  // 垃圾桶图标同时承担"清除搜索输入"功能(原生 × 已隐藏)
  $("#playerSearch").value=""; $("#playerSearchResults").hidden=true;
  if(state.libraryTab==="favorites")renderFavorites();
  else if(state.libraryTab==="following")renderFollowing();
  else { audio.pause(); cleanupDrm(); audio.removeAttribute("src"); state.queue=[]; state.current=-1; state.openAlbums.clear(); renderQueue(); renderQualityControl(); refreshTrackActions(); }
});
$(".queue-head").addEventListener("click",event=>{const tab=event.target.closest("[data-library-tab]");if(tab)showTab(tab.dataset.libraryTab);});
function favInnerTrack(el) {
  // 收藏专辑下拉行:曲目在 favorites[i]._tracks;艺术家专辑下拉行:曲目在 artistEntries()[albumIndex]._tracks
  const favBox=el.closest("[data-fav-album-tracks]");
  const artistBox=el.closest("[data-album-index]");
  const entry=favBox?state.favorites[Number(favBox.dataset.favAlbumTracks)]:artistEntries()[Number(artistBox?.dataset.albumIndex)];
  const row=el.closest("[data-fav-inner-row],[data-artist-track]");
  const index=el.dataset.innerAdd??el.dataset.artistInnerAdd??row?.dataset.favInnerRow??row?.dataset.artistTrack;
  return entry&&entry._tracks?entry._tracks[Number(index)]:null;
}
// 收藏夹单一委托监听:summary 内的可操作元素用 preventDefault 阻止 <details> 展开/折叠
function toggleInnerFavorite(entry, track) {
  if(!entry||!track)return;
  entry._excluded??=new Set();
  const id=String(track.id);
  if(entry._excluded.has(id))entry._excluded.delete(id); else entry._excluded.add(id);
  saveFavorites(); renderFavorites(); renderQueue(); refreshTrackActions();
}
function removeFavoriteAt(index) {
  if(index<0||index>=state.favorites.length)return;
  const fav=state.favorites[index];
  // 软删除:取消收藏先打标记不立即消失,可点回;离开收藏夹页时 flushPendingRemoves 清理
  if(fav._pendingRemove) delete fav._pendingRemove; else fav._pendingRemove=true;
  saveFavorites(); renderQueue(); renderFavorites(); refreshTrackActions();
}
function toggleTrackInQueue(entry) {
  if(state.queue.some(item=>String(item.id)===String(entry.id))){
    const index=state.queue.findIndex(item=>String(item.id)===String(entry.id));
    if(index<0)return; state.queue.splice(index,1);
    if(state.current>=state.queue.length)state.current=state.queue.length-1;
    renderQueue();
  } else addTrackBack(entry);
}
function toggleInnerInQueue(el) {
  const track=favInnerTrack(el); if(!track)return;
  const box=el.closest("[data-fav-album-tracks]");
  const owner=box&&state.favorites[Number(box.dataset.favAlbumTracks)];
  const excluded=Boolean(owner&&owner._excluded&&owner._excluded.has(String(track.id)));
  if(el.dataset.addState==="full"&&!excluded){
    // 对勾 = 从播放列表撤出该曲(可能使专辑头对勾变黄/加号)
    const index=state.queue.findIndex(item=>String(item.id)===String(track.id));
    if(index<0)return; state.queue.splice(index,1);
    if(state.current>=state.queue.length)state.current=state.queue.length-1;
    renderQueue(); return;
  }
  if(excluded){owner._excluded.delete(String(track.id));saveFavorites();}
  if(state.queue.some(item=>String(item.id)===String(track.id)))return showToast(t("alreadyInQueue"));
  // 按 track 位序插回所属专辑分组(避免重加后落在专辑外或打乱位序)
  insertInAlbumOrder(track,`album/${owner?owner.id:""}`);
}
$("#playerFavorites").addEventListener("click",event=>{
  const el=event.target.closest("[data-remove-fav],[data-album-fav-add],[data-inner-fav],[data-inner-add],[data-fav-inner-row],[data-fav-add-btn],[data-fav-play]");
  if(!el)return;
  if(el.closest("summary"))event.preventDefault();
  event.stopPropagation();
  if(el.hasAttribute("data-remove-fav")){removeFavoriteAt(Number(el.dataset.removeFav));return;}
  if(el.hasAttribute("data-album-fav-add")){const entry=state.favorites[Number(el.dataset.albumFavAdd)];if(entry)toggleAlbumInQueue(entry);return;}
  if(el.hasAttribute("data-inner-fav")){const box=el.closest("[data-fav-album-tracks]");const entry=box&&state.favorites[Number(box.dataset.favAlbumTracks)];toggleInnerFavorite(entry,favInnerTrack(el));return;}
  if(el.hasAttribute("data-inner-add")){toggleInnerInQueue(el);return;}
  if(el.hasAttribute("data-fav-inner-row")){const track=favInnerTrack(el);if(track)addAndPlay(track);return;}
  if(el.hasAttribute("data-fav-add-btn")){const entry=state.favorites[Number(el.dataset.favAddBtn)];if(entry)toggleTrackInQueue(entry);return;}
  if(el.hasAttribute("data-fav-play")){const entry=state.favorites[Number(el.dataset.favPlay)];if(entry)addAndPlay(entry);}
});
// 信息页:封面右侧爱心/加号 + 专辑点击跳艺术家列表
$("#infoView").addEventListener("click",event=>{
  const fav=event.target.closest("[data-info-fav]");
  if(fav){event.stopPropagation();event.preventDefault();toggleInfoFavorite(fav.dataset.infoFav);return;}
  const add=event.target.closest("[data-info-add]");
  if(add){event.stopPropagation();event.preventDefault();toggleInfoAdd(add.dataset.infoAdd);return;}
  const album=event.target.closest("[data-info-album-open]");
  if(album){event.stopPropagation();event.preventDefault();openAlbumInArtistList(album.dataset.infoAlbumOpen);return;}
});
$("#playerFavorites").addEventListener("toggle",event=>{
  const details=event.target.closest("[data-fav-card]");
  if(!details)return;
  const entry=state.favorites[Number(details.dataset.favCard)];
  if(entry)details.open?state.openFavAlbums.add(entry.id):state.openFavAlbums.delete(entry.id);
  if(!details.open)return;
  if(!entry)return;
  const box=details.querySelector("[data-fav-album-tracks]");
  const fill=()=>{box.innerHTML=entry._tracks.map((track,i)=>innerFavTrack(track,i,entry)).join("");icon();syncAddedIcons();};
  if(entry._tracks){fill();return;}
  loadFavoriteAlbumTracks(entry).then(tracks=>{ if(tracks)fill(); });
},true);
$("#nowArt").addEventListener("click",()=>{const track=state.queue[state.current];if(!track)return;setCoverLyricsMode(!state.coverLyrics);});
$("#favoriteButton").addEventListener("click",toggleFavorite);
$("#downloadButton").addEventListener("click",downloadCurrent);
$(".lyrics-tabs").addEventListener("click",event=>{const tab=event.target.closest("[data-panel-tab]");if(tab)showPanelTab(tab.dataset.panelTab);});
$("#playerFollowing").addEventListener("click",event=>{
  const remove=event.target.closest("[data-follow-remove]");
  if(remove){event.stopPropagation();state.follows.splice(Number(remove.dataset.followRemove),1);saveFollows();renderFollowing();renderFollowButton();return;}
  const row=event.target.closest("[data-follow-open]");
  if(row){const artist=state.follows[Number(row.dataset.followOpen)];if(artist&&artist.id&&artist.id!=="undefined")openArtistPage(artist.id);else showToast(t("requestFailed"));}
});
// 艺术家视图单一委托监听:summary 内的可操作元素用 preventDefault 阻止 <details> 展开/折叠
function artistToggleInner(el) {
  const album=artistEntries()[Number(el.dataset.albumIndex)];
  const track=album&&album._tracks&&album._tracks[Number(el.dataset.artistInnerAdd)];
  if(!track)return;
  if(trackInQueue(track.id)){
    const index=state.queue.findIndex(item=>String(item.id)===String(track.id));
    if(index>=0){state.queue.splice(index,1);if(state.current>=state.queue.length)state.current=state.queue.length-1;}
  } else insertInAlbumOrder(track,`album/${album.id}`);
  renderQueue();
}
function loadArtistAlbumBox(head) {
  const details=head.closest("[data-artist-album]");
  const entry=artistEntries()[Number(details.dataset.artistAlbum)];
  if(!entry||entry._tracks)return;
  const box=details.querySelector(".playlist-album-tracks");
  loadFavoriteAlbumTracks(entry).then(tracks=>{
    if(tracks){
      box.innerHTML=tracks.map((track,i)=>`<button class="playlist-track-row" type="button" data-artist-track="${i}" data-album-index="${Number(details.dataset.artistAlbum)}"><span class="track-number">${track.track_number||i+1}</span><span class="track-name">${trackTitleBadges(track.title,track.explicit,track.atmos,"strong")}${artistLink(track)}</span><span class="track-duration">${formatTime(track.duration)}</span>${addIcon(trackInQueue(track.id)?"full":"none",`data-artist-inner-add="${i}" data-album-index="${Number(details.dataset.artistAlbum)}"`)}</button>`).join("");
      icon();markOverflowTitles();
    }
  });
}
$("#artistView").addEventListener("click",event=>{
  const el=event.target.closest("[data-artist-goto],#followButton,[data-artist-section],[data-artist-add],[data-artist-fav],[data-artist-inner-add],[data-artist-track],[data-artist-track-play],[data-artist-track-fav],[data-artist-track-add],summary.playlist-album-head");
  if(!el)return;
  if(el.closest("summary")&&!el.matches("summary.playlist-album-head"))event.preventDefault();
  event.stopPropagation();
  if(el.hasAttribute("data-artist-goto")){openArtistPage(el.getAttribute("data-artist-goto"));const panel=$("#artistSearchResults");if(panel)panel.hidden=true;const input=$("#artistSearch");if(input)input.value="";return;}
  if(el.id==="followButton"){toggleFollowArtist(el.dataset.artistId,state.artistView&&state.artistView.name,state.artistView&&state.artistView.picture);return;}
  if(el.hasAttribute("data-artist-section")){state.artistFilter.section=el.dataset.artistSection;renderArtistView();return;}
  if(el.hasAttribute("data-artist-track-play")){const track=(state.artistView.tracks||[])[Number(el.dataset.artistTrackPlay)];if(track)addAndPlay(track);return;}
  if(el.hasAttribute("data-artist-track-fav")){const track=(state.artistView.tracks||[])[Number(el.dataset.artistTrackFav)];if(track){toggleTrackFavorite(plainTrack(track));el.classList.toggle("fav-on");renderArtistList();}return;}
  if(el.hasAttribute("data-artist-track-add")){const track=(state.artistView.tracks||[])[Number(el.dataset.artistTrackAdd)];if(track){toggleTrackInQueue(plainTrack(track));renderArtistList();}return;}
  if(el.hasAttribute("data-artist-add")){const entry=artistEntries()[Number(el.dataset.artistAdd)];if(entry)addArtistAlbum(entry);return;}
  if(el.hasAttribute("data-artist-fav")){const entry=artistEntries()[Number(el.dataset.artistFav)];if(entry){const artists=artistsOf(entry);toggleAlbumFavorite({kind:"album",id:String(entry.id),title:entry.title,artist:artists.map(a=>a.name).join(", "),artists,cover:entry.cover,album_id:String(entry.id),artist_id:artists[0]?artists[0].id:""});el.classList.toggle("fav-on");}return;}
  if(el.hasAttribute("data-artist-inner-add")){artistToggleInner(el);return;}
  if(el.hasAttribute("data-artist-track")){const album=artistEntries()[Number(el.dataset.albumIndex)];const track=album&&album._tracks&&album._tracks[Number(el.dataset.artistTrack)];if(track)addAndPlay(track);return;}
  if(el.matches("summary.playlist-album-head")){loadArtistAlbumBox(el);return;}
});
$("#artistView").addEventListener("input",event=>{
  if(event.target.id!=="artistSearch")return;
  const query=event.target.value.trim();
  const clear=$("#artistSearchClear"); if(clear)clear.hidden=!query;
  clearTimeout(state.artistSearchTimer);
  if(query.length<2){const panel=$("#artistSearchResults");if(panel)panel.hidden=true;return;}
  state.artistSearchTimer=setTimeout(()=>searchTidalArtists(query),350);
});
// 艺术家搜索:自定义灰色 × 清空输入
$("#artistView").addEventListener("click",event=>{
  const clear=event.target.closest("#artistSearchClear");
  if(!clear)return;
  event.stopPropagation(); event.preventDefault();
  const input=$("#artistSearch"); if(input)input.value="";
  clear.hidden=true;
  const panel=$("#artistSearchResults"); if(panel)panel.hidden=true;
  if(input)input.focus();
});
$("#play").addEventListener("click",()=>{if(state.current<0)return playIndex(0);audio.paused?safePlay():audio.pause();});
$("#previous").addEventListener("click",()=>audio.currentTime>4?audio.currentTime=0:playIndex(state.current-1)); $("#next").addEventListener("click",nextTrack);
$("#shuffle").addEventListener("click",()=>{state.shuffle=!state.shuffle;$("#shuffle").classList.toggle("active",state.shuffle);saveQueueSession();});
$("#repeat").addEventListener("click",()=>{state.repeat=(state.repeat+1)%3;renderRepeatIcon();saveQueueSession();});
function renderRepeatIcon() { const button=$("#repeat"); button.classList.toggle("active",state.repeat>0); button.classList.toggle("single",state.repeat===2); if(state.repeat===2){ button.innerHTML=`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 2l4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="M21 13v1a4 4 0 0 1-4 4h-0.5"/><path d="M9.5 18H3"/><path d="M7 22l-4-4 4-4"/><text x="13" y="18" text-anchor="middle" dominant-baseline="central" font-size="11" font-weight="700" fill="currentColor" stroke="none" font-family="inherit">1</text></svg>`; } else { button.innerHTML=`<i data-lucide="repeat"></i>`; } icon(); }
$("#qualityControl").addEventListener("click",event=>{if(state.defaultHighest||state.defaultLowest){if(event.target.closest("#qualityButton")||event.target.closest("[data-quality-choice]"))showToast(t(state.defaultHighest?"defaultHighestToast":"defaultLowestToast"));return;}const choice=event.target.closest("[data-quality-choice]");if(choice){state.quality=choice.dataset.qualityChoice;state.selectedQuality=state.quality;state.actualQuality=null;renderQualityControl();if(state.current>=0)playIndex(state.current);return;}if(event.target.closest("#qualityButton")){const menu=$("#qualityMenu");menu.hidden=!menu.hidden;}});
$("#playerSettingsButton").addEventListener("click",()=>$("#playerSettingsDialog").showModal());
$("[data-close-settings]").addEventListener("click",()=>$("#playerSettingsDialog").close());
function updatePlayerSettings(){
  const highest=$("#playerDefaultHighest").checked;
  const lowest=$("#playerDefaultLowest").checked;
  state.defaultHighest=highest; state.defaultLowest=lowest;
  localStorage.setItem("tiddl-player-default-highest",String(highest));
  localStorage.setItem("tiddl-player-default-lowest",String(lowest));
  const noImages=$("#playerNoImages").checked;
  state.noImages=noImages;
  localStorage.setItem("tiddl-player-no-images",String(noImages));
  applyNoImages();
  if(state.current>=0){audio.pause();playIndex(state.current);}else renderQualityControl();
}
function applyNoImages(){ document.body.classList.toggle("no-images",Boolean(state.noImages)); }
// 最高/最低音质互斥:勾选一个时自动取消另一个,不可能同时开启
$("#playerDefaultHighest").addEventListener("change",()=>{ if($("#playerDefaultHighest").checked) $("#playerDefaultLowest").checked=false; updatePlayerSettings(); });
$("#playerDefaultLowest").addEventListener("change",()=>{ if($("#playerDefaultLowest").checked) $("#playerDefaultHighest").checked=false; updatePlayerSettings(); });
$("#playerNoImages").addEventListener("change",updatePlayerSettings);
$("#volume").addEventListener("input",event=>{audio.volume=Number(event.target.value);audio.muted=false;paintRange(event.target);}); $("#mute").addEventListener("click",()=>{audio.muted=!audio.muted;$("#mute").innerHTML=`<i data-lucide="${audio.muted?"volume-x":"volume-2"}"></i>`;icon();});
// seek 节流:拖动时只更新滑块 UI,真正 seek 放到松开(change/pointerup)时执行一次,
// 避免拖动中每帧触发 currentTime 导致反复中断/重拉(卡顿与重播的根因之一)。
let scrubbing = false;
const seekEl = $("#seek");
seekEl.addEventListener("pointerdown", () => { scrubbing = true; });
seekEl.addEventListener("input", (e) => { scrubbing = true; paintRange(e.target); });
seekEl.addEventListener("change", (e) => {
  scrubbing = false;
  if (Number.isFinite(audio.duration)) audio.currentTime = audio.duration * Number(e.target.value) / 1000;
  paintRange(e.target);
});
seekEl.addEventListener("pointerup", () => { scrubbing = false; if (Number.isFinite(audio.duration)) audio.currentTime = audio.duration * Number(seekEl.value) / 1000; });
audio.addEventListener("timeupdate",()=>{$("#elapsed").textContent=formatTime(audio.currentTime);$("#duration").textContent=formatTime(audio.duration);if(Number.isFinite(audio.duration)){if(!scrubbing){$("#seek").value=audio.currentTime/audio.duration*1000;paintRange($("#seek"));}if(audio.duration-audio.currentTime<10)preloadNext();}highlightLyrics();}); audio.addEventListener("play",()=>{updatePlayButton();state.streamRetries=0;if(state.tapToPlay){state.tapToPlay=false;statusApi=statusApiPending||"";statusApiPending="";renderStatusLine();}showError();spectrumSetPaused(false);});audio.addEventListener("pause",()=>{updatePlayButton();spectrumSetPaused(true);});audio.addEventListener("ended",()=>{if(window.ATPTrace)window.ATPTrace("audio.ended",{ct:audio.currentTime});nextTrack();});audio.addEventListener("stalled",()=>{if(window.ATPTrace)window.ATPTrace("audio.stalled",{ct:audio.currentTime});});audio.addEventListener("waiting",()=>{if(window.ATPTrace)window.ATPTrace("audio.waiting",{ct:audio.currentTime});});audio.addEventListener("error",()=>{if(window.ATPTrace)window.ATPTrace("audio.error",{ct:audio.currentTime,code:audio.error&&audio.error.code});});
// 播放失败处理:最多重试 2 次(每次重新 resolve 拿新 URL);直连失败自动回退后端代理流(服务器端拉取,无跨域限制)
async function streamFailed() {
  if((state.streamRetries||0)>=2){state.streamRetries=0;showError(t("streamFailed"));return;}
  state.streamRetries=(state.streamRetries||0)+1;
  const track=state.queue[state.current];
  if(!track)return;
  audio.pause();
  // 直连(direct_url)失败时,优先回退到后端代理流(同一会话),而非重复 resolve 直连
  if(state.currentIsDirect && state.currentStreamUrl){
    state.currentIsDirect=false;
    audio.src=state.currentStreamUrl;
    state.speedSession=state.currentSessionId;
    showError(t("retryingStream"));
    safePlay();
    return;
  }
  showError(t("retryingStream"));
  playIndex(state.current);
}
// v2/MSE 播放期间 audio error 不应触发 streamFailed 重试:cleanupDrm() 里的 audio.load()
// 会因旧 MSE 销毁产生 error 事件,若走 streamFailed 会再次 playIndex → 双播放竞态(InvalidStateError)。
// 只在 v1 直连/代理播放时 error 才算真实失败,触发重试。
audio.addEventListener("error",()=>{
  const inV2 = Boolean(drmPlayback) || (audio.src && audio.src.startsWith("blob:"));
  if(window.ATPTrace)window.ATPTrace("audio.error",{ct:audio.currentTime,code:audio.error&&audio.error.code,v2:inV2});
  if(inV2){ return; } // MSE 错误由 playDrm 内部处理,不重试
  if(state.current>=0)streamFailed();else showError("This stream format is not supported by this browser.");
});
$("#languageSelect").addEventListener("change",event=>{state.lang=event.target.value;localStorage.setItem("tiddl-language",state.lang);applyLocale();}); $("#themeButton").addEventListener("click",()=>{state.theme=state.theme==="dark"?"light":"dark";localStorage.setItem("tiddl-theme",state.theme);applyTheme();});
document.addEventListener("click",event=>{if(!event.target.closest("#artistSearch")&&!event.target.closest("#artistSearchResults")){const p0=$("#artistSearchResults"); if(p0)p0.hidden=true;}if(!event.target.closest(".player-search-wrap")&&!event.target.closest("#playerSearchResults"))$("#playerSearchResults").hidden=true;if(!event.target.closest("#qualityControl")&&$("#qualityMenu"))$("#qualityMenu").hidden=true;if(!event.target.closest(".artist-chooser"))hideArtistChooser();});
document.addEventListener("keydown",event=>{if(document.body.dataset.route!=="player")return;if(event.target.matches("input,select"))return;if(event.code==="Space"){event.preventDefault();$("#play").click();}if(event.code==="ArrowRight")audio.currentTime+=5;if(event.code==="ArrowLeft")audio.currentTime-=5;});
// 路由进入播放视图时,隐藏状态下测量的滚动标记需要重新计算
window.ATPPlayer = { enter: markOverflowTitles };
if("mediaSession" in navigator){navigator.mediaSession.setActionHandler("play",safePlay);navigator.mediaSession.setActionHandler("pause",()=>audio.pause());navigator.mediaSession.setActionHandler("previoustrack",()=>$("#previous").click());navigator.mediaSession.setActionHandler("nexttrack",nextTrack);}
$("#playerDefaultHighest").checked=state.defaultHighest;$("#playerDefaultLowest").checked=state.defaultLowest;$("#playerNoImages").checked=state.noImages;applyNoImages();audio.volume=.8;paintRange($("#volume"));paintRange($("#seek"));$("#shuffle").classList.toggle("active",state.shuffle);renderRepeatIcon();applyTheme();applyLocale();showTab("playlist");showPanelTab("artist");renderFollowing();refreshTrackActions();updateNowCopy();icon();saveQueueSession();
setInterval(pollSpeed,1000);
// 预热 Widevine CDM + 能力探测:手机硬件 CDM 初始化慢或配置不匹配(遥测 "Unsupported keySystem"),
// 登录/加载后顺序尝试候选配置,成功则缓存 MediaKeys 与可用配置;全部失败则锁死 drmBroken,
// 本会话全部走 V1 秒播,不再每次播放都反复等 V2 失败。
function prewarmWidevine() {
  if (!canPlayDrm()) {
    state.drmBroken = true; localStorage.setItem("tiddl-player-drm-broken", "true");
    if (window.ATPTrace) window.ATPTrace("drm.prewarm", { ok: false, msg: "no EME API" });
    return;
  }
  if (_cachedMediaKeys || window.__drmPrewarming) return;
  window.__drmPrewarming = true;
  const probe = window.ATPEmProbe ? window.ATPEmProbe() : null;
  if (probe && probe.then) probe.then((r) => { if (window.ATPTrace) window.ATPTrace("eme.probe", r); }).catch(() => {});
  (async () => {
    let lastErr = null;
    for (let i = 0; i < DRM_CONFIGS.length; i++) {
      try {
        const access = await withTimeout(navigator.requestMediaKeySystemAccess("com.widevine.alpha", [DRM_CONFIGS[i]]), 6000, "prewarm cfg" + i);
        const keys = await withTimeout(access.createMediaKeys(), 10000, "prewarm create");
        _cachedMediaKeys = keys;
        // CDM 现在可用 → 清除历史失败留下的 drmBroken 锁(无痕窗口内 localStorage 会跨页面保留),
        // 否则 playIndex 永远走 V1,新修复永远测不到。
        state.drmBroken = false; localStorage.removeItem("tiddl-player-drm-broken");
        if (window.ATPTrace) window.ATPTrace("drm.prewarm", { ok: true, cfg: i, contentType: DRM_CONFIGS[i].audioCapabilities[0].contentType, rb: DRM_CONFIGS[i].audioCapabilities[0].robustness || "" });
        return;
      } catch (e) {
        lastErr = e;
        if (window.ATPTrace) window.ATPTrace("drm.prewarm", { ok: false, cfg: i, contentType: DRM_CONFIGS[i].audioCapabilities[0].contentType, rb: DRM_CONFIGS[i].audioCapabilities[0].robustness || "", msg: String(e && e.message || e) });
      }
    }
    state.drmBroken = true; localStorage.setItem("tiddl-player-drm-broken", "true");
    if (window.ATPTrace) window.ATPTrace("drm.prewarm", { ok: false, final: true, msg: String(lastErr && lastErr.message || lastErr) });
  })();
}
if (window.ATPAuth && window.ATPAuth.ready) { window.ATPAuth.ready.then(prewarmWidevine); } else { setTimeout(prewarmWidevine, 2000); }
// 移动端抽屉手势:左栏(library)藏左侧,右栏(lyrics)藏右侧,左右滑屏切换。
// 用原生 Pointer/Touch 事件手动识别横向滑动(不依赖 Hammer.js——它在移动 Chrome 上
// 因 touch-action:pan-y 的 pointercancel 拦截而收不到完整 swipe,Firefox 正常)。
(function () {
  const shell = document.getElementById("view-player");
  if (!shell) return;
  const backdrop = document.getElementById("playerDrawerBackdrop");
  const isMobile = () => window.matchMedia("(max-width: 700px)").matches;
  function setDrawer(kind, open) {
    // 抽屉使用独立类名(drawer-*),与封面歌词模式的 lyrics-open 解耦,避免播放时被误关
    const openClass = kind === "library" ? "drawer-lib-open" : "drawer-lyr-open";
    shell.classList.toggle(openClass, open);
    if (open) shell.classList.toggle(kind === "library" ? "drawer-lyr-open" : "drawer-lib-open", false);
    if (backdrop) backdrop.hidden = !(shell.classList.contains("drawer-lib-open") || shell.classList.contains("drawer-lyr-open"));
  }
  // —— 原生横向滑动识别 ——
  const MIN_DX = 48;            // 触发滑动的水平位移阈值(px),比 Hammer 默认更灵敏
  const RATIO = 1.1;            // 水平需明显大于垂直,避免与上下滚动混淆
  // 可交互元素(输入框/按钮/链接/搜索框及其结果面板等)上的触摸不走抽屉手势,完全交给浏览器原生处理,
  // 避免 setPointerCapture/preventDefault 干扰首次点击聚焦(Chrome 上会吞掉 tap)。
  // 必须覆盖所有绑定 click 的容器(边栏标签/队列/收藏/关注/搜索结果/信息/艺术家/歌词等),
  // 否则手势处理器接管 pointerdown 后 Chrome 不生成 click(边栏首 tap 无效的根因)。
  const isInteractive = (t) => t && t.closest && !!t.closest(
    "input, textarea, select, button, a, label, [contenteditable], " +
    ".artist-search, .player-search-wrap, #artistSearch, .search-clear, " +
    "#artistSearchResults, #playerSearchResults, .player-search-results, " +
    ".library-tabs, [data-library-tab], .queue-head, #playerQueue, .player-queue, " +
    "#playerFavorites, #playerFollowing, #queueEmpty, #favEmpty, #followEmpty, " +
    "#infoView, .info-view, #nowArt, .now-art, #favoriteButton, #downloadButton, " +
    ".lyrics-tabs, [data-panel-tab], #artistView, .artist-view, " +
    ".playlist-album-head, .playlist-album-tracks, [data-play], [data-resource], " +
    "[data-fav-track], [data-fav-album-id], [data-remove], [data-remove-group], " +
    "#play, #previous, #next, #shuffle, #repeat, #qualityControl, #qualityMenu, " +
    "#playerSettingsButton, [data-close-settings], #mute, #volume, #seek, #seekRow"
  );
  let gesture = null;
  function start(x, y, id) {
    gesture = { id, x0: x, y0: y, cx: x, cy: y, active: true, vertical: false };
  }
  function move(x, y) {
    if (!gesture || !gesture.active) return;
    gesture.cx = x; gesture.cy = y;
    // 一旦判定为纵向主导(浏览器原生滚动方向),放弃手势识别,避免干扰列表滚动
    const dx = x - gesture.x0, dy = y - gesture.y0;
    if (Math.abs(dy) > Math.abs(dx) * RATIO && Math.abs(dy) > 8) gesture.vertical = true;
  }
  function end() {
    if (!gesture || !gesture.active) return;
    const g = gesture;
    gesture = null;
    if (g.vertical) return;
    const dx = g.cx - g.x0, dy = g.cy - g.y0;
    if (Math.abs(dx) < MIN_DX || Math.abs(dy) > Math.abs(dx) / RATIO) return;
    if (dx > 0) { // 右滑
      if (shell.classList.contains("drawer-lyr-open")) setDrawer("lyrics", false);
      else setDrawer("library", true);
    } else { // 左滑
      if (shell.classList.contains("drawer-lib-open")) setDrawer("library", false);
      else setDrawer("lyrics", true);
    }
  }
  function cancel() { gesture = null; }
  // —— Chrome Android 首 tap 兜底 ——
  // 根因(已用纯 HTML 页面复现验证):Chrome 在 touch-action:pan-y 元素上检测到滑动手势后,
  // 会抑制随后 ~1000ms 内的原生 click 事件(防误触),而我们的抽屉滑动动画恰好在窗口内,
  // 导致"滑动后第一下点击无效"。Firefox 无此抑制所以正常。
  // 修复:touch-action 保持 pan-y(让水平滑动手势归 JS,抽屉才能开),
  // 这里用 pointerup 识别 tap 并手动派发 click 绕过 Chrome 抑制,同时去重原生 click。
  let _lastTapDown = null; // {x,y,id,t}
  let _suppressUntil = 0; // 手动 click 派发后,该时间点前到达的原生 click 一律吞掉(避免双击)
  const TAP_MOVE_TOL = 14; // tap 允许的最大位移(px)
  document.addEventListener("pointerdown", (e) => {
    if (e.pointerType !== "touch") return;
    _lastTapDown = { x: e.clientX, y: e.clientY, id: e.pointerId, t: Date.now(), target: e.target };
  }, true);
  document.addEventListener("pointerup", (e) => {
    if (e.pointerType !== "touch") return;
    const d = _lastTapDown;
    _lastTapDown = null;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (Math.abs(dx) > TAP_MOVE_TOL || Math.abs(dy) > TAP_MOVE_TOL) return; // 是滑动,非 tap
    const el = e.target;
    if (!el || el === document || el === window) return;
    // 手动派发 click(Chrome 抑制的是"触摸派生的 click",手动派发不受影响)。
    // 手动派发的是 untrusted click,不会被去重监听器拦截;随后到达的原生 trusted click 用时间窗口吞掉。
    try {
      el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, composed: true, view: window, clientX: e.clientX, clientY: e.clientY }));
      _suppressUntil = Date.now() + 300;
    } catch (_) {}
    // 输入框手动聚焦(手动 click 不触发原生 focus)
    try { if (el.matches && el.matches("input, textarea, select")) el.focus(); } catch (_) {}
  }, true);
  // 去重:手动派发 click 后 300ms 内到达的原生(trusted)click 吞掉,避免双击触发。
  // untrusted(手动派发)放行;键盘/鼠标的真实 click 不在触摸流程中,不受影响。
  document.addEventListener("click", (e) => {
    if (!e.isTrusted || Date.now() > _suppressUntil) return;
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
  // Pointer Events(Chrome/Firefox/新 Safari);旧 Safari 回退 Touch Events
  const usePointer = "PointerEvent" in window;
  const bind = (type, fn) => shell.addEventListener(type, fn, { passive: true });
  const traceIn = (evt, extra) => { if (window.ATPTrace) window.ATPTrace("gesture." + evt, Object.assign({ t: Math.round(performance.now()) }, extra || {})); };
  if (usePointer) {
    bind("pointerdown", (e) => {
      if (e.pointerType === "mouse") { traceIn("pd", { why: "mouse", id: e.pointerId }); return; }
      // 抽屉打开时,侧边栏内部的交互元素也允许启动手势(在内部滑动即可关闭抽屉);
      // tap(无位移)在 end() 里不动作,不影响首次点击修复。
      const drawerOpen = shell.classList.contains("drawer-lib-open") || shell.classList.contains("drawer-lyr-open");
      if (isInteractive(e.target) && !(drawerOpen && e.target.closest && e.target.closest(".library-panel, .lyrics-panel"))) {
        traceIn("pd", { why: "interactive", target: e.target.id || e.target.tagName, id: e.pointerId }); return;
      }
      traceIn("pd", { why: "gesture-start", target: e.target.id || e.target.tagName, id: e.pointerId, x: Math.round(e.clientX), y: Math.round(e.clientY) });
      start(e.clientX, e.clientY, e.pointerId);
    });
    bind("pointermove", (e) => {
      if (e.pointerType === "mouse") return;
      if (gesture && gesture.id !== undefined && e.pointerId !== gesture.id) return;
      move(e.clientX, e.clientY);
    });
    bind("pointerup", (e) => { if (e.pointerType === "mouse") return; traceIn("pu", { id: e.pointerId, x: Math.round(e.clientX), y: Math.round(e.clientY) }); end(); });
    bind("pointercancel", (e) => { traceIn("pc", { id: e.pointerId, hadGesture: !!gesture }); cancel(); });
  } else {
    bind("touchstart", (e) => {
      const t = e.changedTouches[0]; if (!t) return;
      const drawerOpen = shell.classList.contains("drawer-lib-open") || shell.classList.contains("drawer-lyr-open");
      if (isInteractive(e.target) && !(drawerOpen && e.target.closest && e.target.closest(".library-panel, .lyrics-panel"))) return;
      start(t.clientX, t.clientY, t.identifier);
    });
    bind("touchmove", (e) => { const t = e.changedTouches[0]; if (!t) return; if (gesture && gesture.id !== undefined && t.identifier !== gesture.id) return; move(t.clientX, t.clientY); });
    bind("touchend", end);
    bind("touchcancel", cancel);
  }
  // 侧边栏无叉号按钮:靠滑动手势/遮罩关闭(drawer 手势在下方绑定)
  if (backdrop) backdrop.addEventListener("click", () => { setDrawer("library", false); setDrawer("lyrics", false); });
  // 暴露给全局:播放/导航等需要主动收起抽屉时调用
  window.ATPCloseDrawers = () => { setDrawer("library", false); setDrawer("lyrics", false); };
})();



})();
