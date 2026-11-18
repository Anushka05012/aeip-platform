"use client";

import { useEffect, useState } from "react";

export type Role = "admin" | "member" | "viewer";
export type ClientSession = { enabled: boolean; user: { login: string; name: string; avatar: string; role: Role } | null };

const rank: Record<Role, number> = { viewer: 0, member: 1, admin: 2 };
let cached: Promise<ClientSession> | null = null;

function load(): Promise<ClientSession> {
    cached ??= fetch("/api/auth/me", { cache: "no-store" })
        .then((response) => response.json() as Promise<ClientSession>)
        .catch(() => ({ enabled: false, user: null }));
    return cached;
}

/** The signed-in user (or the open-mode developer). `can(role)` hides actions the user may not take;
 * the server enforces the same rule, this only keeps the UI honest. */
export function useSession() {
    const [session, setSession] = useState<ClientSession | null>(null);
    useEffect(() => { load().then(setSession); }, []);
    const can = (role: Role) => !!session?.user && rank[session.user.role] >= rank[role];
    return { session, can, loading: session === null };
}
