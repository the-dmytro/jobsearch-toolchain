"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * False while the component is rendered on the server and during hydration, true once it has
 * mounted in the browser. Use it to keep server-unsafe output (the current time, the local time
 * zone, locale-formatted dates) out of the markup that hydration compares. The server markup shows
 * a stable placeholder instead.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false
  );
}
