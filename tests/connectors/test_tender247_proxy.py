import pytest

pytest.importorskip("playwright")

from connectors.tender247 import Tender247Connector

_proxy_server = Tender247Connector._proxy_server
_proxy_launch_args = Tender247Connector._proxy_launch_args


def test_direct_by_default(monkeypatch):
    monkeypatch.delenv("SCRAPER_PROXY", raising=False)
    monkeypatch.setenv("ZYTE_API", "key123")
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")

    # Deliberately off on AWS too: Zyte's rotating exit IP breaks the SPA
    # login, so auto-enabling it would burn credits and still fail.
    assert _proxy_server() is None
    assert _proxy_launch_args() is None


def test_explicit_proxy_is_used(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY", "http://user:pw@proxy.example:8011")

    assert _proxy_launch_args() == {
        "server": "http://proxy.example:8011",
        "username": "user",
        "password": "pw",
    }


def test_credentials_are_split_out_of_the_url(monkeypatch):
    # Chromium ignores user:pass embedded in the proxy URL and the proxy then
    # answers 407, so every navigation hangs until it times out.
    monkeypatch.setenv("SCRAPER_PROXY", "http://key123:@proxy.example:8011")
    config = _proxy_launch_args()

    assert "key123" not in config["server"]
    assert config["username"] == "key123"


def test_proxy_without_credentials(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY", "http://proxy.example:3128")

    assert _proxy_launch_args() == {"server": "http://proxy.example:3128"}
