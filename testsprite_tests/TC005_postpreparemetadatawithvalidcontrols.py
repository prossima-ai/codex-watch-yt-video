import requests

BASE_URL = "http://localhost:5173"
TIMEOUT = 30
FIXTURE_PATH = "/tmp/testsprite-watch-fixture.mp4"
HEADERS = {"Content-Type": "application/json"}

def test_postpreparemetadatawithvalidcontrols():
    url = f"{BASE_URL}/prepare-metadata"
    payload = {
        "sources": [FIXTURE_PATH],
        "detail": "balanced",
        "focus": ["00:00:00.100", "00:00:00.900"],
        "cues": ["00:00:00.250", "00:00:00.750"],
        "max_frames": 100,
        "keep_duplicates": True
    }

    try:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        assert False, f"Request failed: {e}"

    assert response.status_code == 200, f"Expected HTTP 200 but got {response.status_code}"

    try:
        data = response.json()
    except ValueError:
        assert False, "Response is not valid JSON"

    assert data["state"] == "partial"
    assert data["failure"] is None

    assert data["controls"] == {
        "detail": "balanced",
        "focus_start_seconds": 0.1,
        "focus_end_seconds": 0.9,
        "cues_seconds": [0.25, 0.75],
        "max_frames": 100,
        "keep_duplicates": True,
        "output_dir": None,
    }

    evidence = data["evidence"]
    assert isinstance(evidence, dict)
    assert isinstance(evidence["metadata"], dict)
    assert evidence["transcript"] is None
    assert evidence["visual"] is None

test_postpreparemetadatawithvalidcontrols()
