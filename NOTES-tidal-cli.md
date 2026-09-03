# tidal-cli 安装 · 认证 · 播放 全流程记录

> 状态：**已完成落地**。以下均为本机（CachyOS x86_64）实测。
> 日期：2026-08-31
> 仓库：https://github.com/lucaperret/tidal-cli （npm 包 `@lucaperret/tidal-cli`，MIT）

---

## 一、环境

| 项 | 值 |
|---|---|
| 系统 | CachyOS x86_64（Arch 系） |
| Node.js | v26.7.0 |
| npm | 12.0.2 |
| 桌面 | KDE Wayland（DISPLAY=:0 / WAYLAND_DISPLAY=wayland-0） |
| 音频 | PipeWire 1.6.8，唯一设备 = Radeon HDMI（HD-Audio Generic，卡1），默认 sink 为 **Dummy Output（auto_null）** |
| 显示器 | 仅 eDP-1 内置屏，无 HDMI 显示设备连接 |

---

## 二、安装

```bash
# 官方 README 推荐方式（全局安装）
sudo npm install -g @lucaperret/tidal-cli
# → added 8 packages，exit 0

# 验证
which tidal-cli        # /usr/bin/tidal-cli
tidal-cli --help       # 全部命令组正常输出
npm ls -g @lucaperret/tidal-cli   # 实际安装版本 1.2.5
```

- **要求**：Node.js >= 20 ✅（本机 26.7.0）
- **注意**：`tidal-cli --version` 显示 `1.0.0` 是上游硬编码在 `dist/index.js` 里的，与真实版本（1.2.5）不符，属上游 bug，不影响使用。
- 临时克隆仓库 `git clone --depth 1 https://github.com/lucaperret/tidal-cli.git` 用于查 README/package.json，已清理。

---

## 三、认证（OAuth Authorization Code + PKCE）

命令：`tidal-cli auth`（交互式，阻塞等待回调）

流程细节（见 `dist/auth.js`）：
- 客户端 ID：`PYVtmSHMTGI9oBUs`（公开，非机密，用 PKCE 而非 client_secret）
- scopes：`collection.read/write`、`playlists.read/write`、`playback`、`user.read`、`recommendations.read`、`entitlements.read`、`search.read/write`
- 回调：本地起 HTTP server 监听 `http://localhost:17893/callback`
- 浏览器自动打开（`xdg-open`）；若未打开可手动访问控制台打印的 login URL
- 成功回调后显示 "You're in" 页面

执行结果：
```
Opening browser for Tidal authorization...
If the browser doesn't open, visit: https://login.tidal.com/authorize?client_id=PYVtmSHMTGI9oBUs&...
Waiting for authorization...
Authenticated successfully! User ID: 208978338
```

验证：
```bash
tidal-cli user profile
#  ID: 208978338
#  Username: xtq0669969@lusvip.com
#  Country: HK
#  Email: xtq0669969@lusvip.com

tidal-cli search track "Daft Punk" --json   # 正常返回结果 ✅
```

**凭据存储**：`~/.tidal-cli/session.json`（权限 0600，**加密** —— 内容是 salt/key/data/counter 结构，非明文 token，属正常设计，由 `dist/session.js` 的 localStorage polyfill 管理）。注销：`tidal-cli logout`。

---

## 四、播放 —— 遇到的 bug 与修复（重点）

### 4.1 首次播放失败：403

```bash
tidal-cli playback play 20115564 --quality HIGH   # Daft Punk - Get Lucky
```
```
Downloading track 20115564 (HIGH, AACLC)...
Error: Failed to download init segment (403)
```

### 4.2 定位根因

`tidal-cli playback url 20115564 --json` 返回的 `initUrl` 里出现 **`&amp;`（HTML 实体转义的 `&`）**：

```
https://sp-ad-cf.audio.tidal.com/mediatracks/...mp4?Policy=...&amp;Signature=...&amp;Key-Pair-Id=...
```

- `tidal-cli` 的 `decodeManifest()` 用正则从 **DASH XML（MPD）** 中提取 `initialization` / `media` 属性 URL，**没有反转义 XML 实体**，把 `&` 原样保留成 `&amp;`。
- 导致 CloudFront 签名 URL 损坏 → CDN 返回 403。

**curl 实证**：
```bash
原始 URL（含 &amp;） → HTTP 403
sed 替换 &amp; → & 后  → HTTP 200
```

### 4.3 补丁（修改本机安装副本）

文件：`/usr/lib/node_modules/@lucaperret/tidal-cli/dist/playback.js`
备份：`/usr/lib/node_modules/@lucaperret/tidal-cli/dist/playback.js.bak`

改动 3 处（`&amp;` → `&`）：
1. `initUrl: initMatch[1].replace(/&amp;/g, "&")`   （DASH init segment）
2. `mediaTemplate: mediaMatch[1].replace(/&amp;/g, "&")` （DASH media 模板）
3. `url: baseUrlMatch[1].replace(/&amp;/g, "&")`   （direct BaseURL 回退）

```bash
# 示例（以 perl 就地替换）
sudo cp .../playback.js .../playback.js.bak
sudo perl -pi -e 's/initUrl: initMatch\[1\],/initUrl: initMatch[1].replace(\/&amp;\/g, "&"),/' .../playback.js
# ... 共 3 处
```

