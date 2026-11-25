"use client";

import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const subscribe = () => () => undefined;
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

const OPTIONS = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

/**
 * Theme chooser with three options: System, Light and Dark. The choice is saved
 * on this device by next-themes. The buttons stay disabled until the client has
 * mounted, so the first render matches the server.
 */
export function ThemeSelect() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(subscribe, getClientSnapshot, getServerSnapshot);
  const current = mounted ? (theme ?? "system") : undefined;

  return (
    <div role="group" aria-label="Theme" className="inline-flex flex-wrap gap-1 rounded-lg border p-1">
      {OPTIONS.map((option) => {
        const selected = current === option.value;
        return (
          <Button
            key={option.value}
            type="button"
            size="sm"
            variant={selected ? "secondary" : "ghost"}
            aria-pressed={selected}
            disabled={!mounted}
            className={cn("h-7 px-3 text-xs", selected && "font-semibold")}
            onClick={() => setTheme(option.value)}
          >
            {option.label}
          </Button>
        );
      })}
    </div>
  );
}
