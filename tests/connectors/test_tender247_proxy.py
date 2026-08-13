import pytest

pytest.importorskip("playwright")

from connectors.tender247 import Tender247Connector

_proxy_server = Tender247Connector._proxy_server


def test_no_proxy_locally(monkeypatch):
    # Dev machines reach tender247 directly — proxying them wastes credits.
    monkeypatch.delenv("SCRAPER_PROXY", raising=False)
    monkeypatch.delenv("AWS_EXECUTION_ENV", raising=False)
    monkeypatch.setenv("ZYTE_API", "key123")

    assert _proxy_server() is None


def test_zyte_proxy_on_fargate(monkeypatch):
    monkeypatch.delenv("SCRAPER_PROXY", raising=False)
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")
    monkeypatch.setenv("ZYTE_API", "key123")

    assert _proxy_server() == "http://key123:@api.zyte.com:8011"


def test_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY", "http://someone-else:9000")
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")
    monkeypatch.setenv("ZYTE_API", "key123")

    assert _proxy_server() == "http://someone-else:9000"


def test_no_proxy_on_fargate_without_a_key(monkeypatch):
    monkeypatch.delenv("SCRAPER_PROXY", raising=False)
    monkeypatch.delenv("ZYTE_API", raising=False)
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")

    assert _proxy_server() is None
