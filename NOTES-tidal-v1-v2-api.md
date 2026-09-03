# Tidal v1 / v2 API 知识整理

> 基于真实账号实测 + Tidal 网页播放器 HAR 抓包（2026-09-03）。
> 结论均来自实际流解析，非文档猜测。

## 一、两条 API 通道总览

| | v1 API | v2 API |
|---|---|---|
| 端点 | `api.tidal.com/v1/tracks/{id}/playbackinfopostpaywall`（客户端库封装为 `get_track_stream`） | `openapi.tidal.com/v2/trackManifests/{id}` |
| 用途 | 我们的播放/下载主路径（无 DRM 直链） | Tidal 官方网页播放器；我们用于 v2 DRM（EME/Widevine）播放 |
| 格式 | BTS（`application/vnd.tidal.bts`）或 DASH XML | JSON:API + data URI 内嵌 MPEG-DASH XML |
| 加密 | 多数 `encryptionType=NONE`（可直连） | 通常带 DRM（cbcs + Widevine/PlayReady PSSH） |
| 鉴权头 | 常规 `Authorization: Bearer <token>` | **必须 `Accept: application/vnd.api+json`**（否则 404）|

## 二、v1 API（get_track_stream）各音质档实测

请求参数：`audioquality=<LOW|HIGH|LOSSLESS|HI_RES_LOSSLESS>`、`playbackmode=STREAM`、`assetpresentation=FULL`、`deviceType=BROWSER`、`platform=WEB`

实测返回（普通立体声曲目，如 Daft Punk – One More Time 1550546）：

| 档位 | audioQuality | codecs | 扩展名 | 规格 |
|---|---|---|---|---|
| low | LOW | mp4a.40.5（HE-AAC）| .m4a | ≈96 kbps |
| normal | HIGH | mp4a.40.2（AAC-LC）| .m4a | ≈320 kbps |
| high | LOSSLESS | flac | .flac | 44.1kHz / 16bit |
| max | LOSSLESS（注意！）| flac | .flac | 44.1kHz / 16bit |

**关键坑**：
- `max`（HI_RES_LOSSLESS）在 v1 实际返回的仍是 `LOSSLESS` 44.1/16 FLAC——**v1 拿不到真正的 Hi-Res**（96k+/24bit 只存在于 v2 FLAC_HIRES）
- 加密检查：解析 manifest JSON 的 `encryptionType`，非 `NONE` 即 DRM 保护，浏览器无法直接保存

## 三、v2 API（trackManifests）——真正的 Hi-Res 在这里

Tidal 网页播放器真实请求（HAR 实拍）：

```
GET https://openapi.tidal.com/v2/trackManifests/426175179
  ?adaptive=false
  &formats=HEAACV1&formats=AACLC&formats=FLAC&formats=FLAC_HIRES
  &manifestType=MPEG_DASH
  &uriScheme=DATA
  &usage=PLAYBACK
```

请求头：`Accept: application/vnd.api+json`（关键）、`Content-Type: application/vnd.api+json`、`Referer: https://tidal.com/`、`Origin: https://tidal.com`

响应 `attributes.uri` 是 `data:application/dash+xml;base64,<MPD XML>`，MPD 内 Representations 实测：

| formats 参数 | Rep id | codecs | samplingRate | 说明 |
|---|---|---|---|---|
| FLAC_HIRES | `FLAC_HIRES,192000,24` | flac | 192000 | **真正的 Hi-Res（96k+/24bit）** |
| FLAC | `FLAC,44100,16` | flac | 44100 | 普通无损 |
| AACLC | `AACLC` | mp4a.40.2 | 44100 | AAC-LC |
| HEAACV1 | — | mp4a.40.5 | — | HE-AAC |

### FLAC_HIRES：我们此前的盲区

