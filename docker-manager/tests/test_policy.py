import pytest
from src import policy
from werkzeug.exceptions import BadRequest


def test_validate_name_accepts_simple():
    assert policy.validate_name("myproject") == "myproject"


@pytest.mark.parametrize("bad", ["BadCaps", "1numeric", "", "x" * 99, "with space"])
def test_validate_name_rejects(bad):
    with pytest.raises(BadRequest):
        policy.validate_name(bad)


def test_validate_image_allows_frappe_registry():
    policy.validate_image("ghcr.io/frappe/bench-base:python3.11-node20")
    policy.validate_image("barista/bench-myproject:abc1234")


@pytest.mark.parametrize("bad", [
    "evil.io/coinminer:latest",
    "ghcr.io/notfrappe/x",
    "",
    None,
])
def test_validate_image_rejects(bad):
    with pytest.raises(BadRequest):
        policy.validate_image(bad)


def test_reject_dangerous_privileged():
    with pytest.raises(BadRequest):
        policy.reject_dangerous({"privileged": True})


def test_reject_dangerous_host_network():
    with pytest.raises(BadRequest):
        policy.reject_dangerous({"network_mode": "host"})


def test_validate_caps_only_allowed():
    policy.validate_caps(["CHOWN", "SETUID"])
    with pytest.raises(BadRequest):
        policy.validate_caps(["SYS_ADMIN"])
