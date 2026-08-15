# tiddl-ui

[English](README.md) | 简体中文

以最高可用音质下载 Tidal 歌曲和视频。`tiddl-ui` 在原有 Python CLI 基础上增加了本地 Web 下载器和在线播放器。

> [!WARNING]
> 本项目仅供个人使用，与 Tidal 官方无关。用户有责任确保使用方式符合 Tidal 服务条款及所在地版权法律。下载内容仅限个人使用，不得分享或再次分发。开发者不对滥用行为承担责任。

![PyPI - Downloads](https://img.shields.io/pypi/dm/tiddl?style=for-the-badge&color=%2332af64)
![PyPI - Version](https://img.shields.io/pypi/v/tiddl?style=for-the-badge)

# 安装

项目基于 PyPI 上的 [`tiddl`](https://pypi.org/project/tiddl/)，推荐从当前仓库安装带 Web UI 的版本。

> [!IMPORTANT]
> 请先安装 [`ffmpeg`](https://ffmpeg.org/download.html)，它用于将下载的音轨转换为正确格式。

## 从源码安装

```bash
git clone -b web-ui https://github.com/mieboo/tiddl-ui.git
cd tiddl-ui
uv venv
source .venv/bin/activate
uv pip install -e .
```

Windows 激活虚拟环境：

```powershell
.venv\Scripts\activate
```

也可以安装 PyPI 上的原版 CLI：

```bash
uv tool install tiddl
# 或
pip install tiddl
```

# Web 界面

安装完成后启动本地 Web 服务：

```bash
tiddl-ui
```

然后打开 <http://127.0.0.1:8765>。服务默认只监听本机地址。

Web 界面目前支持：

- Tidal 设备授权登录和多账户管理
- 歌曲、专辑等资源的自动预览
- 自动识别各资源支持的音频、视频和 Atmos 规格
- 批量添加 URL，并为每个资源建立独立下载任务
- 实时显示单曲进度、专辑总进度、速度和任务日志
- 搜索 Tidal 曲库并将歌曲或专辑加入下载列表
- 在线播放歌曲和专辑、歌词同步、播放列表及音质选择
- 中文与英文界面、亮色与暗色主题

## 多账户调度

Web 界面可以同时登录多个 Tidal 账户。每个账户使用独立的凭据和 API 缓存。

新下载任务会分配给当前启用且活动任务最少的账户。例如，三个空闲账户处理十个任务时，会按 `4 / 3 / 3` 分配。任务一旦分配，在结束前会保持绑定到该账户。账户组界面会显示用户名和健康状态。

## 在线播放器说明

播放器仅代理在线流，不会把播放内容保存为下载文件。普通 AAC 和 FLAC 流由浏览器原生播放。

部分曲目在 Tidal API 中只返回 Dolby Atmos 的 E-AC-3 或 AC-4 流。Chromium 通常无法直接解码这些格式，目前播放器会给出明确的不兼容提示，不进行 Atmos 转码或伪装成立体声。

# CLI 使用

查看命令：

```bash
tiddl --help
```

主要命令包括：

```text
tiddl auth       管理 Tidal 登录
tiddl download   下载 Tidal 资源
```

## 登录

运行以下命令，并按终端提示完成 Tidal 登录：

```bash
tiddl auth login
```

## 下载

支持歌曲、视频、专辑、艺人、播放列表和 Mix：

```bash
tiddl download url <URL>
```

资源不必填写完整 URL，也可以直接使用：

```bash
tiddl download url track/103805726
tiddl download url album/103805723
```

运行 `tiddl download --help` 查看全部下载选项。

### Dolby Atmos

默认的 `--dolby-atmos none` 表示排除 Atmos，而不是“不使用过滤器”。允许下载 Atmos 流：

```bash
tiddl download url <URL> --dolby-atmos allow
```

只下载 Atmos：

```bash
tiddl download url <URL> --dolby-atmos only
```

### 音质

| 档位 | 扩展名 | 规格 |
| :---: | :---: | :---: |
| LOW | `.m4a` | 96 kbps |
| NORMAL | `.m4a` | 320 kbps |
| HIGH | `.flac` | 16-bit / 44.1 kHz |
| MAX | `.flac` | 最高 24-bit / 192 kHz |

### 输出路径

可以通过模板设置文件名和目录。例如：

```text
{album.artist}/{album.title}/{item.number:02d}. {item.title}
```

将生成类似结构：

```text
Music/
└── Artist/
    └── Album/
        ├── 01. Track.flac
        └── 02. Track.flac
```

模板语法详见 [docs/templating.md](docs/templating.md)。

# 配置

应用数据默认存放在 `~/.tiddl`。可以创建 `config.toml` 调整下载目录、音质和其他默认行为，参考 [docs/config.example.toml](docs/config.example.toml)。

## 自定义应用目录

通过 `TIDDL_PATH` 指定其他数据目录：

```bash
TIDDL_PATH=~/custom/tiddl tiddl auth login
```

## 自定义认证凭据

认证失效时，可以通过环境变量指定其他客户端凭据：

```text
TIDDL_AUTH=<CLIENT_ID>;<CLIENT_SECRET>
```

# 开发

```bash
git clone -b web-ui https://github.com/mieboo/tiddl-ui.git
cd tiddl-ui
uv venv
source .venv/bin/activate
uv pip install -e .
pytest -q
```

# 相关资源

- [Tidal API Wiki](https://github.com/Fokka-Engineering/TIDAL)
- [Tidal Media Downloader](https://github.com/yaronzz/Tidal-Media-Downloader)
- [tiddl 上游项目](https://github.com/oskvr37/tiddl)
