import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { createClient, revalidatePath } = vi.hoisted(() => ({
  createClient: vi.fn(),
  revalidatePath: vi.fn(),
}));

vi.mock("@/lib/supabase/server", () => ({ createClient }));
vi.mock("next/cache", () => ({ revalidatePath }));

import { changeApplicationStage, updateApplication } from "@/lib/actions/applications";
import { createContact } from "@/lib/actions/contacts";

const APPLICATION_ID = "11111111-1111-4111-8111-111111111111";

type Previous = { current_stage: string | null; status: string; outcome: string | null };

type FakeConfig = {
  previous?: Previous;
  readError?: string;
  /** Error for the first stage write. */
  updateError?: string;
  /** Error for the revert write. */
  revertError?: string;
  eventError?: string;
  /** Rows the first (compare-and-set) stage write matches. Defaults to 1. */
  changedRows?: number;
  /** Rows the revert matches. Defaults to 1. */
  revertRows?: number;
};

type Recorded = {
  table: string;
  op: "update" | "insert";
  payload?: Record<string, unknown>;
  filters?: Array<[string, "eq" | "is", unknown]>;
};

/**
 * A minimal chainable stand-in for the Supabase client. Writes are recorded with the filters they
 * were guarded by, so tests can check the compare-and-set conditions as well as the values.
 */
function fakeServerClient(config: FakeConfig) {
  const recorded: Recorded[] = [];
  let applicationUpdates = 0;

  const from = (table: string) => {
    let op: "select" | "update" | "insert" = "select";
    let payload: Record<string, unknown> | undefined;
    const filters: Array<[string, "eq" | "is", unknown]> = [];

    const execute = () => {
      if (op === "select") {
        if (config.readError) return { data: null, error: { message: config.readError } };
        return { data: config.previous ?? null, error: null };
      }
      if (op === "update" && table === "applications") {
        applicationUpdates += 1;
        recorded.push({ table, op, payload, filters: [...filters] });
        const isRevert = applicationUpdates > 1;
        if (isRevert && config.revertError) return { data: null, error: { message: config.revertError } };
        if (!isRevert && config.updateError) return { data: null, error: { message: config.updateError } };
        const rows = isRevert ? (config.revertRows ?? 1) : (config.changedRows ?? 1);
        return { data: Array.from({ length: rows }, () => ({ id: APPLICATION_ID })), error: null };
      }
      recorded.push({ table, op: "insert", payload });
      if (config.eventError) return { data: null, error: { message: config.eventError } };
      return { data: null, error: null };
    };

    const builder = {
      select() {
        return builder;
      },
      eq(column: string, value: unknown) {
        filters.push([column, "eq", value]);
        return builder;
      },
      is(column: string, value: unknown) {
        filters.push([column, "is", value]);
        return builder;
      },
      single() {
        return Promise.resolve(execute());
      },
      update(values: Record<string, unknown>) {
        op = "update";
        payload = values;
        return builder;
      },
      insert(values: Record<string, unknown>) {
        op = "insert";
        payload = values;
        return builder;
      },
      then(onFulfilled?: (value: unknown) => unknown, onRejected?: (reason: unknown) => unknown) {
        return Promise.resolve(execute()).then(onFulfilled, onRejected);
      },
    };
    return builder;
  };

  return { client: { from }, recorded };
}

const PREVIOUS: Previous = { current_stage: "screening", status: "interviewing", outcome: null };
const CLOSED_PREVIOUS: Previous = {
  current_stage: "Rejected after screen",
  status: "rejected",
  outcome: "rejected",
};
const CHANGED_ELSEWHERE = "This application changed elsewhere. Refresh and try again.";

