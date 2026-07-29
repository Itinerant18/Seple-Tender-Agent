"""End-to-end RBAC through the real gated auth middleware.

The rule itself is unit-tested in
``tests/plugins/dashboard_auth/test_basic_roles.py``. This module proves
the *wiring*: that a real login over HTTP mints a role-carrying session,
that ``/api/auth/me`` reports it, and that the middleware actually returns
403 for a scoped user hitting an admin endpoint.

That last point is the whole feature. Hiding nav items in the SPA is
cosmetic — if this file passes, a tender_user with devtools open still
cannot read ``/api/env``.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hermes_cli import web_server
from hermes_cli.dashboard_auth import clear_providers, register_provider
from hermes_cli.dashboard_auth.roles import ROLE_ADMIN, ROLE_TENDER_USER
from hermes_cli.dashboard_auth.routes import _reset_password_rate_limit

import importlib

basic = importlib.import_module("plugins.dashboard_auth.basic")

ADMIN_USER, ADMIN_PW = "seple", "admin-password"
TENDER_USER, TENDER_PW = "Tender", "tender-password"


@pytest.fixture
def gated_app():
    clear_providers()
    register_provider(
        basic.BasicAuthProvider(
            username=ADMIN_USER,
            password_hash=basic.hash_password(ADMIN_PW),
            secret=b"0123456789abcdef0123456789abcdef",
            extra_accounts=(
                (
                    TENDER_USER,
                    basic.hash_password(TENDER_PW),
                    ROLE_TENDER_USER,
                ),
            ),
        )
    )
    _reset_password_rate_limit()
    prev = (
        getattr(web_server.app.state, "bound_host", None),
        getattr(web_server.app.state, "bound_port", None),
        getattr(web_server.app.state, "auth_required", None),
    )
    web_server.app.state.bound_host = "fly-app.fly.dev"
    web_server.app.state.bound_port = 443
    web_server.app.state.auth_required = True
    yield TestClient(web_server.app, base_url="https://fly-app.fly.dev")
    clear_providers()
    _reset_password_rate_limit()
    (
        web_server.app.state.bound_host,
        web_server.app.state.bound_port,
        web_server.app.state.auth_required,
    ) = prev


def _login(client, username, password):
    r = client.post(
        "/auth/password-login",
        json={"provider": "basic", "username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    return r


class TestRoleReachesTheClient:
    def test_admin_login_reports_admin_role(self, gated_app):
        _login(gated_app, ADMIN_USER, ADMIN_PW)
        me = gated_app.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user_id"] == ADMIN_USER
        assert me.json()["role"] == ROLE_ADMIN

    def test_tender_login_reports_scoped_role(self, gated_app):
        _login(gated_app, TENDER_USER, TENDER_PW)
        me = gated_app.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user_id"] == TENDER_USER
        assert me.json()["role"] == ROLE_TENDER_USER


class TestMiddlewareEnforcesRole:
    """The security boundary: these must hold with no browser involved."""

    @pytest.mark.parametrize("path", ["/api/env", "/api/config", "/api/skills"])
    def test_tender_user_forbidden_on_admin_endpoints(self, gated_app, path):
        _login(gated_app, TENDER_USER, TENDER_PW)
        r = gated_app.get(path)
        assert r.status_code == 403, (
            f"{path} returned {r.status_code}; a scoped user must not reach it"
        )

    @pytest.mark.parametrize("path", ["/api/env", "/api/config"])
    def test_admin_not_forbidden_on_same_endpoints(self, gated_app, path):
        """Same routes, admin session — must NOT be the 403 path.

        Asserts only that RBAC didn't reject it; the handler's own status
        (200, 404, 500…) is not this test's business.
        """
        _login(gated_app, ADMIN_USER, ADMIN_PW)
        assert gated_app.get(path).status_code != 403

    def test_tender_user_keeps_its_own_surface(self, gated_app):
        _login(gated_app, TENDER_USER, TENDER_PW)
        assert gated_app.get("/api/auth/me").status_code == 200
        # shell endpoints the SPA needs on every page, including Tenders
        assert gated_app.get("/api/status").status_code != 403
        assert gated_app.post("/api/auth/ws-ticket").status_code != 403

    def test_tender_user_is_read_only_outside_auth_and_pty(self, gated_app):
        _login(gated_app, TENDER_USER, TENDER_PW)
        # GET is fine (the shell reads it); POST would switch profiles
        assert gated_app.get("/api/profiles").status_code != 403
        assert gated_app.post("/api/profiles", json={}).status_code == 403

    def test_traversal_cannot_escape_the_allowed_surface(self, gated_app):
        """A raw ``..`` path must not ride an allowed prefix into /api/env."""
        _login(gated_app, TENDER_USER, TENDER_PW)
        r = gated_app.get("/api/status/../env")
        # Either the gate 403s it or the router never matches it — what must
        # NOT happen is a 200 carrying env contents.
        assert r.status_code != 200, r.text
