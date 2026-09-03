# Atmos-only 曲目零带宽播放方案（浏览器 EME + 后端 license 代理）

> 状态：**已落地并验证成功**（2026-08-31，真实浏览器完整播放 Atmos-only 曲目 328631592/328631593）
> 本文档记录完整思路、解密机制、架构与代码位置，供后续维护参考。

---

## 一、问题背景

Tidal 上部分曲目**只有 Dolby Atmos（eac3/ac4）音频流**，浏览器无法原生解码这类流，导致：
- 旧方案：后端 ffmpeg 转码 eac3 → 立体声 AAC（能播，但**占服务器 CPU/带宽**，违背弱服务器约束）
- 用户核心诉求：**所有音频流由用户浏览器完成，不占用服务器带宽**

## 二、关键探索结论（为什么走这条路）

| 探索项 | 结论 |
|---|---|
| Tidal v2 API 是否有普通流 | ✅ 有：`v2/trackManifests` 返回 AAC-LC/FLAC（非 eac3）|
| 这些流是否 DRM 加密 | ✅ **加密**：MPD 含 cbcs + Widevine/PlayReady PSSH，init 段 sample entry 为 `enca` |
| 分片能否浏览器直连 | ✅ 纯 GET（无自定义头）→ 200，**音频字节零服务器带宽** |
| tidal-cli 为何能"播" | ❌ 误判：tidal-cli 用 `adaptive:false` 只拿到 **PREVIEW（30 秒）**，并非完整流 |
| 能否前端纯 MSE 解密 | ❌ 不能：加密流需要 Widevine license，纯 MSE 卡在"等 license"→ 进度条不动、无声 |
| 能否后端代拿 license | ✅ **能**：`api.tidal.com/v2/widevine` 用**账号 Bearer token** 鉴权，返回 200 license |

**核心突破**：Widevine license 请求本身只有 ~1.7KB challenge / ~710B license，**由后端用账号池 token 转发**（不暴露账号、几乎零带宽），音频大流量全部走浏览器直连 CDN。这就是"零带宽 + 能解密"的完美结合。

## 三、解密机制（核心）

### 3.1 总体链路

```
用户浏览器（我们播放器）
  │ ① POST /api/player/resolve           （后端解析 v2 manifest）
  ▼
后端：v2_drm_manifest() → { pssh, kid, init_url, media_template, segment_count, ... }
  │ ② 返回 drm 播放包
  ▼
用户浏览器
  │ ③ EME: requestMediaKeySystemAccess('com.widevine.alpha')
  │    createMediaKeys → audio.setMediaKeys(keys)
  │    createSession → generateRequest('cenc', pssh)   // 生成 Widevine challenge
  │ ④ message 事件拿到 challenge（~1.7KB 二进制）
  │ ⑤ POST /api/player/drm-license （Content-Type: application/octet-stream, body=challenge）
  ▼
后端：drm_license() 用账号池 Bearer token 转发 → api.tidal.com/v2/widevine
  │ ⑥ 返回 license（~710B 二进制）
  ▼
用户浏览器：session.update(license) → Widevine CDM 解密
  │ ⑦ MSE: append init + 分片（分片由浏览器 fetch CDN，纯 GET，零服务器带宽）
  ▼
播放完成（进度条正常走动、有声音）
```

### 3.2 为什么 license 必须浏览器自己拿

Widevine 的 license **绑定于生成 challenge 的那个浏览器/设备会话**：
- `generateRequest(pssh)` 产生的 challenge 内含该浏览器的 Widevine CDM 公钥
- Tidal 返回的 license 也是**加密绑定那个公钥**的
- 因此 license 请求**不能由后端代发 challenge 再解密**——必须由浏览器 EME 生成 challenge、再由浏览器 `update(license)` 完成解密

**后端只做"鉴权转发"**：把浏览器的 challenge 原样转发给 Tidal（带上账号池 token 表明"这个订阅账号有权播放"），再把 Tidal 返回的 license 原样回给浏览器。后端**看不到也解不开**内容密钥。

