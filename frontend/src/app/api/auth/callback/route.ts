import { NextResponse, type NextRequest } from "next/server";
import { timingSafeEqual } from "node:crypto";
import { authEnabled, cookieOptions, encodeSession, roleFor, safeNext, SESSION_COOKIE, SESSION_HOURS, STATE_COOKIE } from "@/lib/auth/session";

function fail(request: NextRequest, reason: string) {
    const response = NextResponse.redirect(new URL(`/login?error=${reason}`, request.url));
    response.cookies.delete(STATE_COOKIE);
    return response;
}

function sameState(a: string, b: string) {
    const left = Buffer.from(a);
    const right = Buffer.from(b);
    return left.length === right.length && timingSafeEqual(left, right);
}

export async function GET(request: NextRequest) {
    if (!authEnabled()) return NextResponse.redirect(new URL("/", request.url));
    const code = request.nextUrl.searchParams.get("code");
    const state = request.nextUrl.searchParams.get("state") ?? "";
    const [expected = "", next = "/"] = (request.cookies.get(STATE_COOKIE)?.value ?? "").split("|");
    if (!code || !expected || !sameState(state, expected)) return fail(request, "state");

    const origin = process.env.AEIP_PUBLIC_URL ?? request.nextUrl.origin;
    try {
        const tokenResponse = await fetch("https://github.com/login/oauth/access_token", {
            method: "POST",
            headers: { Accept: "application/json", "Content-Type": "application/json" },
            body: JSON.stringify({
                client_id: process.env.GITHUB_CLIENT_ID, client_secret: process.env.GITHUB_CLIENT_SECRET,
                code, redirect_uri: `${origin}/api/auth/callback`,
            }),
        });
        const token = (await tokenResponse.json()) as { access_token?: string };
        if (!token.access_token) return fail(request, "github");
        const userResponse = await fetch("https://api.github.com/user", {
            headers: { Authorization: `Bearer ${token.access_token}`, Accept: "application/vnd.github+json", "User-Agent": "aeip" },
        });
        if (!userResponse.ok) return fail(request, "github");
        const profile = (await userResponse.json()) as { login: string; name?: string | null; avatar_url?: string };
        const role = roleFor(profile.login);
        if (!role) return fail(request, "denied");

        // The GitHub token is not stored: AEIP only needed it to learn who the user is.
        const session = encodeSession({ login: profile.login, name: profile.name ?? profile.login, avatar: profile.avatar_url ?? "", role },
            process.env.AUTH_SECRET!);
        const response = NextResponse.redirect(new URL(safeNext(next), request.url));
        response.cookies.set(SESSION_COOKIE, session, cookieOptions(SESSION_HOURS * 3600));
        response.cookies.delete(STATE_COOKIE);
        console.log(`[auth] login ${profile.login} as ${role}`);
        return response;
    } catch {
        return fail(request, "github");
    }
}
