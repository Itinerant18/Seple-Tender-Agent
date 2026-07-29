"""Role-based access control for the basic dashboard auth provider.

Covers the two things that would silently break RBAC: the credential →
role mapping in the provider, and the path/method rule the gated auth
middleware enforces.
"""

import importlib
import time

import pytest

from hermes_cli.dashboard_auth.roles import (
    ROLE_ADMIN,
    ROLE_TENDER_USER,
    normalize_role,
    role_allows,
)

basic = importlib.import_module("plugins.dashboard_auth.basic")

ADMIN_PW = "admin-password"
TENDER_PW = "tender-password"
SECRET = b"0123456789abcdef0123456789abcdef"


@pytest.fixture
def provider():
    return basic.BasicAuthProvider(
        username="seple",
        password_hash=basic.hash_password(ADMIN_PW),
        secret=SECRET,
        extra_accounts=(
            ("Tender", basic.hash_password(TENDER_PW), ROLE_TENDER_USER),
        ),
    )


class TestCredentialToRole:
    def test_admin_login_gets_admin_role(self, provider):
        s = provider.complete_password_login(username="seple", password=ADMIN_PW)
        assert s.user_id == "seple"
        assert s.role == ROLE_ADMIN

    def test_tender_login_gets_tender_role(self, provider):
        s = provider.complete_password_login(username="Tender", password=TENDER_PW)
        assert s.user_id == "Tender"
        assert s.role == ROLE_TENDER_USER

    @pytest.mark.parametrize(
        "username,password",
        [
            ("seple", TENDER_PW),  # admin user, other account's password
            ("Tender", ADMIN_PW),  # scoped user, admin's password
            ("Tender", "wrong"),
            ("nobody", ADMIN_PW),  # unknown user
        ],
    )
    def test_bad_credentials_rejected(self, provider, username, password):
        with pytest.raises(basic.InvalidCredentialsError):
            provider.complete_password_login(username=username, password=password)

    def test_duplicate_usernames_rejected(self):
        with pytest.raises(ValueError, match="duplicate"):
            basic.BasicAuthProvider(
                username="seple",
                password_hash=basic.hash_password(ADMIN_PW),
                secret=SECRET,
                extra_accounts=(
                    ("seple", basic.hash_password(TENDER_PW), ROLE_TENDER_USER),
                ),
            )

    def test_single_account_still_works(self):
        """No extra_accounts → unchanged single-admin behaviour."""
        p = basic.BasicAuthProvider(
            username="solo",
            password_hash=basic.hash_password(ADMIN_PW),
            secret=SECRET,
        )
        assert p.complete_password_login(
            username="solo", password=ADMIN_PW
        ).role == ROLE_ADMIN


class TestRoleSurvivesSessionLifecycle:
    def test_verify_preserves_role(self, provider):
        t = provider.complete_password_login(username="Tender", password=TENDER_PW)
        assert provider.verify_session(access_token=t.access_token).role == (
            ROLE_TENDER_USER
        )

    def test_refresh_preserves_role(self, provider):
        t = provider.complete_password_login(username="Tender", password=TENDER_PW)
        assert provider.refresh_session(refresh_token=t.refresh_token).role == (
            ROLE_TENDER_USER
        )

    def test_refresh_does_not_promote_admin(self, provider):
        a = provider.complete_password_login(username="seple", password=ADMIN_PW)
        assert provider.refresh_session(refresh_token=a.refresh_token).role == (
            ROLE_ADMIN
        )

    def test_forged_role_claim_fails_signature(self, provider):
        """A tampered role must invalidate the token, not grant admin."""
        t = provider.complete_password_login(username="Tender", password=TENDER_PW)
        forged = basic._sign(
            {
                "sub": "Tender",
                "role": ROLE_ADMIN,
                "kind": "access",
                "exp": int(time.time()) + 999,
            },
            b"a-different-secret-that-is-long-enough",
        )
        assert provider.verify_session(access_token=forged) is None
        # the genuine token still verifies as the scoped role
        assert provider.verify_session(access_token=t.access_token).role == (
            ROLE_TENDER_USER
        )

    def test_legacy_token_without_role_resolves_by_account(self, provider):
        """Sessions minted before roles existed must not lock the admin out."""
        legacy = basic._sign(
            {"sub": "seple", "kind": "access", "exp": int(time.time()) + 999},
            SECRET,
        )
        assert provider.verify_session(access_token=legacy).role == ROLE_ADMIN


