def test_health_ok_with_token(client, auth):
    r = client.get("/v1/health", headers=auth)
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_health_missing_token(client):
    r = client.get("/v1/health")
    assert r.status_code == 401


def test_health_wrong_token(client):
    r = client.get("/v1/health", headers={"X-Auth-Token": "nope"})
    assert r.status_code == 401
