import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const getUser = vi.fn();
  const limit = vi.fn();
  const eq = vi.fn(() => ({ limit }));
  const select = vi.fn(() => ({ eq }));
  const from = vi.fn(() => ({ select }));
  const createSignedUrl = vi.fn();
  const storageFrom = vi.fn(() => ({ createSignedUrl }));
  const createAdminClient = vi.fn(() => ({ storage: { from: storageFrom } }));
  return { getUser, limit, eq, select, from, createSignedUrl, storageFrom, createAdminClient };
});

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({ auth: { getUser: mocks.getUser }, from: mocks.from }),
}));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: mocks.createAdminClient }));

import { getArtifactSignedUrl } from "@/lib/actions/artifacts";

const OWNER = { data: { user: { email: "owner@example.com" } }, error: null };
const PATH = "transcripts/2026/call-1.pdf";

describe("getArtifactSignedUrl", () => {
  let consoleError: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.stubEnv("CRM_OWNER_EMAIL", "owner@example.com");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "service-test-value");
    vi.stubEnv("SUPABASE_STORAGE_BUCKET", "");
    mocks.getUser.mockResolvedValue(OWNER);
    mocks.limit.mockResolvedValue({ data: [{ storage_bucket: "job-artifacts" }], error: null });
    mocks.createSignedUrl.mockResolvedValue({
      data: { signedUrl: "https://abcd.supabase.co/storage/v1/object/sign/job-artifacts/x?token=t" },
      error: null,
    });
    consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleError.mockRestore();
    vi.clearAllMocks();
  });

  it("refuses signed-out callers without looking anything up", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: null }, error: null });

    const res = await getArtifactSignedUrl(PATH);

    expect(res).toEqual({ ok: false, message: "Sign in to open this file." });
    expect(mocks.from).not.toHaveBeenCalled();
    expect(mocks.createSignedUrl).not.toHaveBeenCalled();
  });

  it("refuses signed-in non-owners", async () => {
    mocks.getUser.mockResolvedValue({ data: { user: { email: "stranger@example.com" } }, error: null });

    const res = await getArtifactSignedUrl(PATH);

    expect(res).toEqual({ ok: false, message: "You do not have access to this file." });
    expect(mocks.from).not.toHaveBeenCalled();
    expect(mocks.createSignedUrl).not.toHaveBeenCalled();
  });

  it("rejects a bad path before touching auth or storage", async () => {
    const res = await getArtifactSignedUrl("../secrets.pdf");

    expect(res).toEqual({ ok: false, message: "This file path is not valid." });
    expect(mocks.getUser).not.toHaveBeenCalled();
    expect(mocks.createSignedUrl).not.toHaveBeenCalled();
  });

  it("signs nothing when no artifact row matches the path", async () => {
    mocks.limit.mockResolvedValue({ data: [], error: null });

    const res = await getArtifactSignedUrl(PATH);

    expect(res).toEqual({ ok: false, message: "File not found." });
    expect(mocks.from).toHaveBeenCalledWith("artifacts");
    expect(mocks.eq).toHaveBeenCalledWith("storage_path", PATH);
    expect(mocks.createSignedUrl).not.toHaveBeenCalled();
  });

  it("refuses an artifact stored in a non-default bucket", async () => {
    mocks.limit.mockResolvedValue({ data: [{ storage_bucket: "someone-elses-bucket" }], error: null });

    const res = await getArtifactSignedUrl(PATH);

    expect(res).toEqual({ ok: false, message: "Could not open the file. Try again." });
    expect(mocks.storageFrom).not.toHaveBeenCalled();
    expect(mocks.createSignedUrl).not.toHaveBeenCalled();
  });

  it("returns a generic message on a storage error and does not leak details", async () => {
    mocks.createSignedUrl.mockResolvedValue({
      data: null,
      error: { message: "internal detail: bucket policy row 42" },
    });

    const res = await getArtifactSignedUrl(PATH);

    expect(res).toEqual({ ok: false, message: "Could not open the file. Try again." });
    expect(JSON.stringify(res)).not.toContain("internal detail");
    expect(consoleError).toHaveBeenCalled();
  });

  it("returns a generic message when the lookup itself fails", async () => {
    mocks.limit.mockResolvedValue({ data: null, error: { message: "permission denied for table artifacts" } });

    const res = await getArtifactSignedUrl(PATH);

    expect(res).toEqual({ ok: false, message: "Could not open the file. Try again." });
    expect(JSON.stringify(res)).not.toContain("permission denied");
    expect(mocks.createSignedUrl).not.toHaveBeenCalled();
  });

  it("returns a generic message when the service key is missing", async () => {
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "");
    vi.stubEnv("SUPABASE_SECRET_KEY", "");

    const res = await getArtifactSignedUrl(PATH);

    expect(res).toEqual({ ok: false, message: "Could not open the file. Try again." });
    expect(JSON.stringify(res)).not.toContain("SUPABASE_");
  });

  it("signs a 60 second URL in the default bucket on success", async () => {
    const res = await getArtifactSignedUrl(PATH);

    expect(res).toEqual({
      ok: true,
      url: "https://abcd.supabase.co/storage/v1/object/sign/job-artifacts/x?token=t",
    });
    expect(mocks.storageFrom).toHaveBeenCalledWith("job-artifacts");
    expect(mocks.createSignedUrl).toHaveBeenCalledWith(PATH, 60);
  });

  it("treats a row without a bucket as the default bucket", async () => {
    mocks.limit.mockResolvedValue({ data: [{ storage_bucket: null }], error: null });

    const res = await getArtifactSignedUrl(PATH);

    expect(res.ok).toBe(true);
    expect(mocks.storageFrom).toHaveBeenCalledWith("job-artifacts");
  });
});
