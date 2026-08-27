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

    player_html = page_response("player.html").body.decode()
    index_html = page_response("index.html").body.decode()

    assert "/static/player.js?v=" in player_html
    assert "/static/app.js?v=" in index_html
    assert '"/static/player.js"' not in player_html
    assert '"/static/styles.css"' not in index_html


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
