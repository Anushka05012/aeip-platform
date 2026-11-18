import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth/session";

export async function POST(request: NextRequest) {
    const response = NextResponse.redirect(new URL("/login?signedOut=1", request.url), 303);
    response.cookies.delete(SESSION_COOKIE);
    return response;
}
