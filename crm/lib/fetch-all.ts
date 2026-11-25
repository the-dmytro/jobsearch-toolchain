/**
 * PostgREST caps each response (1000 rows by default), so an unbounded `select` silently
 * truncates. `fetchAll` reads a table in keyset pages: each request asks for the rows whose `id`
 * is greater than the last id already read, ordered by `id`. Offset paging is avoided because a
 * row written between two requests would shift the window and be skipped or repeated.
 *
 * `build(after, pageSize)` must return a query ordered by `id` that applies `gt('id', after)`
 * when `after` is set and `limit(pageSize)`. Paging stops on an empty page, not on a short one,
 * because the server may cap a page below the size asked for. Rows are deduplicated by id.
 */
export const DEFAULT_PAGE_SIZE = 1000;

export type PageError = { message: string; code?: string };

export type PageResult<T> = {
  data: T[] | null;
  error: PageError | null;
};

export type KeysetRow = { id: string };

/** An Error that keeps the PostgREST or Postgres `code`, so friendly messages can map it. */
export type QueryError = Error & { code?: string };

export function queryError(error: PageError): QueryError {
  const err: QueryError = new Error(error.message || "Failed to load rows");
  if (error.code) err.code = error.code;
  return err;
}

export async function fetchAll<T extends KeysetRow>(
  build: (after: string | null, pageSize: number) => PromiseLike<PageResult<T>>,
  pageSize: number = DEFAULT_PAGE_SIZE
): Promise<T[]> {
  if (!Number.isInteger(pageSize) || pageSize < 1) {
    throw new Error("fetchAll: pageSize must be a positive integer");
  }

  const rows: T[] = [];
  const seen = new Set<string>();
  let after: string | null = null;
  for (;;) {
    const { data, error } = await build(after, pageSize);
    if (error) throw queryError(error);

    const page = data ?? [];
    if (page.length === 0) break;

    let added = 0;
    for (const row of page) {
      if (seen.has(row.id)) continue;
      seen.add(row.id);
      rows.push(row);
      added += 1;
    }
    // A page with nothing new means the builder ignored `after`. Stop rather than loop forever.
    if (added === 0) break;
    after = page[page.length - 1].id;
  }
  return rows;
}
