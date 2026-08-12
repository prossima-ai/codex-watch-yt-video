import requests

BASE_URL = "http://localhost:5173"
TIMEOUT = 30
VALID_SOURCE = "/tmp/testsprite-watch-fixture.mp4"
HEADERS = {"Content-Type": "application/json"}

def test_postpreparemetadatawithinvalidcontrols():
    url = f"{BASE_URL}/prepare-metadata"
    invalid_cases = [
        # invalid detail value
        {"sources": [VALID_SOURCE], "detail": "invalid-detail"},
        # malformed timestamp in focus (end before start and string instead of timestamp)
        {"sources": [VALID_SOURCE], "focus": ["not-a-timestamp", "also-not"]},
        {"sources": [VALID_SOURCE], "focus": ["2023-01-01T00:10:00Z", "2023-01-01T00:05:00Z"]},
        # negative cue timestamp
        {"sources": [VALID_SOURCE], "cues": [-5]},
        # non-positive max_frames (zero and negative)
        {"sources": [VALID_SOURCE], "max_frames": 0},
        {"sources": [VALID_SOURCE], "max_frames": -10},
        # stale caption_track or audio_track IDs (using some likely invalid values)
        {"sources": [VALID_SOURCE], "caption_track": "stale-caption-id"},
        {"sources": [VALID_SOURCE], "audio_track": "stale-audio-id"},
    ]

    for payload in invalid_cases:
        response = requests.post(url, json=payload, headers=HEADERS, timeout=TIMEOUT)
        assert response.status_code == 200, f"Unexpected HTTP status code: {response.status_code}"
        data = response.json()
        state = data.get("state", "")
        failure = data.get("failure", None)

        # Outcome must indicate failure or decision_required because controls are invalid
        assert state in ("failed", "decision_required", "stopped", "blocked"), f"Unexpected state value: {state}"
        assert failure is not None, "Failure detail must be provided for invalid control test."

        # Extract failure message string for searching
        failure_str = ""
        if isinstance(failure, dict) and "message" in failure and isinstance(failure["message"], str):
            failure_str = failure["message"].lower()
        else:
            failure_str = str(failure).lower()

        invalid_control_found = False
        for key in ["detail", "focus", "cue", "max_frames", "caption_track", "audio_track"]:
            if key in failure_str or key.replace("_", " ") in failure_str:
                invalid_control_found = True
                break
        assert invalid_control_found, f"Failure message does not indicate invalid control: {failure}"

        # no selection guessed
        assert "selection" not in data, "Response should not contain a guessed selection."

        # no later acquisition begun: check no evidence or similar keys indicating progress
        # The evidence field might be empty or absent for failed cases
        evidence = data.get("evidence", None)
        assert not evidence or len(evidence) == 0 or evidence == {} , "No evidence should be produced for invalid controls"

test_postpreparemetadatawithinvalidcontrols()