class TestRegisterWiring:
    def test_env_configures_tender_account(self, monkeypatch):
        monkeypatch.setenv("HERMES_DASHBOARD_BASIC_AUTH_USERNAME", "seple")
        monkeypatch.setenv("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", ADMIN_PW)
        monkeypatch.setenv("HERMES_DASHBOARD_TENDER_USERNAME", "Tender")
        monkeypatch.setenv("HERMES_DASHBOARD_TENDER_PASSWORD", TENDER_PW)
        monkeypatch.setattr(basic, "_load_config_basic_auth_section", dict)

        registered = []

        class Ctx:
            def register_dashboard_auth_provider(self, p):
                registered.append(p)

        basic.register(Ctx())
        assert len(registered) == 1
        p = registered[0]
        assert p.complete_password_login(
            username="Tender", password=TENDER_PW
        ).role == ROLE_TENDER_USER
        assert p.complete_password_login(
            username="seple", password=ADMIN_PW
        ).role == ROLE_ADMIN

    def test_tender_username_without_password_is_skipped(self, monkeypatch):
        monkeypatch.setenv("HERMES_DASHBOARD_BASIC_AUTH_USERNAME", "seple")
        monkeypatch.setenv("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", ADMIN_PW)
        monkeypatch.setenv("HERMES_DASHBOARD_TENDER_USERNAME", "Tender")
        monkeypatch.delenv("HERMES_DASHBOARD_TENDER_PASSWORD", raising=False)
        monkeypatch.setattr(basic, "_load_config_basic_auth_section", dict)

        registered = []

        class Ctx:
            def register_dashboard_auth_provider(self, p):
                registered.append(p)

        basic.register(Ctx())
        # admin still registers; the half-configured scoped account does not
        assert len(registered) == 1
        with pytest.raises(basic.InvalidCredentialsError):
            registered[0].complete_password_login(
                username="Tender", password=TENDER_PW
            )


class TestApiAuthorizationRule:
    @pytest.mark.parametrize(
        "path,method",
        [
            ("/api/env", "GET"),
            ("/api/config", "POST"),
            ("/api/skills", "GET"),
            ("/api/anything-new", "GET"),
        ],
    )
    def test_admin_unrestricted(self, path, method):
        assert role_allows(ROLE_ADMIN, path, method)

    @pytest.mark.parametrize(
        "path,method",
        [
            ("/api/auth/me", "GET"),
            ("/api/auth/ws-ticket", "POST"),
            ("/api/pty", "POST"),
            ("/api/status", "GET"),
            ("/api/profiles", "GET"),
        ],
    )
    def test_tender_allowed_surface(self, path, method):
        assert role_allows(ROLE_TENDER_USER, path, method)

    @pytest.mark.parametrize(
        "path,method",
        [
            ("/api/env", "GET"),  # key material
            ("/api/config", "GET"),
            ("/api/skills", "GET"),
            ("/api/files/download", "GET"),
            ("/api/profiles", "POST"),  # read-only inside allowed surface
            ("/api/added-next-year", "GET"),  # deny by default
        ],
    )
    def test_tender_denied_surface(self, path, method):
        assert not role_allows(ROLE_TENDER_USER, path, method)

    def test_non_api_paths_never_gated_here(self):
        assert role_allows(ROLE_TENDER_USER, "/login", "GET")
        assert role_allows(ROLE_TENDER_USER, "/assets/index.js", "GET")

    @pytest.mark.parametrize(
        "path,method",
        [
            # traversal out of an allowed prefix into a denied one
            ("/api/status/../env", "GET"),
            ("/api/status/../../api/config", "GET"),
            ("/api/pty/../../api/config", "POST"),
            ("/api/auth/../env", "GET"),
            # segment-boundary spoofing
            ("/api/statusleak", "GET"),
            ("/api/profilesX", "GET"),
        ],
    )
    def test_prefix_match_cannot_be_spoofed(self, path, method):
        assert not role_allows(ROLE_TENDER_USER, path, method)

    def test_legitimate_subpaths_still_allowed(self):
        assert role_allows(ROLE_TENDER_USER, "/api/status/detail", "GET")
        assert role_allows(ROLE_TENDER_USER, "/api/profiles/active", "GET")


class TestNormalizeRole:
    def test_missing_role_is_admin(self):
        """Pre-roles sessions belonged to the only account: the admin."""
        assert normalize_role(None) == ROLE_ADMIN
        assert normalize_role("") == ROLE_ADMIN

    def test_unknown_role_never_escalates(self):
        assert normalize_role("root") == ROLE_TENDER_USER
        assert normalize_role("superuser") == ROLE_TENDER_USER
