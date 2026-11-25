import { describe, expect, it, vi } from "vitest";

import { DEFAULT_PAGE_SIZE, fetchAll, type PageResult } from "@/lib/fetch-all";

type Row = { id: string };

function rows(count: number): Row[] {
  return Array.from({ length: count }, (_, index) => ({ id: `row-${String(index).padStart(5, "0")}` }));
}

/**
 * Mimics PostgREST keyset paging: rows with id greater than `after`, in id order, capped at
 * `maxRows` per request whatever the page size asked for.
 */
function serve(all: Row[], maxRows = DEFAULT_PAGE_SIZE) {
  const sorted = [...all].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return vi.fn(
    (after: string | null, pageSize: number): Promise<PageResult<Row>> => {
      const remaining = after === null ? sorted : sorted.filter((row) => row.id > after);
      return Promise.resolve({
        data: remaining.slice(0, Math.min(pageSize, maxRows)),
        error: null,
      });
    }
  );
}

describe("fetchAll", () => {
  it("returns an empty list after one request when the table is empty", async () => {
    const build = serve(rows(0));

    await expect(fetchAll(build)).resolves.toEqual([]);
    expect(build).toHaveBeenCalledTimes(1);
    expect(build).toHaveBeenCalledWith(null, DEFAULT_PAGE_SIZE);
  });

  it("asks for the next page after the last id it read, until an empty page", async () => {
    const all = rows(1000);
    const build = serve(all);

    const result = await fetchAll(build);

    expect(result).toHaveLength(1000);
    expect(build.mock.calls).toEqual([
      [null, 1000],
      ["row-00999", 1000],
    ]);
  });

  it("returns every row when the table is one row past a page boundary", async () => {
    const all = rows(1001);
    const build = serve(all);

    const result = await fetchAll(build);

    expect(result).toHaveLength(1001);
    expect(result[1000]).toEqual({ id: "row-01000" });
    expect(build).toHaveBeenCalledTimes(3);
    expect(build).toHaveBeenLastCalledWith("row-01000", 1000);
  });

  it("keeps paging and never repeats a row", async () => {
    const all = rows(2500);
    const build = serve(all);

    const result = await fetchAll(build);

    expect(result).toHaveLength(2500);
    expect(new Set(result.map((row) => row.id)).size).toBe(2500);
    expect(build).toHaveBeenCalledTimes(4);
  });

  it("does not truncate when the server caps pages below the requested size", async () => {
    // Server returns 4 rows per request while 5 are asked for, so pages are short but not the end.
    const all = rows(10);
    const build = serve(all, 4);

    const result = await fetchAll(build, 5);

    expect(result.map((row) => row.id)).toEqual(all.map((row) => row.id));
    expect(build.mock.calls.map((call) => call[0])).toEqual([null, "row-00003", "row-00007", "row-00009"]);
  });

  it("honours a custom page size", async () => {
    const all = rows(5);
    const build = serve(all);

    const result = await fetchAll(build, 2);

    expect(result).toHaveLength(5);
    expect(build.mock.calls).toEqual([
      [null, 2],
      ["row-00001", 2],
      ["row-00003", 2],
      ["row-00004", 2],
    ]);
  });

  it("stops rather than looping when a page brings no new rows", async () => {
    const build = vi.fn(() => Promise.resolve({ data: [{ id: "same" }], error: null }));

    const result = await fetchAll(build);

    expect(result).toEqual([{ id: "same" }]);
    expect(build).toHaveBeenCalledTimes(2);
  });

  it("treats a null page as the end of the table", async () => {
    const build = vi.fn(() => Promise.resolve({ data: null, error: null }));

    await expect(fetchAll(build)).resolves.toEqual([]);
    expect(build).toHaveBeenCalledTimes(1);
  });

  it("throws the query error with its message and keeps its code", async () => {
    const build = vi.fn(() =>
      Promise.resolve({ data: null, error: { message: "permission denied", code: "42501" } })
    );

    let failure: (Error & { code?: string }) | undefined;
    try {
      await fetchAll(build);
    } catch (error) {
      failure = error as Error & { code?: string };
    }
    expect(failure?.message).toBe("permission denied");
    expect(failure?.code).toBe("42501");
  });

  it("throws when a later page fails, instead of returning a partial table", async () => {
    const all = rows(1500);
    const serveAll = serve(all);
    let call = 0;
    const build = vi.fn((after: string | null, pageSize: number) => {
      call += 1;
      if (call === 2) {
        return Promise.resolve({ data: null, error: { message: "statement timeout" } });
      }
      return serveAll(after, pageSize);
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
