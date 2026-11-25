import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ArtifactOpenButton } from "@/components/crm/artifact-open-button";
import type { Tables } from "@/types/database.types";

const artifacts = vi.hoisted(() => ({ getArtifactSignedUrl: vi.fn() }));
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }));

vi.mock("@/lib/actions/artifacts", () => ({
  getArtifactSignedUrl: artifacts.getArtifactSignedUrl,
}));
vi.mock("sonner", () => ({ toast }));

function artifact(storagePath: string | null): Tables<"artifacts"> {
  return {
    id: "art-1",
    artifact_type: "transcript",
    title: "Interview transcript",
    storage_bucket: "files",
    storage_path: storagePath,
    local_path: null,
    mime_type: "text/plain",
    sha256: null,
    size_bytes: null,
    related_type: null,
    related_id: null,
    metadata: {},
    created_at: "2026-11-01T09:00:00Z",
  } as Tables<"artifacts">;
}

function fakeTab() {
  return { location: { href: "about:blank" }, close: vi.fn(), opener: undefined as unknown };
}

let tab: ReturnType<typeof fakeTab>;

beforeEach(() => {
  tab = fakeTab();
  artifacts.getArtifactSignedUrl.mockReset();
  toast.error.mockReset();
  vi.spyOn(window, "open").mockImplementation(() => tab as unknown as Window);
});

describe("ArtifactOpenButton", () => {
  it("opens the tab synchronously on click, then points it at the signed link", async () => {
    let resolveUrl!: (value: { ok: true; url: string }) => void;
    artifacts.getArtifactSignedUrl.mockReturnValue(
      new Promise((resolve) => {
        resolveUrl = resolve;
      })
    );
    render(<ArtifactOpenButton artifact={artifact("transcripts/one.txt")} />);

    fireEvent.click(screen.getByRole("button", { name: "Open file" }));

    // The window exists before the signed link has been requested or returned.
    expect(window.open).toHaveBeenCalledWith("", "_blank");
    expect(artifacts.getArtifactSignedUrl).toHaveBeenCalledWith("transcripts/one.txt");
    expect(tab.location.href).toBe("about:blank");
    expect(screen.getByRole("button", { name: "Opening…" })).toBeDisabled();

    await act(async () => {
      resolveUrl({ ok: true, url: "https://files.example.test/signed/one.txt?token=abc" });
    });

    await waitFor(() =>
      expect(tab.location.href).toBe("https://files.example.test/signed/one.txt?token=abc")
    );
    expect(tab.opener).toBeNull();
    expect(tab.close).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("closes the tab and shows the message when the signed link cannot be made", async () => {
    artifacts.getArtifactSignedUrl.mockResolvedValue({ ok: false, message: "File not found." });
    render(<ArtifactOpenButton artifact={artifact("transcripts/two.txt")} />);

    fireEvent.click(screen.getByRole("button", { name: "Open file" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("File not found."));
    expect(tab.close).toHaveBeenCalledTimes(1);
    expect(tab.location.href).toBe("about:blank");
  });

  it("refuses an unsafe link, closes the tab, and says the file could not be opened", async () => {
    artifacts.getArtifactSignedUrl.mockResolvedValue({ ok: true, url: "javascript:alert(1)" });
    render(<ArtifactOpenButton artifact={artifact("transcripts/three.txt")} />);

    fireEvent.click(screen.getByRole("button", { name: "Open file" }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Couldn't open the file. Try again."));
    expect(tab.close).toHaveBeenCalledTimes(1);
    expect(tab.location.href).toBe("about:blank");
  });

  it("explains a blocked pop-up without asking for a signed link", () => {
    vi.mocked(window.open).mockReturnValue(null);
    render(<ArtifactOpenButton artifact={artifact("transcripts/four.txt")} />);

    fireEvent.click(screen.getByRole("button", { name: "Open file" }));

    expect(artifacts.getArtifactSignedUrl).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/blocked the new tab/));
  });

  it("uses a plain message instead of 'No storage path' when the file has no path", () => {
    render(<ArtifactOpenButton artifact={artifact(null)} />);

    fireEvent.click(screen.getByRole("button", { name: "Open file" }));

    expect(window.open).not.toHaveBeenCalled();
    expect(artifacts.getArtifactSignedUrl).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith("This file isn't available to open yet.");
  });
});
