"use client";

import "./globals.css";

import { useEffect } from "react";

/**
 * Last-resort boundary. It replaces the root layout, so it renders its own
 * <html> and <body> and imports the global stylesheet itself.
 *
 * The app theme is stored by next-themes under the "theme" key. This reads it,
 * then applies the `dark` class so the page matches what the person chose. If
 * storage is unavailable, it falls back to the OS setting.
 */
export default function GlobalError({
  error,
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
    try {
      const stored = window.localStorage.getItem("theme");
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const dark = stored === "dark" || (stored !== "light" && prefersDark);
      document.documentElement.classList.toggle("dark", dark);
    } catch {
      /* Storage or matchMedia can be blocked. The default light theme is fine. */
    }
  }, [error]);

  return (
    <html lang="en">
      <head>
        <title>Something went wrong · JobSearch CRM</title>
      </head>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <main
          id="main"
          className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center"
        >
          <div role="alert" className="space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight">Something went wrong</h1>
            <p className="mx-auto max-w-sm text-sm text-muted-foreground">
              The app hit an unexpected problem. Try again. If it keeps happening, sign in again.
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              onClick={() => retry()}
              className="inline-flex h-8 items-center justify-center rounded-lg bg-primary px-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              Try again
            </button>
            <a
              href="/login"
              className="inline-flex h-8 items-center justify-center rounded-lg border border-border bg-background px-2.5 text-sm font-medium hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              Sign in again
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
