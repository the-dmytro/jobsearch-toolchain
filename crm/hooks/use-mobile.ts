"use client";

import * as React from "react";

const MOBILE_BREAKPOINT = 768;

function getSnapshot() {
  if (typeof window === "undefined") return false;
  return window.innerWidth < MOBILE_BREAKPOINT;
}

function getServerSnapshot() {
  return false;
}

function subscribe(onStoreChange: () => void) {
  const handler = () => onStoreChange();
  const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`);
  mql.addEventListener("change", handler);
  window.addEventListener("resize", handler);
  return () => {
    mql.removeEventListener("change", handler);
    window.removeEventListener("resize", handler);
  };
}

export function useIsMobile() {
  return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
