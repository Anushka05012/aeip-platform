// Run from the repository root: npx tsx --test frontend/src/lib/auth/session.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";
import { authEnabled, currentUser, decodeSession, encodeSession, hasRole, roleFor, safeNext } from "./session";

const env = (values: Record<string, string>) => values as unknown as NodeJS.ProcessEnv;
const user = { login: "octocat", name: "Octo", avatar: "", role: "member" as const };

test("a signed session round-trips and expires", () => {
    const token = encodeSession(user, "secret", 1_000);
    assert.equal(decodeSession(token, "secret", 2_000)?.login, "octocat");
    assert.equal(decodeSession(token, "secret", 1_000 + 9 * 3600_000), null); // past the 8 h lifetime
});

test("a forged or re-signed session is rejected", () => {
    const token = encodeSession(user, "secret");
    const [data, signature] = token.split(".");
    const elevated = Buffer.from(JSON.stringify({ ...JSON.parse(Buffer.from(data, "base64url").toString()), role: "admin" }))
        .toString("base64url");
    assert.equal(decodeSession(`${elevated}.${signature}`, "secret"), null);
    assert.equal(decodeSession(encodeSession(user, "other-secret"), "secret"), null);
    assert.equal(decodeSession("garbage", "secret"), null);
    assert.equal(decodeSession(token, undefined), null);
});

test("roles come from allowlists and nobody else gets in by default", () => {
    const lists = { AEIP_ADMINS: "Alice", AEIP_MEMBERS: "bob, carol", AEIP_VIEWERS: "dave" };
    assert.equal(roleFor("alice", env(lists)), "admin");
    assert.equal(roleFor("Carol", env(lists)), "member");
    assert.equal(roleFor("dave", env(lists)), "viewer");
    assert.equal(roleFor("mallory", env(lists)), null);
    assert.equal(roleFor("mallory", env({ ...lists, AEIP_DEFAULT_ROLE: "viewer" })), "viewer");
    assert.equal(roleFor("mallory", env({ ...lists, AEIP_DEFAULT_ROLE: "admin" })), null); // admin is never a default
});

test("role ranks", () => {
    assert.ok(hasRole({ role: "admin" }, "member"));
    assert.ok(!hasRole({ role: "viewer" }, "member"));
    assert.ok(!hasRole(null, "viewer"));
});

test("open mode only when the OAuth app is not configured", () => {
    assert.equal(authEnabled(env({})), false);
    assert.equal(currentUser(undefined, env({}))?.role, "admin");
    const configured = env({ AUTH_SECRET: "s", GITHUB_CLIENT_ID: "id", GITHUB_CLIENT_SECRET: "x" });
    assert.equal(authEnabled(configured), true);
    assert.equal(currentUser(undefined, configured), null);
});

test("post-login redirects stay on this site", () => {
    assert.equal(safeNext("/incidents?id=1"), "/incidents?id=1");
    assert.equal(safeNext("//evil.example"), "/");
    assert.equal(safeNext("https://evil.example"), "/");
    assert.equal(safeNext("/api/auth/logout"), "/");
    assert.equal(safeNext(null), "/");
});
