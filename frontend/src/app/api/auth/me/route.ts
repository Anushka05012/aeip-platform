import { type NextRequest } from "next/server";
import { authEnabled, currentUser, SESSION_COOKIE } from "@/lib/auth/session";

export async function GET(request: NextRequest) {
    const user = currentUser(request.cookies.get(SESSION_COOKIE)?.value);
    return Response.json({ enabled: authEnabled(), user: user && { login: user.login, name: user.name, avatar: user.avatar, role: user.role } },
        { status: user ? 200 : 401, headers: { "Cache-Control": "no-store" } });
}
