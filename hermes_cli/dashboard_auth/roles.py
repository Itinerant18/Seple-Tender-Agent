"""Dashboard roles and the per-role API authorization rule.

Two roles today:

* ``admin`` — the original single dashboard account. Unrestricted; every
  ``/api/`` route behaves exactly as it did before roles existed.
* ``tender_user`` — a scoped account for the SEPLE tender workflow. Sees
  the Tenders board and the Chat page and nothing else.

The rule here is the *authoritative* one: it runs in the gated auth
middleware, after the session cookie is verified, before the request
reaches a handler. Hiding nav items in the SPA is cosmetic — a browser
devtools console can call any endpoint it likes, so the server has to be
the thing that says no.

Deny-by-default for non-admins: an endpoint is reachable only if it is
listed below. A route added later is therefore admin-only until someone
deliberately opens it, which is the failure direction we want.

Note the Tenders board itself is NOT gated here — it reads the separate
tender-api service (compose: ``tender-api:8000``), which has its own
front door. This module governs the Hermes dashboard API only.
"""

from __future__ import annotations

import posixpath

ROLE_ADMIN = "admin"
ROLE_TENDER_USER = "tender_user"

#: Every role this build understands. Anything else is treated as
#: untrusted and gets the tender_user (least-privilege) rule.
KNOWN_ROLES = frozenset({ROLE_ADMIN, ROLE_TENDER_USER})

#: API prefixes a tender_user may reach at all.
#:   /api/auth/     — session identity, logout, websocket tickets
#:   /api/status    — the shell's liveness/status strip
#:   /api/profiles  — ProfileProvider mounts app-wide; a 403 here would
#:                    break the shell for every page, including Tenders.
#:                    Read-only, and the body is metadata only (name,
#:                    model/provider names, profile path, has_env as a
#:                    boolean) — no secret values.
#:   /api/update    — the shell's update banner
#:   /api/pty       — the Chat page's terminal transport
#:
#: SECURITY CAVEAT on /api/pty. It is not a chat-message endpoint: it
#: spawns ``hermes --tui``, the full agent, behind a pseudo-terminal. That
#: agent has filesystem and shell tools (see agent/tool_executor.py —
#: write_file, patch, …), so anyone who can open Chat can ask the agent to
#: read .env and thereby recover the very secrets the /api/env deny rule
#: above is protecting. In other words a tender_user is, in practice,
#: closer to admin than this list suggests.
#:
#: This is inherent to granting Chat at all, not a flaw in the rule — but
#: it is a deliberate, reviewable choice. To close it, drop "/api/pty"
#: from the tuple below (tender_user then loses the Chat page), or give
#: the PTY a tool-restricted agent profile for non-admin roles.
_TENDER_ALLOWED_PREFIXES: tuple[str, ...] = (
    "/api/auth/",
    "/api/status",
    "/api/profiles",
    "/api/update",
    "/api/pty",
)

#: Of those, the only prefixes where a tender_user may use a *writing*
#: method. Everywhere else they are read-only, so e.g. GET /api/profiles
#: (shell needs it) is fine but POST /api/profiles (switch profile) is not.
_TENDER_WRITABLE_PREFIXES: tuple[str, ...] = ("/api/auth/", "/api/pty")

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _normalize_path(path: str) -> str:
    """Collapse ``..``/``.``/duplicate slashes before any prefix matching.

    Without this, ``/api/status/../env`` passes a naive ``startswith``
    check against the allowed ``/api/status`` prefix and then reaches the
    env handler — the ASGI layer does not normalize the raw path for us.
    """
    collapsed = posixpath.normpath(path)
    # normpath strips a trailing slash and turns "" into "."; neither
    # matters for prefix matching, but a leading slash does.
    if not collapsed.startswith("/"):
        collapsed = "/" + collapsed.lstrip(".")
    return collapsed


