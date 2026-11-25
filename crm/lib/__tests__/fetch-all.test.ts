import { describe, expect, it, vi } from "vitest";

import { DEFAULT_PAGE_SIZE, fetchAll, type PageResult } from "@/lib/fetch-all";

type Row = { id: number };

function rows(count: number): Row[] {
  return Array.from({ length: count }, (_, id) => ({ id }));
}

/** Mimics PostgREST: `.range(from, to)` returns that slice, capped at `maxRows` per request. */
function serve(all: Row[], maxRows = DEFAULT_PAGE_SIZE) {
  return vi.fn(
    (from: number, to: number): Promise<PageResult<Row>> =>
      Promise.resolve({
        data: all.slice(from, Math.min(to + 1, from + maxRows)),
        error: null,
      })
  );
}

describe("fetchAll", () => {
  it("returns an empty list after one request when the table is empty", async () => {
    const build = serve(rows(0));

    await expect(fetchAll(build)).resolves.toEqual([]);
    expect(build).toHaveBeenCalledTimes(1);
    expect(build).toHaveBeenCalledWith(0, 999);
  });

  it("requests a second page when exactly one page is full", async () => {
    const all = rows(1000);
    const build = serve(all);

    const result = await fetchAll(build);

    expect(result).toHaveLength(1000);
    expect(build.mock.calls).toEqual([
      [0, 999],
      [1000, 1999],
    ]);
  });

  it("returns every row when the table is one row past a page boundary", async () => {
    const all = rows(1001);
    const build = serve(all);

    const result = await fetchAll(build);

    expect(result).toHaveLength(1001);
    expect(result[1000]).toEqual({ id: 1000 });
    expect(build).toHaveBeenCalledTimes(2);
    expect(build).toHaveBeenLastCalledWith(1000, 1999);
  });

  it("keeps paging until a short page arrives and never repeats a row", async () => {
    const all = rows(2500);
    const build = serve(all);

    const result = await fetchAll(build);

    expect(result).toHaveLength(2500);
    expect(new Set(result.map((row) => row.id)).size).toBe(2500);
    expect(build).toHaveBeenCalledTimes(3);
  });

  it("stops on a short page even when the server caps pages below the requested size", async () => {
    const all = rows(10);
    const build = serve(all, 4);

    // Server returns 4 rows per request, so pages of 5 are short after the first.
    const result = await fetchAll(build, 5);

    expect(result).toHaveLength(4);
    expect(build).toHaveBeenCalledTimes(1);
  });

  it("honours a custom page size", async () => {
    const all = rows(5);
    const build = serve(all);

    const result = await fetchAll(build, 2);

    expect(result).toHaveLength(5);
    expect(build.mock.calls).toEqual([
      [0, 1],
      [2, 3],
      [4, 5],
    ]);
  });

  it("treats a null page as the end of the table", async () => {
    const build = vi.fn(() => Promise.resolve({ data: null, error: null }));

    await expect(fetchAll(build)).resolves.toEqual([]);
    expect(build).toHaveBeenCalledTimes(1);
  });

  it("throws the query error with its message", async () => {
    const build = vi.fn(() =>
      Promise.resolve({ data: null, error: { message: "permission denied" } })
    );

    await expect(fetchAll(build)).rejects.toThrow("permission denied");
  });

  it("throws when a later page fails, instead of returning a partial table", async () => {
    const all = rows(1500);
    let call = 0;
    const build = vi.fn((from: number, to: number) => {
      call += 1;
      if (call === 2) {
        return Promise.resolve({ data: null, error: { message: "statement timeout" } });
      }
      return Promise.resolve({ data: all.slice(from, to + 1), error: null });
    });

    await expect(fetchAll(build)).rejects.toThrow("statement timeout");
    expect(build).toHaveBeenCalledTimes(2);
  });

  it("rejects a page size that is not a positive integer", async () => {
    const build = serve(rows(3));

    await expect(fetchAll(build, 0)).rejects.toThrow("pageSize");
    await expect(fetchAll(build, 2.5)).rejects.toThrow("pageSize");
    expect(build).not.toHaveBeenCalled();
  });
});
