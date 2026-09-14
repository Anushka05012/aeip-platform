import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/layout/Sidebar";
import Topbar from "@/components/layout/Topbar";

export const metadata: Metadata = {
  title: "AEIP — AI Engineering Intelligence Platform",
  description: "Software engineering analytics and failure intelligence system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-[#0B0D12] text-[#D8DBE0]">
        <div className="w-full min-h-screen flex">
          <Sidebar />
          <main className="flex-1 flex flex-col">
            <Topbar />
            <div className="flex-1 overflow-auto px-8 py-7">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}