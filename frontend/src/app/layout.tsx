import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "ToolFall — AI Agent Resilience Demo",
  description: "Watch an AI agent survive real failures, live.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        {/* Navigation */}
        <nav
          className="sticky top-0 z-50 border-b backdrop-blur-md"
          style={{
            background: "rgba(9, 9, 11, 0.85)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-center gap-2.5">
              <span className="text-2xl">⚡</span>
              <span
                className="text-xl font-bold tracking-tight"
                style={{ color: "var(--text)" }}
              >
                ToolFall
              </span>
            </Link>
            <div className="flex items-center gap-6">
              <Link
                href="/"
                className="text-base font-medium transition-colors hover:opacity-100"
                style={{ color: "var(--text-secondary)" }}
              >
                Live Demo
              </Link>
              <Link
                href="/chaos"
                className="text-base font-medium transition-colors hover:opacity-100"
                style={{ color: "var(--text-secondary)" }}
              >
                Chaos Console
              </Link>
              <Link
                href="/eval"
                className="text-base font-medium transition-colors hover:opacity-100"
                style={{ color: "var(--text-secondary)" }}
              >
                Eval Score
              </Link>
            </div>
          </div>
        </nav>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
