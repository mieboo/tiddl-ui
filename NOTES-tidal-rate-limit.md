# Tidal API 限流分析与规避策略

> 日期：2026-08-31
> 来源：本会话大量实测（v2 trackManifests / license / 分片 / 健康探测）+ 代码审计
> 状态：分析结论已固化，供持续参考与加固

---

## 一、Tidal 的限流防护体系（三层）

Tidal 对 API 的访问限制不是一个单一阈值，而是**三层叠加**，各自触发条件不同：

### 1. DataDome 反爬层（最外层、最致命）
- **载体**：`listen.tidal.com` 网页、部分 API/CDN 路径
- **信号**：`ERR_CONNECTION_CLOSED`（连接被重置）、`geo.captcha-delivery.com/captcha` 验证码页、请求超时
- **触发因素**：无头浏览器指纹、数据中心 IP、高频请求、无会话 cookie
- **实测**：
  - 无头 Chromium 访问 `listen.tidal.com` → 被 DataDome 验证码拦截
  - iframe 嵌 Tidal 页 → 同样被验证码拦截
  - 高频探测 v2 API 期间出现 `ERR_CONNECTION_CLOSED` / 连接超时
  - **换 IP（VPN）后恢复** → 确认 IP 是重要维度

### 2. 账号级速率限制（API 层）
- **载体**：`api.tidal.com/v1`、`openapi.tidal.com/v2` 业务端点
- **信号**：429（Too Many Requests）、超时、JSON 解码失败后重试仍失败
- **触发因素**：同一 token 在短窗口内请求过多（搜索/详情/manifest）
- **实测**：连续大量下载分片或重复请求 manifest 会触发超时/连接异常

### 3. CDN 分片访问控制（内容层）
- **载体**：`sp-ad-cf.audio.tidal.com`、`amz-pr-fa.audio.tidal.com` 等音频 CDN
- **信号**：403
- **触发因素**：
  - **带自定义头/Range** → 触发 CORS 预检 → 被拒（403）
  - **服务端/数据中心 IP 直取** → 403（只能由浏览器会话访问）
  - 签名 URL 过期（CloudFront Policy 时效，约 1 小时）
- **实测**：浏览器纯 GET（简单请求、无自定义头）→ 200；带 Range → 403；服务端任意 Origin → 403

---

## 二、触发限流的具体行为（实测对照）

| 行为 | 后果 | 是否可规避 |
|---|---|---|
| 高频连续请求 v2 manifest（<10s 间隔）| ERR_CONNECTION_CLOSED / 超时 | ✅ 加间隔+退避 |
| 一次性下载几十个分片 | 超时（CDN 逐步放慢）| ✅ 渐进按需下载 |
| 无头 UA / 数据中心 IP 访问网页或 CDN | 验证码 / 403 | ✅ 真实浏览器会话 |
| 带 Range/自定义头 fetch 分片 | 403（CORS）| ✅ 改纯 GET |
| 同一 token 短窗口内大量搜索/详情 | 429 / 超时 | ✅ 节流+缓存 |
| 单次正常请求（间隔足够）| 稳定 200 | — |

**关键结论**：Tidal 的限流是**"行为驱动"**的——单次请求、低频请求稳定；高频、无头、数据中心 IP 才会触发。我们已实测的所有关键操作（v2 manifest、license、浏览器直连分片）**在合理节流下都是稳定的**。

---

## 三、规避策略（按重要性排序）

### 1. 客户端节流（最重要）
- **所有后端 Tidal 请求加最小间隔**：默认 ≥2s，v2 manifest/license ≥5-10s
- **信号量/令牌桶**：保证同账号 token 并发请求数 ≤2，全局 ≤5
- **429/连接异常退避**：指数退避（1s → 2s → 4s → 8s），最多 3-5 次

### 2. 请求去重与缓存
- v1 详情/搜索已有 `requests_cache`（3600s），**保持并扩大覆盖面**
- v2 manifest：对同一曲目短窗口内缓存（如 30-60s），避免重复拉取
- 健康/订阅探测：**低频 + 错峰**（已实现：60s 健康、10 轮订阅、逐账号间隔 15s）

### 3. 会话与身份
- 统一真实浏览器 UA + `Referer: https://tidal.com/`
- 分片：**永远用浏览器纯 GET**（简单请求），不在服务端拉分片
- 账号池：`select_account` 多账号轮换（天然分摊单 token 压力）

### 4. 失败降级
- 单账号健康检查失败 → 标记 degraded → 自动切换其他账号
- 订阅检测失败 → 保持 enabled 但记录，不误杀（避免把网络抖动当过期）

### 5. IP 维度
- 后端出网 IP 尽量用住宅/稳定 IP（避免频繁换数据中心 IP）
- 若被 DataDome 标记：等待冷却 + 换 IP（实测有效）

---

## 四、代码现状审计

| 位置 | 现状 | 建议 |
|---|---|---|
| `TidalClient.fetch` | 401 重试 + JSON 解码重试（2s）| ✅ 保留；补充 429/连接异常退避 |
| v1 业务端点 | `requests_cache` 3600s 缓存 | ✅ 好 |
| `v2_drm_manifest`（app.py 1036）| **无节流、无缓存、无重试** | ⚠️ 需加（高价值）|
| `drm_license`（app.py 1890）| 无节流 | ⚠️ 需加 |
| 订阅检测 `probe_subscription` | 低频 + 逐账号 15s 间隔 | ✅ 好 |
| 健康检测 `health_monitor` | 60s 一轮 | ✅ 好 |
| 分片下载（前端）| 浏览器纯 GET 渐进 | ✅ 最优 |

**最高优先级加固**：
1. 全局最小间隔（节流器）
2. v2 manifest + license 加退避重试与短缓存
3. 429/ERR_CONNECTION_CLOSED 统一识别 → 指数退避

---

## 五、一句话总结

> **"低频、真实浏览器会话、纯 GET 分片、多账号分摊、失败退避"** —— 这五件事做好，Tidal 限流基本不会成为问题；当前实现已覆盖大部分，剩 v2 manifest/license 两处直连请求需要补节流与退避。
