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
