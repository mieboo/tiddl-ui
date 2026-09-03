# Flutter App 架构方案（路线 B：原生端 + v1 API）

> 日期：2026-08-31
> 状态：方向已定（路线 B），技术栈评估完成，待实现
> 关联：`NOTES-tidal-v2-api.md`、`NOTES-atmos-playback.md`、`NOTES-tidal-rate-limit.md`

---

## 一、为什么是 Flutter + v1 API（战略结论）

浏览器方案的所有限制（CORS、eac3 解码、v2 DRM）**都是浏览器特有的**。原生 App 全部绕开：

| 能力 | 浏览器方案 | Flutter 原生 |
|---|---|---|
| 直连 Tidal CDN | CORS 拦（v1 403）| dio 原生网络，**无 CORS** |
| Atmos-only 播放 | 需 v2 AAC-LC + EME/license | ExoPlayer 原生解码 **E-AC3** |
| Atmos-only 下载 | v2 加密，拿不到明文 | **v1 eac3 明文直连** |
| 普通曲目下载 | v2 FLAC 分片拼装 | **v1 明文单文件**（更简单）|
| 零服务器带宽 | 是（分片直连）| 是（URL 直连）|
| 后端转码/license | 需要 | **不需要** |

**核心**：原生端用 **v1 API**（tiddl 现有下载逻辑）即拿到明文流，无 DRM、无转码、无 license。

## 二、架构总览

```
Flutter App（原生层）
 ├─ 登录：现有平台账号 → FastAPI（复用现有 users/session）
 ├─ 播放：dio 取 URL → ExoPlayer（media_kit）→ 本地解码
 │     ├─ 普通曲目：v1 明文 FLAC/AAC
 │     └─ Atmos-only：v1 明文 E-AC3（ExoPlayer 原生解）
 ├─ 下载：dio 直连 v1 明文 URL → 存本地（path_provider）
 └─ 数据：Riverpod 状态 + hive 本地缓存

后端 FastAPI（几乎零改动，仍是核心）
 ├─ 账号池管理（select_account / 健康 / 订阅检测）
 ├─ 平台用户登录/会话/权限
 ├─ 管理后台
 └─ ★ 新增：下载/播放 URL 解析端点（复用 tiddl v1 逻辑）
```

## 三、后端新增能力（唯一必做的后端改动）

新增一个解析端点，复用现有 `account_context().api.get_track_stream`（v1）：
- 输入：资源 URL / track_id + 质量档（LOW/HIGH/LOSSLESS/HI_RES）
- 输出：`{ urls: [{ track_id, title, artist, album, cover, filename, mime_type, codec, url }] }`
- URL 是 v1 明文流（单文件），App 拿到后 dio 直连下载/播放
- 服务器只做 URL 解析（小 JSON），**零音频字节过服务器**

## 四、技术栈（Flutter 路线 B）

| 层 | 选型 | 用途 |
|---|---|---|
| 框架 | Flutter 3.x | 单代码库 iOS + Android |
| 网络 | dio + dio_downloader | 无 CORS 直连 CDN、断点续传 |
| 播放 | media_kit（ExoPlayer 封装）| E-AC3/FLAC/AAC 原生解码、后台播放 |
| 后台播放 | audio_service | 前台服务、锁屏/通知控制 |
| 存储 | path_provider + hive | 下载目录、本地媒体库/播放队列 |
| 状态 | Riverpod | 登录、队列、收藏、播放状态 |
| 后端对接 | dio → FastAPI | 复用现有全部后端 |

## 五、模块划分

```
lib/
 ├─ core/          # 网络(dio)、配置、主题(复刻网页版深/浅色)
 ├─ auth/          # 登录、会话 token、登出
 ├─ api/           # FastAPI 客户端(用户/账号/解析端点)
 ├─ models/        # Track/Album/Artist 模型
 ├─ browse/        # 搜索、艺术家、专辑、歌单
 ├─ player/        # ExoPlayer 播放器、队列、后台服务
 ├─ downloads/     # dio 下载、进度、本地库
 ├─ favorites/     # 收藏
 └─ settings/      # 音质偏好、主题、语言
```

## 六、UX 沿用网页版

- 复刻现有设计语言：深/浅色主题、卡片布局、播放页（封面/进度条/音质/歌词/收藏）
- 移动端适配：底部导航（搜索/播放列表/收藏/设置）、下拉刷新、触控交互
- 语言：en/zh 双语（复用现有 i18n 词条思路）

## 七、验证要点（实现前）

1. v1 eac3 Atmos 流 ExoPlayer 能否解码（media_kit 对 E-AC3 支持）——实现时首个验证
2. dio 直连 v1 CDN 无 CORS（原生层无此限制，应直接通过）
3. 后端解析端点与现有账号池/健康检查/订阅检测联动
4. 断点续传 + 后台下载

## 八、里程碑

