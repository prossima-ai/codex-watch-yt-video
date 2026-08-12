import requests

def test_postpreparemetadatawithvalidsinglesource():
    base_url = "http://localhost:5173"
    endpoint = "/prepare-metadata"
    url = base_url + endpoint
    payload = {
        "sources": ["/tmp/testsprite-watch-fixture.mp4"],
        "question": "Is this a valid single source test?"
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
        data = response.json()

        # EvidenceOutcome must have state and source established.
        # By design, 200 response returns typed EvidenceOutcome even on failure, so check state and failure keys.
        assert "state" in data, "Response JSON missing 'state' field"
        assert data["state"] in ("running", "complete", "failed", "stopped", "decision_required", "partial"), f"Unexpected state value: {data['state']}"
        assert "source" in data, "Response JSON missing 'source' field"
        # The source should match the single input source exactly
        assert isinstance(data["source"], dict) or isinstance(data["source"], list), "source field should be dict or list"
        # Confirm that current source is one and corresponds to the given source path or related info
        # Since schema may vary, just check that the input source path or something close is present somewhere
        source_strs = []
        def collect_strings(obj):
            if isinstance(obj, str):
                source_strs.append(obj)
            elif isinstance(obj, list):
                for i in obj:
                    collect_strings(i)
            elif isinstance(obj, dict):
                for v in obj.values():
                    collect_strings(v)
        collect_strings(data["source"])
        assert any("/tmp/testsprite-watch-fixture.mp4" in s for s in source_strs), "The current source is not established as the test fixture path"

        # Assert that no later stages like caption, visual, transcription, workspace, or cleanup are performed
        # According to instructions, do not test them, so no keys related to these stages should appear or not tested here.

    except requests.RequestException as e:
        assert False, f"Request failed: {e}"
    except ValueError:
        assert False, "Response is not valid JSON"

test_postpreparemetadatawithvalidsinglesource()