### 3.3 鉴权细节

- **license 端点**：`POST https://api.tidal.com/v2/widevine`
- **请求头**：`Content-Type: application/octet-stream`，`Origin: https://tidal.com`，`Referer: https://tidal.com/`，`Authorization: Bearer <账号池token>`
- **Tidal 校验**：challenge 内含内容/账号/设备信息，license server 校验**该账号有权播放此内容**（有订阅）+ 绑定浏览器设备
- **账号池透明**：浏览器端完全不接触 Tidal 账号，只有后端持有 token；`select_account()` 按负载选账号

### 3.4 音频字节零带宽

- init/media 分片 URL 来自 v2 manifest（CloudFront 签名 URL，`sp-ad-cf.audio.tidal.com`）
- 浏览器**纯 GET**（无自定义头）直接拉取 → **200**，音频大流量不经过服务器
- 之前"403"是因为带 Range/自定义头触发 CORS 预检被拒，**纯 GET 简单请求可绕过**

## 四、代码位置

### 后端 `tiddl/web/app.py`
| 函数/端点 | 作用 |
|---|---|
| `v2_drm_manifest(track_id, account_id)` | 调 `v2/trackManifests`（adaptive:true）解析 MPD → 返回 pssh/kid/init_url/media_template/segment_count/codec 等 |
| `resolve_player_stream()` atmos 分支 | Atmos-only 时**优先尝试 v2 AAC-LC 直连**（返回带 `drm` 的会话），失败才回退 ffmpeg 转码 |
| `POST /api/player/resolve` | 对 Atmos-only 返回 `drm` 包（含 pssh/init/media_template/segment_count） |
| `POST /api/player/drm-license` | **license 代理**：接收浏览器 challenge → 用账号池 token 转发 `api.tidal.com/v2/widevine` → 返回 license |
| `POST /api/player/drm-resolve` | （诊断用）直接返回 v2 DRM 包 |

### 前端 `tiddl/web/static/player.js`
| 函数 | 作用 |
|---|---|
| `canPlayDrm()` | 检测 MediaSource + `requestMediaKeySystemAccess`（Widevine EME） |
| `playDrm(bundle)` | **核心**：EME 拿 Widevine license（经后端代理）+ MSE 渐进播放 init+分片（浏览器直连 CDN） |
| `base64ToArrayBuffer()` | PSSH base64 → ArrayBuffer（EME initData） |
| `appendOne(sb, buf)` | 串行 append 分片到 SourceBuffer（等 updateend） |
| `playIndex()` | Atmos-only 时优先 `data.drm && canPlayDrm()` → `playDrm(data.drm)`，失败回退转码流 |

### 关键参数
- `adaptive: true`：**必须**用 true 才返回完整流（false 只给 30 秒 PREVIEW）
- `formats: AACLC`：浏览器可解码的普通 AAC（44.1kHz 立体声）
- `manifestType: MPEG_DASH`、`uriScheme: DATA`、`usage: PLAYBACK`

## 五、验证记录

- 真实浏览器（用户环境，有 Widevine CDM）：播放 328631592（Atmos-only，274s）**成功**，进度条走动、有声音、完整播放
- license 代理：HAR 真实 challenge → 后端转发 → **200 + 710B license** ✅
- 音频分片：浏览器纯 GET → 200 ✅
- 后端测试：127 项全过

## 六、局限与后续

1. **需要浏览器支持 Widevine EME**（Chrome/Edge 自带；Firefox 需 Google 的 CDM；Safari 走 FairPlay 不支持本方案）
2. **license 有有效期**（通常绑定播放会话/较短期），暂停过久或重播可能需重新 resolve + 拿新 license
3. **兜底**：EME 不可用或 license 失败时，应回退到后端 ffmpeg 转码流（保证可播，占 CPU/带宽）
4. 账号池：license 用 `select_account()` 选号，若该账号无此内容播放权需健康检查/重试
