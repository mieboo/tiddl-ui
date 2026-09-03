import pytest

from tiddl.cli.commands.subcommands.search import _display_name
from tiddl.core.api.models import Track


def _track(artists=None, artist=None):
    return Track.model_construct(
        id=1,
        title="Song",
        artists=artists if artists is not None else [],
        artist=artist,
        audioModes=["STEREO"],
    )


def test_display_name_empty_artists_no_crash():
    """P0-10: artists 为空时 _display_name 不应 IndexError。"""
    name = _display_name(_track(artists=[], artist="Solo Artist"))
    assert "Song" in name
    assert "Solo Artist" in name


def test_display_name_no_artist_at_all():
    """P0-10: artists 和 artist 都为空时也不应崩溃。"""
    name = _display_name(_track(artists=[], artist=None))
    assert "Song" in name