- Tidal 把 **FLAC 与 FLAC_HIRES 分成两个独立 formats**：请求 `FLAC` 永远只给 44.1/16；必须显式请求 `FLAC_HIRES` 才返回 192kHz/24bit（甚至 88.2kHz/24bit 等，视曲目而定）
- 我们的 `v2_drm_manifest()` 只传 `FLAC`/`AACLC` 单格式 → **永远见不到 Hi-Res**
- 后果：播放/下载显示的"Hi-Res"标签（mediaMetadata 含 HIRES_LOSSLESS）与实际流（44.1/16）不符——**不是 Tidal 造假，是我们没请求对的格式**
- 解析 v2 MPD 时不要只取最后一个 Representation：用 `root.iter("{urn:mpeg:dash:schema:mpd:2011}Representation")` 收集全部，按需选最高档

## 四、Atmos 曲目的行为差异（重要）

以 Joni Mitchell – River（426175179，audioModes=['DOLBY_ATMOS']）为例：

**v1**：无论请求什么音质档，都返回 `DOLBY_ATMOS / eac3 / audioQuality=LOW`（E-AC-3，768kbps，6声道）——**v1 对 Atmos-only 曲目只给 Atmos 流，没有立体声版本**

**v2**：
- `formats=FLAC_HIRES` → `FLAC_HIRES,192000,24`（真 Hi-Res 无损）
- `formats=FLAC` → 44.1/16
- `formats=AACLC` → AAC-LC 44.1kHz
- 但带 DRM（cbcs + Widevine/PlayReady PSSH），需 EME license 才能解密

**推论**：之前"Atmos-only 只能转码"的结论不完整——v2 有普通 AAC/FLAC（只是带 DRM）。播放路径（resolve_player_stream）遇到 Atmos 才走转码是合理的兜底；但**下载要 Hi-Res 必须走 v2 FLAC_HIRES + DRM 处理**，v1 拿不到。

## 五、E-AC-3 流解析要点

- E-AC-3（Atmos 承载格式）容器是 mp4，`codecs=eac3`
- syncframe 头解析采样率（fscod）：0=48k、1=44.1k、2=32k——但**在 mp4 里要先找 mdat 内的 syncframe**（0x0B77），不要在文件头找
- E-AC-3 是压缩编码，无 16/24bit 位深概念（Atmos JOC 内部分辨率另说）
- ffprobe 可确认：`River.m4a` 实测 `eac3 / 48kHz / 6ch / 768kbps`

## 六、浏览器直连 / 下载路径要点

- v1 直链（`direct_url`）：非 DRM、非 Atmos、非转码、mime∈{audio/mp4, audio/flac} 时浏览器可直接 `<audio>` 播放，零服务器带宽；签名有效期约 60 分钟
- 浏览器下载（`/api/download/browser/{track_id}`）：服务器解析流后**流式转发字节**（不落盘），必须走服务器——跨域 `download` 属性失效 + CORS 限制 fetch 跨域 CDN + 需要服务器设置 `Content-Disposition: filename`
- v1 下载各档 = 上一节表格；Atmos-only 曲目 v1 下载只会得到 E-AC-3（手机默认播放器放不了）

## 七、已确认的坑 / 备忘

1. **v2 必须 `Accept: application/vnd.api+json`**，缺失/用 application/json → 404
2. **v3 trackManifests 不存在**（`/v3/trackManifests/{id}` → 404）
3. formats 参数传 `ATMOS` / `DOLBY_ATMOS` → HTTP 400（不是合法值）
4. Tidal 网页播放器 `adaptive=false`（我们是 true，暂无影响）
5. 分片 CDN（sp-ad-cf.audio.tidal.com）带任意 Origin/Referer 都 403，只能由已登录 Tidal 会话的浏览器访问（DataDome 反爬）
6. Hi-Res 是否可用还取决于账号权限（HiFi Plus）与曲目实际提供；`mediaMetadata.tags` 含 `HIRES_LOSSLESS` 只是声明，流规格以 MPD Representation 为准

## 八、改进方向（未实现，供参考）

1. `v2_drm_manifest()` 增加 `FLAC_HIRES` 格式支持，让播放/下载能真正拿到 Hi-Res（需处理 DRM license，复杂度高）
2. 解析 v2 MPD 时收集全部 Representation，按最高可用档展示/请求
3. v1 `get_track_stream` 对 Atmos-only 曲目与 v2 行为不一致——如需无损下载，优先考虑 v2 FLAC_HIRES 路径
