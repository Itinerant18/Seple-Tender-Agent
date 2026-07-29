/**
 * Current dashboard role, read from the server.
 *
 * The role comes from GET /api/auth/me — it is minted into the signed
 * session at login and cannot be edited client-side. What this hook drives
 * (hiding nav entries, redirecting away from admin routes) is presentation
 * only: the same rule is enforced in the gated auth middleware, so a user
 * who bypasses the UI gets a 403 from the API rather than data.
 *
 * Loopback / --insecure binds have no gate, so /api/auth/me 401s. That is
 * the "no roles in play" case and resolves to "admin" — the historical
 * unrestricted behaviour.
 */
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { UserRole } from "@/lib/api";

// Module-level cache: /api/auth/me is stable for the life of the page, and
// several components ask for the role. One request, not one per mount.
let cached: UserRole | null = null;
let inflight: Promise<UserRole> | null = null;

function fetchRole(): Promise<UserRole> {
  if (cached) return Promise.resolve(cached);
  if (!inflight) {
    inflight = api
      .getAuthMe()
      .then((me) => me.role ?? "admin")
      .catch(() => "admin" as UserRole) // ungated bind, or older backend
      .then((role) => {
        cached = role;
        inflight = null;
        return role;
      });
  }
  return inflight;
}

export function useRole(): { role: UserRole; loading: boolean } {
  const [role, setRole] = useState<UserRole | null>(cached);

  useEffect(() => {
    if (cached) return;
    let alive = true;
    void fetchRole().then((r) => {
      if (alive) setRole(r);
    });
    return () => {
      alive = false;
    };
  }, []);

  // Default to the restricted role while loading so an admin-only page
  // never flashes its contents before the role resolves.
  return { role: role ?? "tender_user", loading: role === null };
}

/** Routes a tender_user may open. Everything else redirects. */
export const TENDER_USER_ROUTES = ["/tenders", "/chat"] as const;

export function roleCanOpen(role: UserRole, path: string): boolean {
  if (role === "admin") return true;
  return TENDER_USER_ROUTES.some(
    (allowed) => path === allowed || path.startsWith(`${allowed}/`),
  );
}