> 建议：若上游修复，可 `npm update -g @lucaperret/tidal-cli` 覆盖本补丁。

### 4.4 修复后播放成功

```bash
tidal-cli playback play 20115564 --quality HIGH
```
```
Downloading track 20115564 (HIGH, AACLC)...
Playing... Press Ctrl+C to stop.   # mpv 完整播放，exit 0
```

- 播放实现（`dist/playback.js`）：请求 `/trackManifests/{id}`（`manifestType=MPEG_DASH, uriScheme=DATA, usage=PLAYBACK`）→ base64 MPD → 下载 init+segments 拼成临时文件（`/tmp/tidal-<id>.mp4` 或 `.flac`）→ `mpv --no-video` 播放，结束后删临时文件。

---

## 五、按链接播放

用户提供 URL `http://tidal.com/track/328631593` → track ID = **328631593**

```bash
tidal-cli track info 328631593
#  Track: [328631593] The Game of Love (Drumless Edition)
#  Artists: Daft Punk
#  Album: Random Access Memories (Drumless Edition)
#  Duration: 5:22 | ISRC: GBDUW2300230

tidal-cli playback play 328631593 --quality HIGH
# → 下载成功，mpv 完整播放（5:22），exit 0 ✅
```

> 关联：此曲目正是 `NOTES-tidal-v2-api.md` 中提到的 "Atmos-only" 曲目（328631592 相邻 ID）。v2 API 下它有普通 AACLC/FLAC 流，tidal-cli 用 HIGH(AACLC) 直接可播。

---

## 六、遗留问题：无实际音频输出（听不到声音）

播放链路完全正常（下载/解码/mpv 均成功），但**本机没有可用物理音频输出**：

```
Audio
 ├─ Devices:  43. Radeon High Definition Audio Controller [alsa]
 ├─ Sinks:  * 91. Dummy Output [vol: 0.95]   ← 虚拟无声 sink
```

原因：
1. 声卡只有 HDMI 0/1/2 数字输出（无模拟输出）
2. 没有连接 HDMI 显示器/功放/耳机 DAC
3. WirePlumber 因无连接设备，未把 HDMI 加载为活动 sink，默认落到 Dummy Output

解决选项（未执行，待用户选择）：
- 连接 HDMI 音频设备（显示器/功放/耳机 DAC）→ PipeWire 自动加载
- 连接 USB 音频适配器（UAC2，即插即用）
- 配置蓝牙音箱（`bluetoothctl` 配对后选为 sink）

---

## 七、常用命令速查

```bash
tidal-cli auth                                   # 登录（OAuth）
tidal-cli user profile                           # 用户信息
tidal-cli search track|artist|album|playlist "<q>"   # 搜索（加 --json）
tidal-cli track info <id>                        # 曲目信息
tidal-cli playback play <id> [--quality LOW|HIGH|LOSSLESS|HI_RES]
tidal-cli playback url <id> --json               # 取流媒体 URL（诊断用）
tidal-cli playback info <id>                     # 播放信息/增益
tidal-cli playlist list / create --name "..."    # 歌单
tidal-cli library ...                            # 收藏库
tidal-cli share track <id>                       # 生成分享链接
tidal-cli logout                                 # 注销
```

---

## 八、涉及的关键文件路径

| 文件 | 说明 |
|---|---|
| `/usr/bin/tidal-cli` | 可执行入口 |
| `/usr/lib/node_modules/@lucaperret/tidal-cli/dist/playback.js` | 已打补丁（&amp;→&） |
| `/usr/lib/node_modules/@lucaperret/tidal-cli/dist/playback.js.bak` | 补丁前备份 |
| `/usr/lib/node_modules/@lucaperret/tidal-cli/dist/auth.js` / `session.js` | OAuth 与凭据存储 |
| `~/.tidal-cli/session.json` | 加密凭据（0600） |
| `/tmp/tidal-<id>.mp4` | 播放时临时下载文件（结束后自动删除） |

## 九、重大结论(2026-08-31,推翻 DRM 假设)

### 决定性验证
- **打补丁后的全局 tidal-cli 用 mpv(无 Widevine)完整播放了 328631592**(真正的 Atmos-only 曲目, 4分34秒, exit 0)
- 也完整播放 328631593(Daft Punk The Game of Love, 5分22秒)
- 结论:**v2 的 AACLC 流对 Atmos-only 曲目是未加密的普通 AAC,可直接播放!**

### 之前误判的原因
- 我在 /tmp/tidal-cli(未打补丁克隆) 拿到的 init/media URL 含 `&amp;` → CloudFront 签名 URL 损坏 → 403/解码失败
- 全局版(/usr/lib/node_modules/...)已打补丁(&amp;→&, 3处) → 200 + 可播
- 之前 ffprobe 看到的 senc/tenc/schm/schi 加密 box + 解码失败 = 因 URL 损坏拿到错误/加密数据所致(或需与 mpv 同样处理)

### 对我们播放器的意义
- 后端 v2 manifest 解析必须做 `&amp;`→`&` 反转义(我已有 html.unescape, 需确认), 即可拿到未加密 AACLC 分片
- 浏览器 `<audio>` 直连这些分片即可零带宽播放 Atmos-only, 无需 EME/Widevine!