- M1：后端解析端点 + Flutter 壳 + 登录 + 搜索/播放（普通曲目）
- M2：Atmos-only eac3 播放验证
- M3：下载（单曲/专辑）+ 本地库
- M4：后台播放 + 锁屏控制 + 管理后台对接

## 九、M1 地基验证结果（2026-08-31，已通过）

### 验证 1：v1 Atmos eac3 流可解码 ✅
- 328631592（Atmos-only）v1 LOW 档 → **eac3，encryptionType=NONE（明文）**
- 26MB 单文件，`amz-pr-fa.audio.tidal.com` 直连 200
- ffprobe：`Dolby Digital Plus + Dolby Atmos`，5.1(side) 48kHz，274.4s 完整时长
- **ffmpeg 转码成 AAC 成功（exit 0）** → 标准解码器可解

### 验证 2：浏览器解不了 eac3，原生能 ✅
- 浏览器 `canPlayType`：eac3 = `''`（空=不支持），ac3 = `''`，**aac = 'probably'**
- 说明：浏览器端确实解不了 E-AC3（这正是之前需要 v2+EME 的原因）
- 原生端：Android MediaCodec 5.0+ 普遍支持 E-AC3；media_kit 基于 libmpv（自带 FFmpeg，含 E-AC3 解码器）→ **ExoPlayer/media_kit 可解**

### 验证 3：v1 明文流原生直连无 CORS ✅
- 原生/非浏览器请求（requests）→ **200，26MB**，无任何 Origin 校验问题
- 证明原生 App 用 dio 直连 v1 CDN 可行

### 结论：路线 B + v1 API 全链路成立
- Atmos-only：v1 明文 eac3 → media_kit 原生解码 → 播放 ✅（无需 v2/DRM/license/转码）
- 普通曲目：v1 明文 FLAC/AAC 单文件直连 ✅
- 下载：v1 明文直连，零服务器带宽 ✅

## 十、M1 后端交付（已上线验证）

### 端点 1：POST /api/mobile/stream（单曲按需，推荐）
- 输入 `{track_id, track_quality}` → 返回该曲 v1 明文流 URL（FLAC/AAC/eac3）
- **一次 Tidal 请求**，App 播放/下载某首时调用 → 限流友好
- 实测：`145738202` → flac/.flac/STEREO @ lgf.audio.tidal.com ✅

### 端点 2：POST /api/mobile/resolve（小批量）
- 输入 `{urls, track_quality}` → 支持 **track/album/playlist/artist/mix**
- **截断上限 MOBILE_RESOLVE_LIMIT=30**：避免大歌单/艺人数百次请求触发限流
- 实测：歌单 60 首 → 截断返回 29 首（未超时）✅
- 实测：专辑 13 首全 FLAC ✅；Atmos-only 单曲 → eac3 明文 ✅

### App 调用约定
- 单曲播放/下载：**/api/mobile/stream**（逐首按需）
- 专辑/歌单浏览：/api/mobile/resolve（小批量 ≤30）；超出部分 App 自行循环调 stream

## 十一、架构决策确认：手机端完全脱离 v2 API

- 手机端（Flutter）**全程 v1 API**：解析用 `mobile/stream`/`mobile/resolve`，音频是 v1 明文 eac3/flac/aac。
- **不碰 v2**：无 v2 manifest、无 EME/license、无 DRM、无转码。
- 凭据隔离不变：App 不接触 Tidal token；后端持账号池 token 调 v1 解析，返回匿名 CDN URL。
- 链路：App → v1 解析(后端) → 明文 URL → App dio 直连 CDN（零服务器带宽）。
- 播放：media_kit（ExoPlayer）原生解 E-AC3，无需 ffmpeg。
- 可选增强（暂不做）：`ffmpeg_kit_flutter` 转 AAC 立体声（体积小、兼容最广），仅当用户要"转码分享"时引入。

## 十二、Flutter 编译修复（Linux 桌面首次构建）

- media_kit 1.2.6 `PlayerStream` **无 `playbackState`** → 改用 `playing` + `position` 流驱动刷新
- `Slider` 的 `clamp(1, 1<<53)` 类型错误（int→double）→ 用 `toDouble()` 规范化
- 删除 `flutter create` 默认计数器测试（引用不存在的 `MyApp`）
- 清理未用变量/const 优化
- `flutter analyze` **No issues found** ✅

## 十三、M1 里程碑：Linux 桌面播放验证通过 ✅

- 用户在 Linux 桌面 `flutter run -d linux` 验证：**播放功能正常**
- media_kit 成功解码 v1 明文 FLAC 和 Atmos eac3
- 关键结论：**手机端纯 v1 + 零带宽方案成立**（无 v2、无 DRM、无转码）

## 十四、专辑/歌单批量下载（已实现）

- 搜索页：`album` 结果右侧显示**下载全部**按钮
- `DownloadsScreen.downloadMany`：逐首串行调 `startDownload`（复用 dio 直连 v1 URL，零服务器带宽）
  - 已存在文件自动跳过
  - 串行避免并发触 CDN 限流
