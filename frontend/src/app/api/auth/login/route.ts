import { NextResponse, type NextRequest } from "next/server";
import { authEnabled, cookieOptions, newState, safeNext, STATE_COOKIE } from "@/lib/auth/session";

/** Starts GitHub OAuth. `state` is random, stored in an httpOnly cookie and checked on return (CSRF). */
export async function GET(request: NextRequest) {
    if (!authEnabled()) return NextResponse.redirect(new URL("/", request.url));
    const state = newState();
    const next = safeNext(request.nextUrl.searchParams.get("next"));
    const origin = process.env.AEIP_PUBLIC_URL ?? request.nextUrl.origin;
    const authorize = new URL("https://github.com/login/oauth/authorize");
    authorize.searchParams.set("client_id", process.env.GITHUB_CLIENT_ID!);
    authorize.searchParams.set("redirect_uri", `${origin}/api/auth/callback`);
    authorize.searchParams.set("scope", "read:user"); // identity only: AEIP never acts on the user's repositories
    authorize.searchParams.set("state", state);
    authorize.searchParams.set("allow_signup", "false");
    const response = NextResponse.redirect(authorize);
    response.cookies.set(STATE_COOKIE, `${state}|${next}`, cookieOptions(600));
    return response;
}
