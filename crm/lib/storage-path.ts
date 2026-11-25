const MAX_LENGTH = 1024;
// Control characters, including NUL, DEL and all C0 controls.
const CONTROL_CHARS = /[\x00-\x1f\x7f]/;
// Characters that would be interpreted by a URL or a filesystem path, or that could
// smuggle an encoded traversal (for example "%2e%2e").
const FORBIDDEN_CHARS = /[\\%?#]/;

/**
 * Relative object key inside a storage bucket. Validated segment by segment, so
 * "file..pdf" is fine but "..", ".", empty segments (leading, trailing or doubled
 * slashes) and anything that changes how the key is parsed are not.
 */
export function isSafeStoragePath(path: string): boolean {
  if (typeof path !== "string") return false;
  if (path.length === 0 || path.length > MAX_LENGTH) return false;
  if (path !== path.trim()) return false;
  if (path.startsWith("/")) return false;
  if (CONTROL_CHARS.test(path) || FORBIDDEN_CHARS.test(path)) return false;
  return path
    .split("/")
    .every((segment) => segment !== "" && segment !== "." && segment !== "..");
}
