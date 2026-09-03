import asyncio
import time
from pydantic import ValidationError
import pytest
from types import SimpleNamespace

from tiddl.web.app import (
    DownloadRequest,
    Job,
    ResourceDownloadOptions,
    download_command,
    format_duration,
    handle_output_line,
    image_url,
    player_quality_tiers,
    player_sessions,
    player_speed,
    search_result,
    select_account,
    AccountHealth,
    PlayerSession,
    account_health,
    available_account_ids,
    check_account_health,
    detect_download_options,
)
from tiddl.web.player import is_protected_stream


def test_is_protected_stream_gate():
    """明文/直连门禁:仅 manifest 的 encryptionType 判定,缺省视为明文。"""
    assert is_protected_stream({}) is False
    assert is_protected_stream({"encryptionType": "NONE"}) is False
    assert is_protected_stream({"encryptionType": ""}) is False
    assert is_protected_stream({"encryptionType": "CENC"}) is True
    assert is_protected_stream({"encryptionType": "SAMPLE_AES"}) is True


def test_player_quality_tiers_fall_back_from_requested_ceiling():
    assert player_quality_tiers("HI_RES_LOSSLESS") == [
        "HI_RES_LOSSLESS", "LOSSLESS", "HIGH", "LOW"
    ]
    assert player_quality_tiers("HIGH") == ["HIGH", "LOW"]


def make_player_session(session_id: str, expired: bool = False, bytes_served: int = 0) -> PlayerSession:
    return PlayerSession(
        id=session_id,
        track_id="42",
        account_id="a" * 10,
        url="https://stream.test/audio",
        mime_type="audio/flac",
        codec="flac",
        quality="LOSSLESS",
        audio_mode="STEREO",
        bit_depth=16,
        sample_rate=44100,
        expires_at=time.time() - 1 if expired else time.time() + 60,
        bytes=bytes_served,
    )


def test_player_speed_reports_session_bytes_and_expiry():
    live = make_player_session("alive1", bytes_served=2048)
    player_sessions[live.id] = live
    try:
        assert asyncio.run(player_speed("alive1")) == {"bytes": 2048, "expired": False}
    finally:
        player_sessions.pop("alive1", None)

    finished = make_player_session("done1", expired=True, bytes_served=4096)
    player_sessions[finished.id] = finished
    try:
        assert asyncio.run(player_speed("done1")) == {"bytes": 4096, "expired": True}
    finally:
        player_sessions.pop("done1", None)


def test_player_speed_rejects_unknown_session():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        asyncio.run(player_speed("missing"))
    assert exc.value.status_code == 404


def test_page_responses_version_static_assets():
    from tiddl.web.app import page_response

    spa_html = page_response("spa.html").body.decode()

    assert "/static/player.js?v=" in spa_html
    assert "/static/app.js?v=" in spa_html
    assert "/static/router.js?v=" in spa_html
    assert '"/static/player.js"' not in spa_html
    assert '"/static/styles.css"' not in spa_html
    assert spa_html.count('id="languageSelect"') == 1
    assert 'id="view-downloads"' in spa_html
    assert 'id="view-player"' in spa_html
    assert page_response("spa.html").headers["cache-control"] == "no-cache"


def test_lan_addresses_keep_only_private_ipv4(monkeypatch):
    from tiddl.web.app import lan_addresses

    monkeypatch.setattr(
        "tiddl.web.app.candidate_ips",
        lambda: ["127.0.0.1", "8.8.8.8", "198.18.0.1", "169.254.3.4", "192.168.1.5", "10.1.2.3", "172.20.0.1", "172.33.0.9"],
    )

    assert lan_addresses(8765) == [
        "http://192.168.1.5:8765",
        "http://10.1.2.3:8765",
        "http://172.20.0.1:8765",
    ]


def test_download_request_accepts_tidal_resources():
    request = DownloadRequest(
        urls=[" album/103805723 ", "https://tidal.com/browse/track/103805724"]
    )

    assert request.urls == [
        "album/103805723",
        "https://tidal.com/browse/track/103805724",
    ]


def test_download_request_accepts_track_nested_under_album_url():
    url = "https://tidal.com/album/547537326/track/547537333"

    assert DownloadRequest(urls=[url]).urls == [url]


def test_download_request_rejects_non_tidal_url():
    with pytest.raises(ValidationError):
        DownloadRequest(urls=["https://example.com/track/123"])


