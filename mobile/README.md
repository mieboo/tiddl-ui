# ATP Mobile（Flutter 客户端）

Abducted Tidal Player 的原生手机客户端。**路线 B：Flutter + v1 API**。

- 原生直连 Tidal CDN（dio，无 CORS），**零服务器带宽**
- media_kit（ExoPlayer）原生解码 **E-AC3 / FLAC / AAC**（含 Dolby Atmos）
- 下载走 **v1 明文流**（FLAC/AAC/eac3），不受 DRM 限制
- 后端仅做 URL 解析与账号池管理，不转发音频字节

## 目录结构

```
lib/
 ├─ main.dart            # 入口(初始化 MediaKit/配置/会话)
 ├─ core/                # config(服务器地址)、api_client(API)、theme(主题)
 ├─ auth/                # 登录(含 2FA)、会话
 ├─ home/                # 底部导航(搜索/下载/设置)
 ├─ browse/              # 搜索页
 ├─ player/              # 播放页(media_kit)
 ├─ downloads/           # 下载(dio 直连,进度)
 └─ settings/            # 设置(服务器地址/账号/登出)
```

## 运行前提

- 本机安装 Flutter 3.x + Android SDK
- 后端已启动（`uv run tiddl-ui`，监听 `0.0.0.0:8765` 以允许手机访问）
- 已有平台用户账号（管理后台创建）

## 步骤

```bash
cd mobile
flutter pub get
flutter run   # 连接 Android 设备/模拟器
```

首次启动在登录页可修改服务器地址：
- Android 模拟器访问宿主机：`http://10.0.2.2:8765`
- 真机访问局域网：`http://<电脑局域网IP>:8765`（后端需 `TIDDL_HOST=0.0.0.0` 启动）

## Android 明文 HTTP 配置

后端为 `http://`（非 https），需在 `android/app/src/main/AndroidManifest.xml`
的 `<application>` 上允许明文流量：

```xml
<application
    android:usesCleartextTraffic="true"
    ...>
```

（生产可改为 https + 反向代理，避免明文。）

## 依赖

| 包 | 用途 |
|---|---|
| dio | 原生网络：直连 CDN、断点下载 |
| media_kit + media_kit_libs_video | ExoPlayer 封装，解 E-AC3/FLAC/AAC |
| provider | 状态管理 |
| shared_preferences | 服务器地址/偏好持久化 |
| path_provider | 下载目录 |
