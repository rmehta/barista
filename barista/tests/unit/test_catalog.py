"""Pure-Python tests for the catalog module — URL validation and
app-name derivation. No Frappe site needed."""

import pytest

from barista.catalog import FIRST_PARTY, derive_app_name, is_valid_git_url


@pytest.mark.parametrize("url", [
    "https://github.com/frappe/erpnext",
    "https://github.com/frappe/erpnext.git",
    "https://gitlab.com/owner/repo",
    "https://git.example.com:8443/owner/repo.git",
    "git@github.com:frappe/hrms.git",
    "git@github.com:frappe/hrms",
])
def test_valid_git_urls(url):
    assert is_valid_git_url(url)


@pytest.mark.parametrize("url", [
    "",
    "not-a-url",
    "ftp://example.com/repo",
    "https://github.com",                # missing path
    "https://github.com/",               # empty owner/repo
    "rm -rf /",
])
def test_invalid_git_urls(url):
    assert not is_valid_git_url(url)


@pytest.mark.parametrize("url, expected", [
    ("https://github.com/frappe/erpnext", "erpnext"),
    ("https://github.com/frappe/erpnext.git", "erpnext"),
    ("https://github.com/owner/my-cool-app", "my_cool_app"),
    ("https://github.com/owner/my-cool-app.git", "my_cool_app"),
    ("git@github.com:frappe/hrms.git", "hrms"),
])
def test_derive_app_name(url, expected):
    assert derive_app_name(url) == expected


@pytest.mark.parametrize("url", [
    "https://github.com/owner/1starts-with-digit",   # invalid Python identifier
    "https://github.com/owner/-bad",
])
def test_derive_app_name_rejects(url):
    with pytest.raises(ValueError):
        derive_app_name(url)


def test_first_party_catalog_invariants():
    """Every catalog entry must be valid: URL parseable, name matches
    derivation, branch non-empty."""
    seen_names = set()
    for app in FIRST_PARTY:
        assert is_valid_git_url(app.repository_url), app
        assert app.default_branch, app
        assert app.app_name not in seen_names, f"duplicate: {app.app_name}"
        seen_names.add(app.app_name)

    # critical apps must be present
    names = {a.app_name for a in FIRST_PARTY}
    for required in ("frappe", "erpnext", "hrms", "crm", "insights", "builder"):
        assert required in names, f"catalog missing {required}"


def test_frappe_is_first_in_catalog():
    """frappe must be the head of the list — every Bench Spec needs
    it installed first."""
    assert FIRST_PARTY[0].app_name == "frappe"
