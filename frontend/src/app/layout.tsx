import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";
import { themeInitScript } from "@/lib/theme-script";

const plexSans = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-sans" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: "AEIP — Engineering Intelligence",
  description: "Software engineering analytics and CI/CD failure intelligence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="bg-paper text-ink text-[14px]">
        <div className="w-full min-h-screen flex">
          <Sidebar />
          <main className="flex-1 min-w-0 flex flex-col">
            <Topbar />
            <div className="flex-1 overflow-auto px-6 lg:px-10 py-8">
              <div className="max-w-[1180px] mx-auto">{children}</div>
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