beforeEach(() => {
  createClient.mockReset();
  revalidatePath.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("changeApplicationStage", () => {
  it("moves the stage, with its status and outcome, and records a stage_change event", async () => {
    const fake = fakeServerClient({ previous: PREVIOUS });
    createClient.mockResolvedValue(fake.client);

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(result).toEqual({ ok: true });
    expect(fake.recorded.map((r) => [r.table, r.op])).toEqual([
      ["applications", "update"],
      ["application_events", "insert"],
    ]);
    expect(fake.recorded[0].payload).toEqual({ current_stage: "onsite", status: "interviewing", outcome: null });
    expect(fake.recorded[0].filters).toContainEqual(["current_stage", "eq", "screening"]);
    expect(fake.recorded[1].payload).toMatchObject({
      event_type: "stage_change",
      title: "Stage → onsite",
      metadata: { from_stage: "screening", to_stage: "onsite" },
    });
    expect(revalidatePath).toHaveBeenCalledWith(`/applications/${APPLICATION_ID}`);
  });

  it("clears the rejection when an application leaves Closed", async () => {
    const fake = fakeServerClient({ previous: CLOSED_PREVIOUS });
    createClient.mockResolvedValue(fake.client);

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "screening" });

    expect(result).toEqual({ ok: true });
    expect(fake.recorded[0].payload).toEqual({ current_stage: "screening", status: "interviewing", outcome: null });
    expect(fake.recorded[0].filters).toContainEqual(["current_stage", "eq", "Rejected after screen"]);
  });

  it("writes the rejection with status and outcome when the column is Closed", async () => {
    const fake = fakeServerClient({ previous: PREVIOUS });
    createClient.mockResolvedValue(fake.client);

    await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "rejected" });

    expect(fake.recorded[0].payload).toEqual({ current_stage: "rejected", status: "rejected", outcome: "rejected" });
    expect(fake.recorded[1].payload).toMatchObject({ metadata: { to_stage: "rejected" } });
  });

  it("guards a null stage with an IS NULL condition", async () => {
    const fake = fakeServerClient({ previous: { current_stage: null, status: "applied", outcome: null } });
    createClient.mockResolvedValue(fake.client);

    await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "applied" });

    expect(fake.recorded[0].filters).toContainEqual(["current_stage", "is", null]);
  });

  it("reports a change elsewhere, and records no event, when the compare-and-set matches no row", async () => {
    const fake = fakeServerClient({ previous: PREVIOUS, changedRows: 0 });
    createClient.mockResolvedValue(fake.client);

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(result).toEqual({ ok: false, message: CHANGED_ELSEWHERE });
    expect(fake.recorded.map((r) => r.table)).toEqual(["applications"]);
  });

  it("restores the previous stage, status and outcome under the same condition when the event cannot be recorded", async () => {
    const fake = fakeServerClient({
      previous: CLOSED_PREVIOUS,
      eventError: 'insert rejected: relation "application_events" permission denied',
    });
    createClient.mockResolvedValue(fake.client);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(result).toEqual({
      ok: false,
      message: "The stage change could not be recorded, so the stage was left unchanged. Try again.",
    });
    const updates = fake.recorded.filter((r) => r.op === "update");
    expect(updates).toHaveLength(2);
    expect(updates[1].payload).toEqual({
      current_stage: "Rejected after screen",
      status: "rejected",
      outcome: "rejected",
    });
    expect(updates[1].filters).toContainEqual(["current_stage", "eq", "onsite"]);
    expect(consoleError).toHaveBeenCalledWith(expect.stringContaining("permission denied"));
  });

  it("never sends the raw database error to the client", async () => {
    const fake = fakeServerClient({
      previous: PREVIOUS,
      eventError: 'insert rejected: relation "application_events" permission denied',
    });
    createClient.mockResolvedValue(fake.client);
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(JSON.stringify(result)).not.toContain("permission denied");
    expect(JSON.stringify(result)).not.toContain("application_events");
  });

  it("says so when the revert also fails", async () => {
    const fake = fakeServerClient({
      previous: PREVIOUS,
      eventError: "insert failed",
      revertError: "update failed",
    });
    createClient.mockResolvedValue(fake.client);
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(result.ok).toBe(false);
    expect(result).toMatchObject({ message: expect.stringContaining("Refresh and check the stage") });
  });

  it("says so when the revert matches no row, because the stage changed again meanwhile", async () => {
    const fake = fakeServerClient({ previous: PREVIOUS, eventError: "insert failed", revertRows: 0 });
    createClient.mockResolvedValue(fake.client);
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(result).toMatchObject({ ok: false, message: expect.stringContaining("Refresh and check the stage") });
  });

  it("stops before writing an event when the stage update fails", async () => {
    const fake = fakeServerClient({ previous: PREVIOUS, updateError: "row locked" });
    createClient.mockResolvedValue(fake.client);
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(result).toEqual({ ok: false, message: "Could not move the application. Try again." });
    expect(fake.recorded.map((r) => r.table)).toEqual(["applications"]);
  });

  it("returns a not-found message when the application cannot be read", async () => {
    const fake = fakeServerClient({ readError: "JSON object requested, multiple (or no) rows returned" });
    createClient.mockResolvedValue(fake.client);
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(result).toEqual({ ok: false, message: "Could not find this application." });
    expect(fake.recorded).toHaveLength(0);
  });

  it("rejects a stage outside the board vocabulary before touching the database", async () => {
    createClient.mockResolvedValue(fakeServerClient({}).client);

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "declined" });

    expect(result).toEqual({ ok: false, message: "Check newStage and try again." });
    expect(createClient).not.toHaveBeenCalled();
  });

  it("rejects invalid input before touching the database", async () => {
    createClient.mockResolvedValue(fakeServerClient({}).client);

    const result = await changeApplicationStage({ applicationId: "not-a-uuid", newStage: "" });

    expect(result).toEqual({ ok: false, message: "Check applicationId, newStage and try again." });
    expect(createClient).not.toHaveBeenCalled();
  });
});

