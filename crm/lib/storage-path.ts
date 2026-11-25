/** Relative object keys only: no leading slash, no "..", no backslashes, no NUL. */
export function isSafeStoragePath(path: string): boolean {
  if (typeof path !== "string") return false;
  if (path.trim() === "") return false;
  if (path.startsWith("/")) return false;
  if (path.includes("..")) return false;
  if (path.includes("\\")) return false;
  if (path.includes("\0")) return false;
  return true;
}