- 依赖 `resolve`（album ≤30 首用 resolve 一次拿全部 URL；大歌单后续可改 stream 逐首）
- 重构：`startDownload` 改为接收 `ScaffoldMessengerState?`（消除 BuildContext 跨 async gap 的 lint）
- `flutter analyze` **No issues found** ✅

## 十五、三栏横滑 UX 落地（已完成 + 编译通过）

### 布局
- HomeScreen = PageView：左栏(队列/收藏/关注) / 中栏(正在播放) / 右栏(歌词/信息)
- 中间为锚点;左↔中↔右往返,不直穿;底部三颗指示点;左/右栏有"回播放"悬浮球
- 左栏头部:下载 + 设置入口(底部面板:服务器地址/默认音质/登出)

### 完整复刻网页版联动
- 队列:单曲 + 专辑混排,专辑折叠组(封面/曲数/收藏/移除/下载全部),可展开
- 收藏:两级(单曲/专辑);收藏专辑自动吸附单曲;专辑内曲目可排除(划线);软删除+UNDO
- 三态:单曲 +/✓;专辑 +/✓实/✓半(计数);加入/整张移除
- 关注:艺术家列表
- 持久化:队列/收藏/关注自动防抖保存(800ms);播放自动切歌(解析URL)
- 歌词:新增 /api/mobile/lyrics 端点,右栏显示(失败优雅空)

### 后端新增
- /api/mobile/lyrics/{track_id}(歌词/字幕/rtl)
- /api/mobile/stream|resolve 返回 album_id(专辑分组/下载用)
- 修复 tiddl core ApiError 构造崩溃(**kwargs 吸收 timestamp 等额外字段)

### 质量
- flutter analyze: No issues found ✅
- flutter build linux --debug: ✓ 编译通过 ✅

## 十六、三栏横滑重构（按用户新设计）

### 操作逻辑(PageView 天然实现)
- **左滑(手指从右往左) → 打开右侧面板**: 信息 / 下载器
- **右滑(手指从左往右) → 打开左侧面板**: 播放列表 / 收藏夹 / 艺术家
- 中间 = 正在播放(锚点)

### 左栏: 播放列表 / 收藏夹 / 艺术家(关注并入)
- 关注列表并进艺术家 Tab;点开艺人 → 详情页(专辑/单曲/参与曲目,可加队列/关注)
- 搜索结果 artist 类型可点开详情页
- 新增 ArtistDetailScreen + ApiClient.artist()

### 右栏: 信息 / 下载器
- 信息: 当前曲目详情(封面/标题/艺术家/专辑/时长)
- 下载器: 任务列表 + **已完成本地库**(扫描下载目录,播放/删除)

### 中栏: 正在播放 + 歌词覆盖层(cover-lyrics)
- 歌词从右栏移入中栏,点击封面切换歌词覆盖(网页版同款)

## 十七、网页版登录修复：会话持久化（消除"频繁要求登录"）

### 根因
- 平台会话 **仅存内存**（SessionStore 是普通 dict），**服务器一重启全部失效**
- 服务器重启 → 所有用户 cookie 失效 → 网页端频繁要求重新登录

### 修复（tiddl/web/users.py）
- 会话**持久化到磁盘**（`~/.tiddl/sessions.json`），重启后自动加载
- **滑动续期**：活跃会话每次访问自动续期（7 天窗口），不会固定到期被登出
- 磁盘写入做 5 秒节流，避免每次请求都写文件
- 原子写（tmp + replace），防文件损坏

### 验证
- 回归测试 2 条：`test_session_persistence_survives_store_recreation`（重启存活）、`test_session_sliding_renewal`（滑动续期）
- 端到端：登录 → 重启服务 → 原 cookie 请求 `/api/user/me` 仍 **200**
- 全量测试 **129 passed**

## 十八、网页版下载配额 + systemFacts 精简

### 下载配额(每用户 12h 2GB)
- `users.py`：`User.download_usage` 持久化字段 + `DOWNLOAD_QUOTA_BYTES`(2GB)/`DOWNLOAD_QUOTA_WINDOW`(12h)
- `UsersStore` 方法：`record_download_bytes` / `download_usage_bytes` / `download_remaining_bytes`(滑动窗口,持久化防重启绕过)
- `app.py`：Job 加 `username`；`/api/downloads` 创建前检查剩余配额(超限 429,优先于账号检查)；`run_job` 完成时按实际 `job.downloaded` 记账；`/api/status` 返回 `quota_*` 字段

### systemFacts 精简 + 配额进度条
- 移除普通用户不需要的技术字段:Python 版本、ffmpeg 状态、本地服务、ATP 版本
- 保留:Tidal 登录、磁盘可用、运行任务、下载路径
- 新增:**下载配额进度条**(quota-fact,显示 已用/总额 + 进度条)
