"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DateRangePicker } from "@/components/crm/date-range-picker";
import { ThemeToggle } from "@/components/crm/theme-toggle";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import {
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { isDemoMode } from "@/lib/demo";
import { Badge } from "@/components/ui/badge";

const LABELS: Record<string, string> = {
  applications: "Applications",
  opportunities: "Opportunities",
  companies: "Companies",
  contacts: "Contacts",
  interviews: "Interviews",
  communications: "Communications",
  transcripts: "Transcripts",
  runs: "Automation runs",
  insights: "Insights",
  settings: "Settings",
};

function breadcrumbSegments(pathname: string) {
  if (pathname === "/") {
    return [{ href: "/", label: "Dashboard" }];
  }

  const parts = pathname.split("/").filter(Boolean);
  return parts.map((part, index) => {
    const href = `/${parts.slice(0, index + 1).join("/")}`;
    const label = LABELS[part] ?? part.replace(/-/g, " ");
    return { href, label };
  });
}

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const segments = breadcrumbSegments(pathname);

  return (
    <>
      <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 h-6" />
        <Breadcrumb className="min-w-0 flex-1">
          <BreadcrumbList>
            {segments.map((segment, index) => {
              const isLast = index === segments.length - 1;
              return (
                <span key={segment.href} className="contents">
                  <BreadcrumbItem>
                    {isLast ? (
                      <BreadcrumbPage className="capitalize">
                        {segment.label}
                      </BreadcrumbPage>
                    ) : (
                      <BreadcrumbLink
                        render={<Link href={segment.href} />}
                        className="capitalize"
                      >
                        {segment.label}
                      </BreadcrumbLink>
                    )}
                  </BreadcrumbItem>
                  {!isLast ? <BreadcrumbSeparator /> : null}
                </span>
              );
            })}
          </BreadcrumbList>
        </Breadcrumb>
        <div className="flex items-center gap-1">
          {isDemoMode() ? (
            <Badge variant="secondary" className="hidden sm:inline-flex">
              Demo mode
            </Badge>
          ) : null}
          <DateRangePicker />
          <ThemeToggle />
        </div>
      </header>
      <main className="flex-1 overflow-auto p-4 md:p-6">{children}</main>
    </>
  );
}
