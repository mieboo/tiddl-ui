import pytest
from pathlib import Path

from tiddl.cli.utils.download import get_existing_track_filename


def test_predicts_flac_for_lossless_stereo():
    """LOSSLESS + STEREO → .flac(与实际落盘一致)。"""
    p = get_existing_track_filename("LOSSLESS", "LOSSLESS", Path("song"), audio_mode="STEREO")
    assert p.suffix == ".flac"


def test_predicts_m4a_for_atmos_stream():
    """P0-4: LOSSLESS 但 Atmos(非 STEREO)时,实际落盘是 .m4a,预测必须一致,否则反复重下。"""
    p = get_existing_track_filename("LOSSLESS", "HI_RES_LOSSLESS", Path("song"), audio_mode="DOLBY_ATMOS")
    assert p.suffix == ".m4a"


def test_predicts_m4a_for_high():
    """HIGH → .m4a。"""
    p = get_existing_track_filename("HIGH", "HIGH", Path("song"), audio_mode="STEREO")
    assert p.suffix == ".m4a"


def test_backward_compat_without_audio_mode():
    """不传 audio_mode 时保持旧行为(默认按音质预测)。"""
    p = get_existing_track_filename("LOSSLESS", "LOSSLESS", Path("song"))
    assert p.suffix == ".flac"
