
import yaml


def test_put_routes_writes_yaml(client, auth, app, tmp_path):
    out = tmp_path / "dynamic.yml"
    app.config["TRAEFIK_DYNAMIC"] = str(out)

    payload = {
        "routes": [
            {"host": "myshop.localhost", "service": "barista-bench-myproject",
             "port": 80, "tls": False},
            {"host": "dev.example.com", "service": "barista-bench-dev",
             "port": 80, "tls": True},
        ]
    }
    r = client.put("/v1/routes", json=payload, headers=auth)
    assert r.status_code == 200
    assert r.get_json()["applied"] == 2

    doc = yaml.safe_load(out.read_text())
    routers = doc["http"]["routers"]
    services = doc["http"]["services"]
    assert "barista-bench-myproject" in routers
    assert "barista-bench-dev" in services
    assert services["barista-bench-myproject"]["loadBalancer"]["servers"][0]["url"] \
        == "http://barista-bench-myproject:80"
    assert routers["barista-bench-dev"]["entryPoints"] == ["websecure"]
