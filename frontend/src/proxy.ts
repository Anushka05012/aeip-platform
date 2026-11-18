import { NextResponse, type NextRequest } from "next/server";
import { authEnabled, decodeSession, SESSION_COOKIE } from "@/lib/auth/session";

/** Every page requires a signed-in user when login is configured (SEC-01). API routes check for themselves. */
export function proxy(request: NextRequest) {
    if (!authEnabled()) return NextResponse.next();
    const user = decodeSession(request.cookies.get(SESSION_COOKIE)?.value, process.env.AUTH_SECRET);
    if (user) return NextResponse.next();
    const login = new URL("/login", request.url);
    login.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
    return NextResponse.redirect(login);
}

export const config = {
    matcher: ["/((?!api/|login|_next/static|_next/image|favicon.ico|.*\.(?:png|svg|ico|jpg|webp)$).*)"],
};
