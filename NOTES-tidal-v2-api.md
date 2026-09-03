# Tidal v2 API 破解笔记（Atmos-only 曲目播放方案）

> 状态：**探索中，未落地**。以下均为 Playwright + 真实账号实测，非猜测。
> 日期：2026-08-31

## 一、核心发现（最重要的突破）

**Tidal 网页版播放器使用的不是 tiddl 依赖的 v1 API，而是一套全新的 v2 API：**

```
GET https://openapi.tidal.com/v2/trackManifests/{trackId}
```

网页版真实请求（Playwright 抓包）：

```
https://openapi.tidal.com/v2/trackManifests/147287375
  ?adaptive=true
  &formats=HEAACV1
  &formats=AACLC
  &formats=FLAC
  &formats=FLAC_HIRES
  &manifestType=MPEG_DASH
  &uriScheme=DATA
  &usage=PLAYBACK
```

请求头（关键）：
- `Accept: application/vnd.api+json`  ← **JSON:API 格式，缺失/用 application/json 会 404**
- `Content-Type: application/vnd.api+json`
- `Authorization: Bearer <o2_access token>`

### 响应结构

```json
{
  "data": {
    "id": "328631592",
    "type": "trackManifests",
    "attributes": {
      "trackPresentation": "FULL",
      "uri": "data:application/dash+xml;base64,<MPD XML>"
    }
  }
}
```

### 关键结论：Atmos-only 曲目其实有普通 AAC/FLAC 流

对 `audioModes=['DOLBY_ATMOS']` 的曲目（如 328631592 / 365179105）：

- **老 v1 API**（`api.tidal.com/v1/tracks/{id}/playbackinfopostpaywall`）无论请求什么 quality/deviceType，都只返回 `DOLBY_ATMOS / eac3` → 让我们误以为"只有 Atmos 流"
- **v2 API** 返回 `trackPresentation: FULL`，MPD 里的 Representations：
  - `FLAC_HIRES,88200,24` → codecs=flac
  - `FLAC,44100,16` → codecs=flac
  - `AACLC` → codecs=mp4a.40.2（浏览器原生可解码）
  - `HEAACV1` → codecs=mp4a.40.5
- **即：这些"Atmos-only"曲目本质上有普通 AAC/FLAC 流，浏览器可直接播放，不需要转码**

### 我们账号的 token 也能用

tiddl 的 auth token（o2_access, cid=6432）加 `Accept: application/vnd.api+json` 即可拿到 FULL manifest。
之前 404 的唯一原因是 Accept 头错误（application/json）。

## 二、Audio CDN / 分片

- 音频分片来自 `https://sp-ad-cf.audio.tidal.com/mediatracks/...`（CloudFront 签名 URL：Policy/Signature/Key-Pair-Id）
- MPD 里 `media="...$Number$.mp4..."` 是分片模板
- **CORS 预检（OPTIONS）返回 `Access-Control-Allow-Origin: *`**，跨域 fetch 分片在 CORS 层面放行
- 但直取 GET 分片目前 403（原因待确认：DataDome 反爬？URL 时效？会话绑定？）
- 注意：这些流很可能带 **DRM（cbcs + Widevine/PlayReady PSSH）** —— 从 AACLC MPD 看到 `<ContentProtection>` 和 PSSH box。Tidal 网页版靠浏览器 EME + Widevine 解密播放。

## 三、待确认点（限流恢复后验证）

1. **DRM 是否强制**：v2 返回的 AAC-LC 流是否必须走 EME/Widevine？有没有无 DRM 的流（如 usage=DOWNLOAD / uriScheme 变体 / manifestType 变体）？
2. **分片 403 原因**：是 DataDome 反爬（需浏览器会话 cookie），还是 URL 时效/绑定？
3. **纯前端零后端带宽是否可行**：如果分片可被浏览器跨域 fetch 且流无 DRM → 前端 MSE 直接播放；若有 DRM → 需 EME license，复杂度高。

