"""Tests for tiddl.web.drm: v2 format selection and browser aac_only detection."""

import pytest

from tiddl.web.drm import V2_QUALITY_FORMATS, browser_prefers_aac, v2_formats_for_quality


class TestV2FormatsForQuality:
    def test_hires_requests_flac_hires_chain(self):
        assert v2_formats_for_quality("HI_RES_LOSSLESS") == ["FLAC_HIRES", "FLAC", "AACLC", "HEAACV1"]

    def test_lossless_requests_flac(self):
        assert v2_formats_for_quality("LOSSLESS") == ["FLAC", "AACLC", "HEAACV1"]

    def test_aac_only_excludes_flac_and_hires(self):
        assert v2_formats_for_quality("HI_RES_LOSSLESS", aac_only=True) == ["AACLC", "HEAACV1"]
        assert v2_formats_for_quality("LOSSLESS", aac_only=True) == ["AACLC", "HEAACV1"]

    def test_aac_only_keeps_aac_qualities_unchanged(self):
        assert v2_formats_for_quality("HIGH", aac_only=True) == ["AACLC", "HEAACV1"]
        assert v2_formats_for_quality("LOW", aac_only=True) == ["HEAACV1", "AACLC"]

    def test_unknown_quality_falls_back_to_aaclc(self):
        assert v2_formats_for_quality("BOGUS") == ["AACLC"]
        assert v2_formats_for_quality("BOGUS", aac_only=True) == ["AACLC"]
        assert v2_formats_for_quality(None) == ["AACLC"]

    def test_every_quality_has_a_nonempty_chain(self):
        for quality in ("LOW", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS"):
            chain = v2_formats_for_quality(quality)
            assert chain, quality
            assert chain == V2_QUALITY_FORMATS[quality]


class TestBrowserPrefersAac:
    @pytest.mark.parametrize(
        "ua",
        [
            # 真实 Firefox UA(桌面与 Android)
            "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
            "Mozilla/5.0 (Android 13; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
            # 真 Safari
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        ],
    )
    def test_aac_preferred_for_firefox_and_safari(self, ua):
        assert browser_prefers_aac(ua) is True

    @pytest.mark.parametrize(
        "ua",
        [
            # Chromium 系:Safari 标记存在但不应误判
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            # Edge / Opera
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0",
            # 非浏览器 / 缺失
            None,
            "",
            "curl/8.5.0",
            "python-requests/2.32.0",
        ],
    )
    def test_aac_not_forced_for_chromium_or_unknown(self, ua):
        assert browser_prefers_aac(ua) is False

    def test_chromium_contains_safari_token_but_is_not_safari(self):
        # Chrome UA 内嵌 "Safari/537.36",必须不被误判为 Safari
        chrome = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        assert browser_prefers_aac(chrome) is False

    def test_firefox_ua_case_insensitive(self):
        assert browser_prefers_aac("MOZILLA/5.0 FIREFOX/127.0") is True


class TestManifestCacheQualitySelection:
    """回归:缓存只存原始 manifest,选档必须按每次 fmt_list 重算。

    线上 bug:缓存曾存「已选档的完整 bundle」,第一次请求(如 LOW)把
    best_rep 固化,后续切 HIGH/LOSSLESS 命中同一缓存返回同一档位
    (表现为切什么音质都变回 320kbps)。
    """

    # 4 档 MPD:FLAC_HIRES(1760365) / FLAC(941436) / AACLC(321708) / HEAACV1(97877)
    MPD = """<?xml version="1.0"?>
    <MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT4M34S">
      <Period>
        <AdaptationSet mimeType="audio/mp4">
          <ContentProtection schemeIdUri="urn:mpeg:dash:mp4protection:2011" value="cenc"
            xmlns:cenc="urn:mpeg:cenc:2013" cenc:default_KID="01234567-89ab-cdef-0123-456789abcdef"/>
          <ContentProtection schemeIdUri="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed">
            <cenc:pssh xmlns:cenc="urn:mpeg:cenc:2013">AAAABHBzc2gAAAAA</cenc:pssh>
          </ContentProtection>
          <Representation id="FLAC_HIRES,1760365,96000,24" codecs="flac" bandwidth="1760365" audioSamplingRate="96000">
            <SegmentTemplate initialization="init-hires.mp4" media="seg-hires-$Number$.mp4"/>
          </Representation>
          <Representation id="FLAC,941436,44100,16" codecs="flac" bandwidth="941436" audioSamplingRate="44100">
            <SegmentTemplate initialization="init.mp4" media="seg-$Number$.mp4"/>
          </Representation>
          <Representation id="AACLC,321708,44100" codecs="mp4a.40.2" bandwidth="321708" audioSamplingRate="44100">
            <SegmentTemplate initialization="init-aac.mp4" media="seg-aac-$Number$.mp4"/>
          </Representation>
          <Representation id="HEAACV1,97877,44100" codecs="mp4a.40.5" bandwidth="97877" audioSamplingRate="44100">
            <SegmentTemplate initialization="init-heaac.mp4" media="seg-heaac-$Number$.mp4"/>
          </Representation>
        </AdaptationSet>
      </Period>
    </MPD>"""

    def _mock_manifest(self, monkeypatch, tmp_path):
        """把 v2_drm_manifest 的网络请求替换成固定 MPD,隔离真实 Tidal。"""
        import base64
        import tiddl.web.drm as drm
        from tiddl.web.drm import _v2_manifest_cache

        _v2_manifest_cache.clear()

        class _FakeResp:
            status_code = 200

            def json(self):
                payload = base64.b64encode(self.MPD.encode()).decode()
                return {"data": {"attributes": {"uri": f"data:application/dash+xml,{payload}"}}}

        fake = _FakeResp()
        fake.MPD = self.MPD

        monkeypatch.setattr(drm, "_tidal_get", lambda *a, **k: fake)
        monkeypatch.setattr(
            drm,
            "account_context",
            lambda account_id=None: type("C", (), {"api": type("A", (), {"client": type("T", (), {"token": "fake"})()})()})(),
        )
        return drm, _v2_manifest_cache

    def test_quality_switch_recomputes_selection_same_cache(self, monkeypatch, tmp_path):
        drm, cache = self._mock_manifest(monkeypatch, tmp_path)
        from tiddl.web.drm import v2_formats_for_quality

        results = []
        for q in ("HI_RES_LOSSLESS", "LOSSLESS", "HIGH", "LOW", "LOSSLESS"):
            b = drm.v2_drm_manifest("track1", "acct1", v2_formats_for_quality(q))
            results.append((q, b.get("format")))
        # 每个档位应返回对应 format,且全程只请求一次 Tidal(缓存命中)
        assert results == [
            ("HI_RES_LOSSLESS", "FLAC_HIRES"),
            ("LOSSLESS", "FLAC"),
            ("HIGH", "AACLC"),
            ("LOW", "HEAACV1"),
            ("LOSSLESS", "FLAC"),
        ]
        # 缓存键与档位无关: 始终同一个键
        assert len(cache) == 1
        # 缓存内容是原始 manifest(含 root),而非选档后的 bundle
        cached_manifest = cache[("acct1", "track1", "ALL")][1]
        assert "root" in cached_manifest
        assert "format" not in cached_manifest  # 选档结果不入缓存
