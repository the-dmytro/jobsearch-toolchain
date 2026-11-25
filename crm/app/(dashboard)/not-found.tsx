import Link from "next/link";
import { CompassIcon } from "lucide-react";

import { EmptyState } from "@/components/crm/empty-state";
import { buttonVariants } from "@/components/ui/button";

/** Shown inside the dashboard shell when a dashboard page calls `notFound()`. */
export default function DashboardNotFound() {
  return (
    <div className="mx-auto w-full max-w-lg py-8">
      <EmptyState
        icon={<CompassIcon className="size-5" />}
        title="We couldn't find that page"
        description="The link may be out of date, or the record may have been removed."
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Link href="/" className={buttonVariants({ variant: "default", size: "sm" })}>
              Go to dashboard
            </Link>
            <Link href="/applications" className={buttonVariants({ variant: "outline", size: "sm" })}>
              View applications
            </Link>
          </div>
        }
      />
    </div>
  );
}
