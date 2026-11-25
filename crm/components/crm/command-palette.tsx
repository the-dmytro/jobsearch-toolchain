"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Briefcase,
  Building2,
  Calendar,
  Home,
  Lightbulb,
  Mail,
  Mic,
  Search,
  Users,
  Zap,
} from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

const links = [
  { href: "/", label: "Dashboard", icon: Home },
  { href: "/applications", label: "Applications", icon: Briefcase },
  { href: "/opportunities", label: "Opportunities", icon: Search },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/contacts", label: "Contacts", icon: Users },
  { href: "/interviews", label: "Interviews", icon: Calendar },
  { href: "/communications", label: "Communications", icon: Mail },
  { href: "/transcripts", label: "Transcripts", icon: Mic },
  { href: "/runs", label: "Automation runs", icon: Zap },
  { href: "/insights", label: "Insights", icon: Lightbulb },
  { href: "/settings", label: "Settings", icon: Search },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const router = useRouter();

  useEffect(() => {
    function down(e: KeyboardEvent) {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="Jump to a page"
      description="Type a page name, then press Enter to open it."
    >
      <CommandInput placeholder="Jump to page…" aria-label="Search pages" />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {links.map(({ href, label, icon: Icon }) => (
            <CommandItem
              key={href}
              onSelect={() => {
                setOpen(false);
                router.push(href);
              }}
            >
              <Icon className="mr-2 size-4" />
              {label}
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Quick tips">
          <CommandItem disabled>
            On Applications, choose Board to move an application to another stage
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
