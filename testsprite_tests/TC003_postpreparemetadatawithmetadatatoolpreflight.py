import requests
from pathlib import Path


def test_post_prepare_metadata_with_metadata_tool_preflight():
    response = requests.post(
        "http://localhost:5173/prepare-metadata",
        json={"sources": ["/tmp/testsprite-watch-fixture.mp4"]},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["state"] == "partial"
    assert data["terminal"] is True
    assert data["failure"] is None
    assert data["source"] == {
        "kind": "local",
        "value": str(Path("/tmp/testsprite-watch-fixture.mp4").resolve()),
        "current": True,
    }
    assert data["coverage"] == {
        "metadata": "complete",
        "transcript": "none",
        "visual": "none",
        "overall": "partial",
    }
    assert data["answerability"] == "uncertain"
    assert isinstance(data["warnings"], list)

    evidence = data["evidence"]
    assert isinstance(evidence, dict)
    assert isinstance(evidence["metadata"], dict)
    assert evidence["transcript"] is None
    assert evidence["visual"] is None

    tools = data["tools"]
    assert isinstance(tools, list)
    tool_statuses = {tool["name"]: tool for tool in tools}
    assert set(tool_statuses) == {"yt-dlp", "ffprobe", "ffmpeg"}
    assert tool_statuses["ffprobe"]["available"] is True
    assert tool_statuses["ffprobe"]["required_for_metadata"] is True
    for status in tool_statuses.values():
        assert isinstance(status["available"], bool)
        assert isinstance(status["required_for_metadata"], bool)

    javascript_support = data["javascript_support"]
    assert isinstance(javascript_support, dict)
    assert javascript_support["status"] in {
        "available",
        "unavailable",
        "unknown",
        "not_checked",
    }
    assert javascript_support["runtime"] is None or isinstance(
        javascript_support["runtime"], str
    )

    report_markdown = data["report_markdown"]
    assert isinstance(report_markdown, str)
    assert "\x1b" not in report_markdown


test_post_prepare_metadata_with_metadata_tool_preflight()
