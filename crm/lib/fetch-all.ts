/**
 * PostgREST returns at most 1000 rows per request, so an unbounded `select` silently
 * truncates. `fetchAll` walks the table with `.range(from, to)` until a short page.
 *
 * The caller must supply a stable `order` (for example `order('id')`) inside `build`,
 * otherwise pages can overlap or skip rows.
 */
export const DEFAULT_PAGE_SIZE = 1000;

export type PageResult<T> = {
  data: T[] | null;
  error: { message: string } | null;
};

export async function fetchAll<T>(
  build: (from: number, to: number) => PromiseLike<PageResult<T>>,
  pageSize: number = DEFAULT_PAGE_SIZE
): Promise<T[]> {
  if (!Number.isInteger(pageSize) || pageSize < 1) {
    throw new Error("fetchAll: pageSize must be a positive integer");
  }

  const rows: T[] = [];
  for (let from = 0; ; from += pageSize) {
    const { data, error } = await build(from, from + pageSize - 1);
    if (error) {
      throw new Error(error.message || "Failed to load rows");
    }
    const page = data ?? [];
    for (const row of page) rows.push(row);
    if (page.length < pageSize) break;
  }
  return rows;
}