## 四、最优方案方向（待验证后定稿）

目标（用户约束）：服务器带宽/性能弱，不能做任何后端转码；原始流不走后端；后端只解析 URL；下载/转码/播放由前端承担。

**理想方案**：
- 后端：调 v2 API 拿 AAC/FLAC manifest（很小的 JSON 请求），解析出分片 URL 返回给前端；不碰音频字节、不转码
- 前端：MSE 拉分片直接播放（AAC/FLAC 浏览器原生解码）
- 若 DRM 强制 → 需评估 EME/Widevine 方案（较复杂，可能依赖浏览器自带 Widevine）

**对比 ffmpeg.wasm 方案**：v2 API 能拿到 AAC-LC，则根本不需要转码，比 ffmpeg.wasm 更彻底、零 CPU。

## 五、关键测试命令/参数备忘

- v2 manifest（Python 直调，注意 Accept 头）：
```python
headers = {
  "Authorization": f"Bearer {token}",
  "Accept": "application/vnd.api+json",
  "Content-Type": "application/vnd.api+json",
  "Referer": "https://tidal.com/",
}
requests.get("https://openapi.tidal.com/v2/trackManifests/{tid}",
  params={"adaptive":"true","formats":"AACLC","manifestType":"MPEG_DASH","uriScheme":"DATA","usage":"PLAYBACK"},
  headers=headers, timeout=60)
```
- 解析 MPD：`base64.b64decode(uri.split(",",1)[1])` 得到 XML，取 `media=` 模板
- 分片 URL：模板 `$Number$` → `1`
- Playwright 抓包：拦截 `openapi.tidal.com` 的 trackManifests 请求，读请求头 Authorization

## 六、风险/注意
- DataDome 反爬：频繁请求会触发 `ERR_CONNECTION_CLOSED`/超时，需控制频率、间隔 10s+，用真实浏览器会话
- v2 API 可能需要特定 `cid`（网页版 cid=13557，我们 cid=6432 也能用）
- DRM 是最大不确定项，直接影响"纯前端"可行性

## 七、阶段0 决定性验证结果(2026-08-31)

### 已确认
1. **v2 trackManifests 对 Atmos-only 曲目返回 FULL AAC-LC/FLAC 流**(非 eac3),用我们账号 token + `Accept: application/vnd.api+json` 即可。
2. **但这些流带 DRM**:AACLC MPD 内含 `<ContentProtection value="cbcs">` + Widevine/PlayReady PSSH。Tidal 网页版靠浏览器 EME + 内置 Widevine CDM 解密播放。
3. 浏览器直连分片(带 DataDome cookie 后页面内 fetch)仍 `Failed to fetch` —— CDN 需合法会话/签名,且 DRM 流无法用纯前端 ffmpeg.wasm 读取解密。

### 对"浏览器直连零带宽"的含义
- **普通立体声流**:浏览器 `<audio src="Tidal CDN URL">` 可直连播放(媒体元素不需 CORS),零服务器带宽可行。
- **Atmos-only 曲目**:v2 有 AAC-LC 但 DRM 加密;纯前端无 Widevine license 无法解密。要播需依赖浏览器内置 Widevine(类似 tidal-hifi 的 Electron 方案)或接受无法播放。

### 结论
"浏览器直连零带宽"对普通流成立;Atmos-only 是 DRM 障碍,非工程可实现(纯前端)。

## 八、阶段4 浏览器直连零带宽(已落地,2026-08-31)

### 实现
- 后端 `/api/player/resolve` 新增 `direct_url` 字段:
  - 仅当 `非transcoded && audio_mode==STEREO && mime_type∈{audio/mp4,audio/flac}` 时返回 Tidal CDN 原始 URL
  - Atmos/转码/不确定情况 `direct_url=null`,仍走 `/api/player/stream/{session_id}` 代理兜底
- 前端 `playIndex`: `audio.src = data.direct_url || data.stream_url`;直连时 `speedSession=null`(不轮询后端速度,因为字节不经服务器)

