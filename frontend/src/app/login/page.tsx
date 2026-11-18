const errors: Record<string, string> = {
  denied: "Your GitHub account is not on this AEIP workspace's access list. Ask an admin to add you.",
  state: "The sign-in link expired or was tampered with. Please try again.",
  github: "GitHub sign-in failed. Please try again.",
};

export default async function LoginPage({ searchParams }: {
  searchParams: Promise<{ error?: string; next?: string; signedOut?: string }>;
}) {
  const params = await searchParams;
  const error = params.error;
  const next = params.next?.startsWith("/") && !params.next.startsWith("//") ? params.next : "/";

  return <div className="min-h-[70vh] flex items-center justify-center">
    <div className="w-full max-w-[380px] bg-panel border border-line rounded-md p-7">
      <div className="flex items-center gap-2.5">
        <svg width="20" height="20" viewBox="0 0 18 18" aria-hidden>
          <rect x="1" y="1" width="16" height="16" rx="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M5 12.5 8 5.5l3 7M6.2 10h3.6M12.5 5.5v7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <span className="text-[17px] font-semibold">AEIP</span>
      </div>
      <h1 className="mt-5 text-[20px] font-semibold tracking-[-0.01em]">Sign in</h1>
      <p className="mt-1 text-[13px] text-muted">Engineering intelligence for your team&apos;s repositories, CI and production.</p>
      {error && <p className="mt-4 rounded-[5px] border border-bad/25 bg-bad-soft text-bad px-3 py-2 text-[13px]">{errors[error] ?? errors.github}</p>}
      {params.signedOut && <p className="mt-4 text-[13px] text-ink-2">You have signed out.</p>}
      <a href={`/api/auth/login?next=${encodeURIComponent(next)}`}
        className="mt-6 flex items-center justify-center gap-2 h-10 rounded-[5px] bg-ink text-paper text-[14px] font-medium hover:opacity-85">
        <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden fill="currentColor">
          <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.22 1.87.87 2.33.66.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.6 7.6 0 0 1 8 3.87c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.66 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
        </svg>
        Continue with GitHub
      </a>
      <p className="mt-4 text-[11.5px] leading-5 text-muted">AEIP only reads your GitHub identity (read:user). Access and roles are set by your workspace admin.</p>
    </div>
  </div>;
}
