import { type NextRequest } from "next/server";
import { currentUser, hasRole, type Role, SESSION_COOKIE } from "@/lib/auth/session";

/**
 * Backend-for-frontend: the browser never talks to the intelligence service directly.
 * This handler checks the session and role, then forwards the call with a shared service
 * token (AEIP_SERVICE_TOKEN) and the caller's identity, which the Python API verifies again.
 */
const API = process.env.INTELLIGENCE_API_URL ?? "http://localhost:8001";

function requiredRole(method: string, path: string, search: URLSearchParams): Role {
    if (method === "POST" && path.startsWith("/api/events")) return "admin";
    if (method === "POST") return "member"; // analyse, explain, ask: they spend GitHub and LLM quota
    if (path === "/api/incidents" && search.get("ai") === "1") return "member";
    return "viewer";
}

async function forward(request: NextRequest, params: Promise<{ path: string[] }>) {
    const user = currentUser(request.cookies.get(SESSION_COOKIE)?.value);
    if (!user) return Response.json({ error: "Sign in to use AEIP." }, { status: 401 });
    const path = "/" + (await params).path.map(encodeURIComponent).join("/");
    if (!/^\/(health|api\/[a-z/-]+)$/.test(path)) return Response.json({ error: "Route not found" }, { status: 404 });
    const needed = requiredRole(request.method, path, request.nextUrl.searchParams);
    if (!hasRole(user, needed)) {
        return Response.json({ error: `Your role (${user.role}) cannot do this; it needs ${needed}.` }, { status: 403 });
    }
    const headers: Record<string, string> = {
        "Content-Type": request.headers.get("Content-Type") ?? "application/json",
        "X-AEIP-User": user.login,
        "X-AEIP-Role": user.role,
    };
    if (process.env.AEIP_SERVICE_TOKEN) headers["X-AEIP-Service-Token"] = process.env.AEIP_SERVICE_TOKEN;
    try {
        const upstream = await fetch(`${API}${path}${request.nextUrl.search}`, {
            method: request.method, headers, cache: "no-store",
            body: request.method === "POST" ? await request.text() : undefined,
        });
        return new Response(await upstream.text(), {
            status: upstream.status,
            headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json", "Cache-Control": "no-store" },
        });
    } catch {
        return Response.json({ error: "The intelligence service is not running. Start it with: python scripts/serve.py" }, { status: 502 });
    }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
    return forward(request, context.params);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
    return forward(request, context.params);
}
