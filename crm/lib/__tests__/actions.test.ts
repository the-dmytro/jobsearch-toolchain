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

type FakeConfig = {
  previous?: { current_stage: string | null; status: string };
  readError?: string;
  updateError?: string;
  revertError?: string;
  eventError?: string;
};

type Recorded = {
  table: string;
  op: "select" | "update" | "insert";
  payload?: Record<string, unknown>;
};

/**
 * A minimal chainable stand-in for the Supabase client. Each awaited chain is recorded so
 * tests can check what was written and in which order.
 */
function fakeServerClient(config: FakeConfig) {
  const recorded: Recorded[] = [];
  let applicationUpdates = 0;

  const from = (table: string) => {
    let op: Recorded["op"] = "select";
    let payload: Record<string, unknown> | undefined;

    const execute = () => {
      if (op === "select") {
        if (config.readError) return { data: null, error: { message: config.readError } };
        return { data: config.previous ?? null, error: null };
      }
      recorded.push({ table, op, payload });
      if (op === "update" && table === "applications") {
        applicationUpdates += 1;
        if (applicationUpdates === 1 && config.updateError) {
          return { data: null, error: { message: config.updateError } };
        }
        if (applicationUpdates === 2 && config.revertError) {
          return { data: null, error: { message: config.revertError } };
        }
        return { data: null, error: null };
      }
      if (op === "insert" && config.eventError) {
        return { data: null, error: { message: config.eventError } };
      }
      return { data: null, error: null };
    };

    const builder = {
      select() {
        return builder;
      },
      eq() {
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

const PREVIOUS = { current_stage: "screening", status: "active" };

beforeEach(() => {
  createClient.mockReset();
  revalidatePath.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("changeApplicationStage", () => {
  it("moves the stage and records a stage_change event with from and to stages", async () => {
    const fake = fakeServerClient({ previous: PREVIOUS });
    createClient.mockResolvedValue(fake.client);

    const result = await changeApplicationStage({ applicationId: APPLICATION_ID, newStage: "onsite" });

    expect(result).toEqual({ ok: true });
    expect(fake.recorded.map((r) => [r.table, r.op])).toEqual([
      ["applications", "update"],
      ["application_events", "insert"],
    ]);
    expect(fake.recorded[0].payload).toEqual({ current_stage: "onsite" });
    expect(fake.recorded[1].payload).toMatchObject({
      event_type: "stage_change",
      title: "Stage → onsite",
      metadata: { from_stage: "screening", to_stage: "onsite" },
    });
    expect(revalidatePath).toHaveBeenCalledWith(`/applications/${APPLICATION_ID}`);
  });

  it("restores the previous stage and status when the event cannot be recorded", async () => {
    const fake = fakeServerClient({
      previous: PREVIOUS,
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
    expect(updates[1].payload).toEqual({ current_stage: "screening", status: "active" });
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

  it("stops before writing when the stage update fails", async () => {
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
