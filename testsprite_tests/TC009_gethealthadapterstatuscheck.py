import requests

def test_gethealthadapterstatuscheck():
    url = "http://localhost:5173/health"
    headers = {
        "Accept": "application/json"
    }
    timeout = 30

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        assert False, f"Request to /health failed: {e}"

    try:
        adapter_status = response.json()
    except ValueError:
        assert False, "Response is not valid JSON"

    # Assert the response is HTTP 200
    assert response.status_code == 200, f"Expected status code 200 but got {response.status_code}"

    # The adapter status object is expected; check keys to confirm availability and readiness
    # Since the PRD does not specify exact keys, verify presence of typical keys for status confirmation
    # Here we expect at least one key that indicates adapter availability and readiness
    assert isinstance(adapter_status, dict), "Adapter status is not a JSON object"
    assert adapter_status, "Adapter status object is empty"

    # Typical keys might include 'available' or 'ready' or similar; assert presence of at least one such key
    availability_keys = {"available", "ready", "status"}
    found = any(key in adapter_status for key in availability_keys)
    assert found, f"Adapter status object missing expected keys ({availability_keys}): {adapter_status}"

test_gethealthadapterstatuscheck()