### 验证
- resolve 返回 STEREO 曲目的 `direct_url`(amz-pr-fa.audio.tidal.com/...mp4?token=...)
- 无 Origin 请求 → HTTP 200, type=audio/mp4, 8.9MB
- 签名 token 有效期约 60 分钟
- Playwright 真实浏览器 `<audio>` 直接加载 → loadedmetadata, duration=222s ✅(零服务器带宽)

### 结论
普通立体声流浏览器直连已生效:后端只做 resolve(小 JSON),音频字节零服务器带宽。
Atmos-only 仍受 DRM 限制,走代理转码/或不可播(见第七节)。

## 九、Atmos-only 播放方案 D 勘察(2026-08-31,用户要求:先验C不可行则用D)

### C 判不可行(已最终确认)
- v2 AAC-LC/FLAC 流带 DRM:PSSH 含 Widevine(edef8ba9) + PlayReady(9a04f079),MPD 内 <ContentProtection value="cbcs">
- 分片(sp-ad-cf.audio.tidal.com)服务端带任意 Origin/Referer 都 403 —— 只能由**已登录 Tidal 会话的浏览器**访问
- 无头 Chromium 无 Widevine EME;iframe 嵌 Tidal 页被 DataDome 验证码拦截(geo.captcha-delivery.com/captcha)
- 结论:纯前端/无会话环境无法拉分片,也无法解密

### D 两条子路线
- D1 自研 EME + 逆向 license 协议:需抓官方网页版 license 端点与请求格式(被 DataDome 挡),且分片仍需已登录浏览器会话;复杂度高
- D2 iframe 内嵌官方播放器:无 X-Frame-Options/CSP 限制(头全空),但 iframe 内 Tidal 页被 DataDome 验证码拦截,且借用官方 UI(非自研)
- tidal-hifi 现状:Electron 内嵌官方网页版,license 由官方 JS 处理,无自研 DRM;需要 Widevine CDM + 已登录会话

### 待用户配合
D 若要落地,需真实用户浏览器(带 Tidal 登录会话 + Widevine)验证:
1) 该浏览器能否 fetch 分片(短时效签名 URL + DataDome cookie)
2) 抓 license 请求(端点/格式/鉴权)以便 D1 复刻

## 十、D1 自研 EME(Widevine)实施进度(2026-08-31)

### 已打通的地基(全部实测)
1. v2 trackManifests → FULL AAC-LC 单文件静态流(4m34s, 44.1kHz 立体声, cbcs 加密)
2. PSSH 含 Widevine(edef8ba9) + PlayReady(9a04f079);KID=78eab717...
3. init 分片(783B)与 media 分片(160KB)均可被浏览器**纯 GET 直连**(200) —— 无 Range/自定义头时绕过 CORS 预检,零带宽可行
4. tidal-hifi = Electron 内嵌官方网页版,license 由官方 JS 处理,无自研 DRM

### 已实现
- 后端 `v2_drm_manifest()` + `POST /api/player/drm-resolve`:解析 MPD → {pssh, kid, init_url, media_url, codec, mime_type, duration_s, sample_rate}(已验证 200)
- 前端 MSE+EME 播放路径(playDrm):MediaSource + SourceBuffer + Widevine EME
  - fetch init/media 分片(纯 GET,零带宽) → appendBuffer
  - generateRequest(pssh) → message → requestLicense → session.update → 播放
  - Atmos-only(转码兜底)时优先尝试 EME,失败回退转码流
  - 移除/清空队列时 cleanupDrm

### 待办:license 端点逆向(必须用户真实浏览器配合)
- 前端已内置:EME message 事件 console.log 打印 license 请求字节数/类型;license URL 走 localStorage["tiddl-license-url"]
- 需要用户:在已登录 Tidal 的真实 Chromium DevTools→Network 播放 328631592,抓 license 请求(URL 含 license/widevine/playready),填入 tiddl-license-url
