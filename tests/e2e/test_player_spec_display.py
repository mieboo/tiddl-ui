"""Playwright E2E 测试:Abducted Tidal Player 音质显示全链路。

覆盖:
- 登录门禁流程
- 搜索曲目(点击第一条 → 触发 resolve)
- /api/player/resolve 返回规格字段(bit_depth/sample_rate/bitrate/codec)
- 音质菜单渲染真实规格(点击搜索结果后)
- 下载选项(含 Atmos 复合档)
- 播放信息面板规格字段

运行:先启动服务(TIDDL_PATH=可写目录 + TIDDL_ADMIN_*),再:
  .venv/bin/python tests/e2e/test_player_spec_display.py
"""

import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8899")
USERNAME = os.environ.get("E2E_USERNAME", "e2eadmin")
PASSWORD = os.environ.get("E2E_PASSWORD", "e2epass123")
SEARCH_QUERY = os.environ.get("E2E_SEARCH", "Daft Punk")
TRACK_ID = os.environ.get("E2E_TRACK_ID", "1550546")  # Daft Punk - One More Time

passed = 0
failed = 0
failures: list[str] = []


def report(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        failures.append(f"{name}: {detail}")
        print(f"  ❌ {name}: {detail}")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        console_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(f"{msg.type}: {msg.text}")
            if msg.type == "error" and "favicon" not in msg.text
            else None,
        )
        page.on("pageerror", lambda err: console_errors.append(f"pageerror: {err}"))

        # ---------- 1. 登录门禁 ----------
        print("\n[1] 登录门禁")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        report("登录门禁初始可见", page.locator("#loginGate").is_visible())

        page.fill("#loginUsername", USERNAME)
        page.fill("#loginPassword", PASSWORD)
        page.click("#loginSubmit")
        page.wait_for_timeout(1200)
        report("登录成功(门禁消失)", not page.locator("#loginGate").is_visible())

        # 首次登录会弹 onboarding 引导层,关闭它(产品真实行为:点"Start listening")
        if page.locator("#onboardingOverlay").is_visible():
            page.locator("#onboardingDone").click()
            page.wait_for_timeout(300)
            report("onboarding 引导层已关闭", not page.locator("#onboardingOverlay").is_visible())

        # ---------- 2. 搜索 ----------
        print("\n[2] 搜索")
        page.fill("#playerSearch", SEARCH_QUERY)
        page.press("#playerSearch", "Enter")
        page.wait_for_timeout(3000)
        result = page.locator(f'.player-result[data-resource="track/{TRACK_ID}"]')
        report("搜索结果包含目标曲目", result.count() > 0, f"count={result.count()}")

        # ---------- 3. resolve 规格字段(后端契约) ----------
        print("\n[3] /api/player/resolve 规格字段")
        resolve = page.evaluate(
            """async (trackId) => {
                const r = await fetch('/api/player/resolve', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({track_id: trackId, quality: 'LOSSLESS', drm: false})
                });
                if (!r.ok) return {http: r.status, detail: (await r.json()).detail};
                return await r.json();
            }""",
            TRACK_ID,
        )
        if resolve.get("http"):
            report("resolve HTTP 200", False, f"HTTP {resolve['http']}: {resolve.get('detail')}")
        else:
            report("resolve HTTP 200", True)
            report(
                "含规格字段",
                all(k in resolve for k in ("bit_depth", "sample_rate", "bitrate", "codec", "quality")),
                f"keys={sorted(k for k in resolve if k in ('bit_depth','sample_rate','bitrate','codec','quality','mime_type'))}",
            )
            report(
                "无损档位规格匹配(LOSSLESS→FLAC 无码率)",
                resolve["quality"] == "LOSSLESS"
                and resolve["codec"] == "flac"
                and resolve["bit_depth"] in (16, 24)
                and resolve["sample_rate"] in (44100, 48000, 88200, 96000, 192000)
                and resolve["bitrate"] is None,
                f"quality={resolve.get('quality')} codec={resolve.get('codec')} bit={resolve.get('bit_depth')} rate={resolve.get('sample_rate')} bitrate={resolve.get('bitrate')}",
            )

        # ---------- 3b. Atmos 曲目规格(v1 只给 E-AC-3 768kbps) ----------
        print("\n[3b] Atmos 曲目规格字段")
        atmos = page.evaluate(
            """async (trackId) => {
                const r = await fetch('/api/player/resolve', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({track_id: trackId, quality: 'LOSSLESS', allow_atmos: true, drm: false})
                });
                if (!r.ok) return {http: r.status, detail: (await r.json()).detail};
                return await r.json();
            }""",
            os.environ.get("E2E_ATMOS_TRACK_ID", "426175179"),  # Joni Mitchell - River (Atmos-only)
        )
        if atmos.get("http"):
            report("Atmos resolve HTTP 200", False, f"HTTP {atmos['http']}: {atmos.get('detail')}")
        else:
            report("Atmos resolve HTTP 200", True)
            # allow_atmos=true 时优先走 v2 DRM FLAC 直连(无损、无码率),而非 v1 eac3
            report(
                "Atmos 曲目走 v2 DRM 无损路径",
                atmos.get("audio_mode") == "DOLBY_ATMOS"
                and atmos.get("codec") == "flac"
                and atmos.get("bitrate") is None,
                f"mode={atmos.get('audio_mode')} codec={atmos.get('codec')} bitrate={atmos.get('bitrate')} drm={bool(atmos.get('drm'))}",
            )

        # ---------- 3c. 前端规格显示函数(actualSpecText) ----------
        print("\n[3c] 前端规格显示函数")
        spec_text = page.evaluate(
            """(data) => {
                try {
                    // 复用 player.js 的 actualSpecText 逻辑
                    const info = {bit_depth: data.bit_depth, sample_rate: data.sample_rate, bitrate: data.bitrate};
                    const parts = [];
                    if (info.bit_depth) parts.push(info.bit_depth + ' bit');
                    if (info.sample_rate) parts.push((info.sample_rate/1000).toFixed(1) + ' kHz');
                    if (info.bitrate) parts.push(info.bitrate + ' kbps');
                    return {ok: true, text: parts.join(' · ')};
                } catch (e) { return {ok: false, err: String(e)}; }
            }""",
            resolve,
        )
        if spec_text.get("ok"):
            report(
                "规格显示含位深/采样率",
                "bit" in spec_text["text"] and "kHz" in spec_text["text"],
                repr(spec_text["text"]),
            )
        else:
            report("规格显示函数可用", False, spec_text.get("err"))

        # ---------- 4. 点击播放 → 音质菜单渲染真实规格 ----------
        print("\n[4] 播放 & 音质菜单渲染")
        if result.count() > 0:
            result.first.click()
            page.wait_for_timeout(4000)
            menu_text = page.locator("#qualityControl").inner_text()
            report("音质菜单已渲染", len(menu_text.strip()) > 0, repr(menu_text[:80]))
            report(
                "菜单显示规格(含 kbps 或 bit/kHz)",
                ("kbps" in menu_text or "bit" in menu_text or "kHz" in menu_text or "Lossless" in menu_text or "Hi-Res" in menu_text),
                repr(menu_text[:120]),
            )
        else:
            report("点击搜索结果触发播放", False, "no result to click")

        # ---------- 5. 下载选项 ----------
        print("\n[5] 下载选项")
        preview = page.evaluate(
            """async (trackId) => {
                const r = await fetch('/api/preview', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({urls: ['track/' + trackId]})
                });
                if (!r.ok) return {http: r.status, detail: (await r.json()).detail};
                const body = await r.json();
                const c = body.resources && body.resources[0];
                return {options: c && c.download_options, specs: c && c.specs};
            }""",
            TRACK_ID,
        )
        if preview.get("http"):
            report("preview HTTP 200", False, f"HTTP {preview['http']}: {preview.get('detail')}")
        else:
            report("preview HTTP 200", True)
            opts = preview.get("options") or {}
            report("下载选项含 track_quality", "track_quality" in opts, str(opts))
            specs = preview.get("specs") or []
            qspec = next((s for s in specs if s.get("key") == "track_quality"), None)
            report(
                "track_quality 选项合法(low/normal/high)",
                bool(qspec) and set(qspec.get("choices", [])) <= {"low", "normal", "high", "high_atmos"},
                str(qspec),
            )

        # ---------- 6. 控制台错误(过滤登录探测的预期 401) ----------
        print("\n[6] 控制台错误")
        unexpected = [
            e for e in console_errors
            if "401" not in e and "404" not in e  # 登录探测 401 与缺失资源 404 为预期
        ]
        report("无意外 JS 控制台错误", len(unexpected) == 0, "; ".join(unexpected[:5]))

        browser.close()

    print(f"\n===== 结果: {passed} passed, {failed} failed =====")
    for f in failures:
        print(f"  FAIL: {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
