import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

/**
 * Catches URLs that match no route. This renders without the dashboard shell, so
 * it uses plain links only and stays a Server Component.
 */
export default function NotFound() {
  return (
    <main
      id="main"
      className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center"
    >
      <p className="text-sm font-medium text-muted-foreground">404</p>
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
        <p className="mx-auto max-w-sm text-sm text-muted-foreground">
          That address doesn&apos;t match a page in the CRM. Check the link, or head back to your
          dashboard.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Link href="/" className={buttonVariants({ variant: "default", size: "sm" })}>
          Go to dashboard
        </Link>
        <Link href="/applications" className={buttonVariants({ variant: "outline", size: "sm" })}>
          View applications
        </Link>
      </div>
    </main>
  );
}