def test_progress_event_updates_public_job_state():
    job = Job(
        id="job",
        kind="download",
        label="Album",
        command=["private"],
        account_id="account-a",
        env={"TIDDL_AUTH_FILE": "private"},
        subtitle="Artist",
        cover="https://example.test/cover.jpg",
        resource_type="album",
    )

    handle_output_line(
        job,
        'TIDDL_EVENT {"event":"download_progress","title":"Track",'
        '"downloaded":1024,"total":2048,"speed":512,"progress":0.5,'
        '"segment":1,"segment_count":1}',
    )

    public = job.public()
    assert public["current_item"] == "Track"
    assert public["progress"] == 0.5
    assert public["speed"] == 512
    assert public["account_id"] == "account-a"
    assert public["subtitle"] == "Artist"
    assert public["cover"] == "https://example.test/cover.jpg"
    assert public["resource_type"] == "album"
    assert "command" not in public
    assert "env" not in public


def test_resource_progress_is_tracked_separately_from_current_item():
    job = Job(id="job", kind="download", label="Album", command=[])
    handle_output_line(
        job,
        'TIDDL_EVENT {"event":"download_progress","title":"Track",'
        '"downloaded":512,"total":1024,"speed":256,"progress":0.5}',
    )
    handle_output_line(
        job,
        'TIDDL_EVENT {"event":"resource_progress","completed":3,"total":10}',
    )

    public = job.public()
    assert public["progress"] == 0.5
    assert public["resource_completed"] == 3
    assert public["resource_total"] == 10


def test_tidal_image_url_and_duration_format():
    assert image_url("05f8dc0e-260a-469f-8635-272daa77130f") == (
        "https://resources.tidal.com/images/05f8dc0e/260a/469f/8635/"
        "272daa77130f/320x320.jpg"
    )
    assert format_duration(195) == "3:15"
    assert format_duration(3723) == "1:02:03"


def test_search_result_can_be_added_as_download_resource():
    item = SimpleNamespace(
        id=42,
        title="Result",
        artists=[SimpleNamespace(name="Artist")],
        album=SimpleNamespace(cover="cover-id"),
        explicit=True,
    )

    result = search_result(item, "track")

    assert result["resource"] == "track/42"
    assert result["subtitle"] == "Artist"
    assert result["cover"].endswith("/160x160.jpg")


def test_player_track_carries_artist_id():
    from tiddl.web.app import player_track

    track = SimpleNamespace(
        id=7,
        title="Song",
        artists=[SimpleNamespace(id=99, name="Artist")],
        album=SimpleNamespace(id=5, title="Album", cover="cover"),
        duration=180,
        explicit=False,
        mediaMetadata=SimpleNamespace(tags=["LOSSLESS"]),
        audioModes=["STEREO"],
    )

    payload = player_track(track)

    assert payload["artist_id"] == "99"
    assert payload["artist"] == "Artist"


def test_player_artist_overview_shapes_albums_and_singles(monkeypatch):
    from datetime import datetime
    from tiddl.web.app import player_artist

    release = SimpleNamespace(
        id=3,
        title="Release",
        artists=[SimpleNamespace(name="Artist")],
        cover="abc-def",
        duration=200,
        releaseDate=datetime(2013, 5, 17),
    )

    class Api:
        def get_artist(self, artist_id):
            return SimpleNamespace(name="Artist", picture="pic-id")

        def get_artist_albums(self, artist_id, limit=100, filter="ALBUMS"):
            return SimpleNamespace(items=[release] if filter == "ALBUMS" else [])

    monkeypatch.setattr("tiddl.web.app.available_account_ids", lambda: ["a" * 10])
    monkeypatch.setattr("tiddl.web.app.account_context", lambda account_id=None: SimpleNamespace(api=Api()))

    overview = asyncio.run(player_artist("99"))

    assert overview["name"] == "Artist"
    assert overview["picture"].endswith("/320x320.jpg")
    assert overview["albums"][0]["id"] == "3"
    assert overview["albums"][0]["year"] == "2013"
    assert overview["singles"] == []


def test_select_account_balances_ten_tasks_across_three_accounts(monkeypatch):
    accounts = ["a", "b", "c"]
    monkeypatch.setattr("tiddl.web.app.available_account_ids", lambda: accounts)
    loads = {account: 0 for account in accounts}

    for _ in range(10):
        selected = select_account(loads)
        loads[selected] += 1

    assert loads == {"a": 4, "b": 3, "c": 3}


def test_unhealthy_accounts_are_excluded_from_scheduling(monkeypatch):
    monkeypatch.setattr("tiddl.web.app.account_ids", lambda: ["healthy", "bad"])
    monkeypatch.setattr(
        "tiddl.web.app.load_account_settings", lambda: {"healthy": True, "bad": True}
    )
    account_health.clear()
    account_health["healthy"] = AccountHealth(status="healthy")
    account_health["bad"] = AccountHealth(status="unhealthy")

    assert available_account_ids() == ["healthy"]


