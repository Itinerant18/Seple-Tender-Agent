import pytest

pytest.importorskip("playwright")

# tender_tiger uses relative imports, so load it as a package member rather
# than by file path the way the gem_direct tests do.
from connectors.tender_tiger import TenderTigerConnector

_is_logged_in_url = TenderTigerConnector._is_logged_in_url


def test_dashboard_url_counts_as_logged_in():
    assert _is_logged_in_url("https://www.tendertiger.com/Dashboard/Dashboard") is True


def test_homepage_redirect_is_not_logged_in():
    # Observed on AWS 13-08-2026: an expired session redirects here, not to
    # /User/Account, so the old "not /User/Account" check reported success.
    assert _is_logged_in_url("https://www.tendertiger.com/") is False


def test_login_page_is_not_logged_in():
    assert _is_logged_in_url("https://www.tendertiger.com/User/Account?login") is False


def test_missing_url_does_not_raise():
    assert _is_logged_in_url(None) is False
