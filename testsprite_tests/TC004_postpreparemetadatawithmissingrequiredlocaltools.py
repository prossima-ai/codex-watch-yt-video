import requests


def test_postpreparemetadatawithmissingrequiredlocaltools():
    response = requests.post(
        "http://localhost:5173/prepare-metadata",
        json={"sources": ["/tmp/testsprite-watch-fixture.mp4"]},
        headers={
            "Content-Type": "application/json",
            "X-TestSprite-Simulate-Missing-Tool": "ffprobe",
        },
        timeout=30,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert data["state"] == "failed"
    assert data["terminal"] is True
    assert data["evidence"] is None
    assert data["coverage"] == {
        "metadata": "none",
        "transcript": "none",
        "visual": "none",
        "overall": "none",
    }

    failure = data["failure"]
    assert failure["stage"] == "preflight"
    assert failure["category"] == "missing_dependency"
    assert "ffprobe" in failure["message"]
    assert "Install it deliberately, then retry" in failure["message"]
    assert failure["attempts"] == 0
    assert failure["disposal_state"] == "not_created"
    assert failure["reuse_state"] == "current_source_only"

    tool_statuses = {tool["name"]: tool for tool in data["tools"]}
    assert tool_statuses["ffprobe"] == {
        "name": "ffprobe",
        "available": False,
        "required_for_metadata": True,
        "version": None,
    }


test_postpreparemetadatawithmissingrequiredlocaltools()
