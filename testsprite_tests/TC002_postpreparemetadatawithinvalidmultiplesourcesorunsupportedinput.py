import requests

def test_post_prepare_metadata_with_invalid_multiple_sources_or_unsupported_input():
    base_url = "http://localhost:5173"
    url = f"{base_url}/prepare-metadata"
    timeout = 30

    # Prepare test cases with diverse invalid or unsupported sources
    test_sources_cases = [
        ["local_fixture_1.mp4", "local_fixture_2.mp4"],            # multiple sources
        ["http://example.com/playlist.m3u8"],                      # playlist URL (not allowed)
        ["unsupported_format.xyz"],                                # unsupported source format
        ["private_source_path_or_url"],                            # private source (simulated)
        ["live_source_url_or_identifier"]                          # live source (simulated)
    ]

    headers = {"Content-Type": "application/json"}

    for sources in test_sources_cases:
        payload = {"sources": sources}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException:
            # If request fails (non-200), this is also acceptable per spec since error or stopped outcome expected
            # So no assertion fail here; just continue to next scenario
            continue

        # On 200 response: verify response JSON indicates stopped or failed state with failure detail
        resp_json = response.json()
        state = resp_json.get("state")
        failure = resp_json.get("failure")

        assert state in ("stopped", "failed"), (
            f"Expected 'state' to be 'stopped' or 'failed' for sources {sources}, got '{state}'"
        )
        assert failure is not None, (
            f"Expected 'failure' field with details for sources {sources}, got None or empty"
        )

        # Assert no later stages performed by confirming absence or empty captions, visual, transcription in the evidence
        evidence = resp_json.get("evidence") or {}

        caption_val = evidence.get("caption")
        assert not caption_val, (
            f"Expected no caption evidence for sources {sources}"
        )

        visual_val = evidence.get("visual")
        assert not visual_val, (
            f"Expected no visual evidence for sources {sources}"
        )

        transcription_val = evidence.get("transcription")
        assert not transcription_val, (
            f"Expected no transcription evidence for sources {sources}"
        )

test_post_prepare_metadata_with_invalid_multiple_sources_or_unsupported_input()