def _matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    """Prefix match on path-segment boundaries.

    ``/api/status`` must match ``/api/status`` and ``/api/status/x`` but
    NOT ``/api/statusleak``. Prefixes that already end in ``/`` (e.g.
    ``/api/auth/``) are inherently boundary-safe.
    """
    for prefix in prefixes:
        if prefix.endswith("/"):
            if path.startswith(prefix):
                return True
        elif path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def role_allows(role: str, path: str, method: str) -> bool:
    """True if ``role`` may issue ``method`` against ``path``.

    Non-``/api/`` paths always pass: the dashboard is a single-page bundle
    whose routes are resolved client-side, so there is no per-page HTML to
    gate. Route visibility is enforced in the SPA; the data behind it is
    enforced here.
    """
    if role == ROLE_ADMIN:
        return True
    path = _normalize_path(path)
    if not path.startswith("/api/"):
        return True
    if not _matches_prefix(path, _TENDER_ALLOWED_PREFIXES):
        return False
    if method.upper() in _SAFE_METHODS:
        return True
    return _matches_prefix(path, _TENDER_WRITABLE_PREFIXES)


def normalize_role(role: str | None) -> str:
    """Map an absent/unknown role onto a known one.

    Unknown roles fall to ``tender_user`` rather than ``admin`` so a typo in
    config can never mint privilege. ``None``/empty means a session minted
    before roles existed, when the only account was the admin — those stay
    admin so an upgrade doesn't lock the operator out of their own dashboard.
    """
    if not role:
        return ROLE_ADMIN
    return role if role in KNOWN_ROLES else ROLE_TENDER_USER


def _self_check() -> None:
    """Smallest check that fails if the authorization rule regresses."""
    # admin is unrestricted
    assert role_allows(ROLE_ADMIN, "/api/env", "GET")
    assert role_allows(ROLE_ADMIN, "/api/config", "POST")

    # tender_user: allowed surface
    assert role_allows(ROLE_TENDER_USER, "/api/auth/me", "GET")
    assert role_allows(ROLE_TENDER_USER, "/api/auth/logout", "POST")
    assert role_allows(ROLE_TENDER_USER, "/api/pty", "POST")
    assert role_allows(ROLE_TENDER_USER, "/api/status", "GET")
    assert role_allows(ROLE_TENDER_USER, "/api/profiles", "GET")

    # tender_user: denied surface — key material, config, shell, skills
    assert not role_allows(ROLE_TENDER_USER, "/api/env", "GET")
    assert not role_allows(ROLE_TENDER_USER, "/api/config", "GET")
    assert not role_allows(ROLE_TENDER_USER, "/api/skills", "GET")
    assert not role_allows(ROLE_TENDER_USER, "/api/files/download", "GET")
    # read-only even inside the allowed surface
    assert not role_allows(ROLE_TENDER_USER, "/api/profiles", "POST")
    # unknown routes are denied, not allowed, by default
    assert not role_allows(ROLE_TENDER_USER, "/api/something-added-later", "GET")
    # traversal must not ride in on an allowed prefix
    assert not role_allows(ROLE_TENDER_USER, "/api/status/../env", "GET")
    assert not role_allows(ROLE_TENDER_USER, "/api/pty/../../api/config", "POST")
    # prefix match respects segment boundaries
    assert not role_allows(ROLE_TENDER_USER, "/api/statusleak", "GET")
    assert role_allows(ROLE_TENDER_USER, "/api/status/detail", "GET")
    # SPA shell + login page are never gated here
    assert role_allows(ROLE_TENDER_USER, "/login", "GET")
    assert role_allows(ROLE_TENDER_USER, "/assets/index.js", "GET")

    # normalize_role: unknown never escalates, legacy sessions stay admin
    assert normalize_role(None) == ROLE_ADMIN
    assert normalize_role("") == ROLE_ADMIN
    assert normalize_role("admin") == ROLE_ADMIN
    assert normalize_role("tender_user") == ROLE_TENDER_USER
    assert normalize_role("root") == ROLE_TENDER_USER
    print("roles: ok")


if __name__ == "__main__":
    _self_check()