def test_health_check_isolates_after_three_failures_and_recovers(monkeypatch):
    account_id = "a" * 10
    class Api:
        def __init__(self):
            self.error = RuntimeError("temporary network error")

        def get_session(self):
            if self.error:
                raise self.error

    api = Api()
    monkeypatch.setattr(
        "tiddl.web.app.account_context", lambda account_id: SimpleNamespace(api=api)
    )
    monkeypatch.setattr(
        "tiddl.web.app.load_auth_data",
        lambda path: SimpleNamespace(username="tester", refresh_token="token"),
    )
    account_health.clear()

    asyncio.run(check_account_health(account_id))
    assert account_health[account_id].status == "degraded"
    asyncio.run(check_account_health(account_id))
    asyncio.run(check_account_health(account_id))
    assert account_health[account_id].status == "unhealthy"

    api.error = None
    asyncio.run(check_account_health(account_id))
    assert account_health[account_id].status == "healthy"
    assert account_health[account_id].failures == 0


def test_each_download_command_contains_one_resource():
    request = DownloadRequest(
        urls=["album/1", "track/2"],
        track_quality="max",
        threads=2,
    )

    first = download_command(request, request.urls[0])
    second = download_command(request, request.urls[1])

    assert first[-2:] == ["url", "album/1"]
    assert second[-2:] == ["url", "track/2"]
    assert "track/2" not in first
    assert "album/1" not in second


def test_download_command_sets_singles_filter_for_artists():
    request = DownloadRequest(urls=["artist/1"])

    albums = download_command(request, "artist/1", singles=False)
    singles = download_command(request, "artist/1", singles=True)
    track = download_command(DownloadRequest(urls=["track/2"]), "track/2", singles=True)

    assert albums[albums.index("--singles") + 1] == "none"
    assert singles[singles.index("--singles") + 1] == "only"
    assert "--singles" not in track


def test_build_preview_artist_splits_albums_and_singles(monkeypatch):
    from tiddl.web.app import build_preview

    album = SimpleNamespace(id=1, title="Album", artists=[SimpleNamespace(name="Artist")], cover="c", duration=100, explicit=False)
    single = SimpleNamespace(id=2, title="Single", artists=[SimpleNamespace(name="Artist")], cover="c", duration=90, explicit=False)

    class Api:
        def get_artist(self, artist_id):
            return SimpleNamespace(name="Artist", picture="p")

        def get_artist_albums(self, artist_id, limit=100, filter="ALBUMS"):
            items = [album] if filter == "ALBUMS" else [single]
            return SimpleNamespace(items=items, totalNumberOfItems=len(items))

    monkeypatch.setattr("tiddl.web.app.account_context", lambda account_id=None: SimpleNamespace(api=Api()))

    cards = build_preview(["artist/1"])

    assert [card["subtitle"] for card in cards] == ["Artist releases", "Singles & EPs"]
    assert [card["singles"] for card in cards] == [False, True]
    assert [card["items"][0]["title"] for card in cards] == ["Album", "Single"]
    assert all(card["input_index"] == 0 for card in cards)


def test_detected_resource_options_override_global_defaults():
    request = DownloadRequest(urls=["video/1"])
    options = ResourceDownloadOptions(
        track_quality="max",
        video_quality="fhd",
        videos="only",
        atmos="allow",
    )

    command = download_command(request, request.urls[0], options)

    assert command[command.index("--track-quality") + 1] == "max"
    assert command[command.index("--videos") + 1] == "only"
    assert command[command.index("--dolby-atmos") + 1] == "allow"


def test_detect_download_options_exposes_supported_choices():
    track = SimpleNamespace(
        mediaMetadata=SimpleNamespace(tags=["HIRES_LOSSLESS", "DOLBY_ATMOS"]),
        audioModes=["STEREO", "DOLBY_ATMOS"],
    )
    entry = SimpleNamespace(item=track, type="track")

    options, specs = detect_download_options(
        [{"type": "track"}, {"type": "video"}], [entry]
    )

    assert options == {
        "track_quality": "max",
        "video_quality": "fhd",
        "videos": "allow",
        "atmos": "allow",
    }
    assert specs[0]["choices"] == ["low", "normal", "high", "max"]
    assert specs[2]["choices"] == ["none", "allow", "only"]
    assert specs[3]["choices"] == ["none", "allow", "only"]
