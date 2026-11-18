/**
 * Sessions and roles (SEC-01/02/03). Server-only: used by proxy.ts and the route handlers.
 *
 * Login is GitHub OAuth. The session is a small JSON payload signed with HMAC-SHA256
 * (AUTH_SECRET) in an httpOnly cookie, so it cannot be read by page scripts or forged.
 * Roles come from allowlists in env, so access is granted deliberately, never by default.
 *
 * With no OAuth app configured, AEIP runs in "open" mode for local development: everyone
 * acts as admin and the UI says so.
 */
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export type Role = "admin" | "member" | "viewer";
export type SessionUser = { login: string; name: string; avatar: string; role: Role; exp: number };

export const SESSION_COOKIE = "aeip_session";
export const STATE_COOKIE = "aeip_oauth_state";
export const SESSION_HOURS = 8;
const ROLE_RANK: Record<Role, number> = { viewer: 0, member: 1, admin: 2 };

export function authEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
    return Boolean(env.AUTH_SECRET && env.GITHUB_CLIENT_ID && env.GITHUB_CLIENT_SECRET);
}

export const OPEN_MODE_USER: SessionUser = { login: "local", name: "Local developer", avatar: "", role: "admin", exp: 0 };

function list(value: string | undefined): Set<string> {
    return new Set((value ?? "").split(",").map((item) => item.trim().toLowerCase()).filter(Boolean));
}

/** AEIP_ADMINS / AEIP_MEMBERS / AEIP_VIEWERS are comma-separated GitHub logins. AEIP_DEFAULT_ROLE
 * (viewer|member) lets any other GitHub user in; leave it unset to deny everyone not listed. */
export function roleFor(login: string, env: NodeJS.ProcessEnv = process.env): Role | null {
    const name = login.toLowerCase();
    if (list(env.AEIP_ADMINS).has(name)) return "admin";
    if (list(env.AEIP_MEMBERS).has(name)) return "member";
    if (list(env.AEIP_VIEWERS).has(name)) return "viewer";
    const fallback = (env.AEIP_DEFAULT_ROLE ?? "").toLowerCase();
    return fallback === "viewer" || fallback === "member" ? fallback : null;
}

export function hasRole(user: Pick<SessionUser, "role"> | null, needed: Role): boolean {
    return !!user && ROLE_RANK[user.role] >= ROLE_RANK[needed];
}

function sign(data: string, secret: string): string {
    return createHmac("sha256", secret).update(data).digest("base64url");
}

export function encodeSession(user: Omit<SessionUser, "exp">, secret: string, now = Date.now()): string {
    const payload: SessionUser = { ...user, exp: now + SESSION_HOURS * 3600_000 };
    const data = Buffer.from(JSON.stringify(payload)).toString("base64url");
    return `${data}.${sign(data, secret)}`;
}

export function decodeSession(token: string | undefined, secret: string | undefined, now = Date.now()): SessionUser | null {
    if (!token || !secret) return null;
    const [data, signature] = token.split(".");
    if (!data || !signature) return null;
    const expected = Buffer.from(sign(data, secret));
    const given = Buffer.from(signature);
    if (expected.length !== given.length || !timingSafeEqual(expected, given)) return null;
    try {
        const user = JSON.parse(Buffer.from(data, "base64url").toString()) as SessionUser;
        if (typeof user.exp !== "number" || user.exp < now || !(user.role in ROLE_RANK)) return null;
        return user;
    } catch {
        return null;
    }
}

export function newState(): string {
    return randomBytes(24).toString("base64url");
}

export function cookieOptions(maxAgeSeconds: number) {
    return {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax" as const,
        path: "/",
        maxAge: maxAgeSeconds,
    };
}

/** Only same-site relative paths are allowed after login (no open redirects). */
export function safeNext(value: string | null | undefined): string {
    return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/api/") ? value : "/";
}

/** Who is calling: the signed session, or the open-mode developer when auth is not configured. */
export function currentUser(cookieValue: string | undefined, env: NodeJS.ProcessEnv = process.env): SessionUser | null {
    if (!authEnabled(env)) return OPEN_MODE_USER;
    return decodeSession(cookieValue, env.AUTH_SECRET);
}