describe("updateApplication", () => {
  it("returns a plain message when the update fails", async () => {
    const fake = fakeServerClient({ updateError: "column does not exist" });
    createClient.mockResolvedValue(fake.client);
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await updateApplication({ id: APPLICATION_ID, notes: "hello" });

    expect(result).toEqual({ ok: false, message: "Could not save the application. Try again." });
  });

  it("returns ok on success", async () => {
    createClient.mockResolvedValue(fakeServerClient({}).client);

    await expect(updateApplication({ id: APPLICATION_ID, notes: "hello" })).resolves.toEqual({ ok: true });
  });

  it.each([
    ["current_stage", { current_stage: "onsite" }],
    ["status", { status: "offer" }],
    ["outcome", { outcome: "rejected" }],
  ])("rejects a %s key before touching the database", async (_name, extra) => {
    const fake = fakeServerClient({});
    createClient.mockResolvedValue(fake.client);

    const result = await updateApplication({ id: APPLICATION_ID, notes: "hello", ...extra });

    expect(result.ok).toBe(false);
    expect(createClient).not.toHaveBeenCalled();
    expect(fake.recorded).toHaveLength(0);
  });

  it("writes only the keys it was sent", async () => {
    const fake = fakeServerClient({});
    createClient.mockResolvedValue(fake.client);

    await updateApplication({ id: APPLICATION_ID, salary_requested_text: "80k" });

    expect(fake.recorded).toEqual([
      { table: "applications", op: "update", payload: { salary_requested_text: "80k" }, filters: [["id", "eq", APPLICATION_ID]] },
    ]);
  });

  it("succeeds without a write when the payload has no editable fields", async () => {
    const fake = fakeServerClient({});
    createClient.mockResolvedValue(fake.client);

    await expect(updateApplication({ id: APPLICATION_ID })).resolves.toEqual({ ok: true });
    expect(fake.recorded).toHaveLength(0);
  });
});

describe("createContact", () => {
  it("returns the new id in data", async () => {
    const client = {
      from: () => ({
        insert: () => ({
          select: () => ({ single: () => Promise.resolve({ data: { id: "contact-1" }, error: null }) }),
        }),
      }),
    };
    createClient.mockResolvedValue(client);

    await expect(
      createContact({ organization_id: APPLICATION_ID, full_name: "Ada Lovelace", email: "" })
    ).resolves.toEqual({ ok: true, data: { id: "contact-1" } });
  });

  it("returns a generic message when the insert fails", async () => {
    const client = {
      from: () => ({
        insert: () => ({
          select: () => ({
            single: () => Promise.resolve({ data: null, error: { message: "duplicate key" } }),
          }),
        }),
      }),
    };
    createClient.mockResolvedValue(client);
    vi.spyOn(console, "error").mockImplementation(() => {});

    const result = await createContact({ organization_id: APPLICATION_ID, full_name: "Ada" });

    expect(result).toEqual({ ok: false, message: "Could not save the contact. Try again." });
  });
});
