"use client";

import { LoaderCircleIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { getArtifactSignedUrl } from "@/lib/actions/artifacts";
import { safeExternalUrl } from "@/lib/safe-url";
import type { Tables } from "@/types/database.types";

const NO_FILE_MESSAGE = "This file isn't available to open yet.";
const OPEN_FAILED_MESSAGE = "Couldn't open the file. Try again.";
const BLOCKED_MESSAGE = "Your browser blocked the new tab. Allow pop-ups for this site and try again.";

/**
 * Opens a stored file in a new tab through a short-lived signed link.
 *
 * The tab is opened synchronously on the click, so browsers allow it as a user
 * action. Its address is set once the signed link arrives. If anything fails,
 * the tab is closed and the user sees a message.
 */
export function ArtifactOpenButton({ artifact }: { artifact: Tables<"artifacts"> }) {
  const [loading, setLoading] = useState(false);

  async function open() {
    const path = artifact.storage_path;
    if (!path) {
      toast.error(NO_FILE_MESSAGE);
      return;
    }

    // Open the tab first, while the click still counts as a user action.
    const tab = window.open("", "_blank");
    if (!tab) {
      toast.error(BLOCKED_MESSAGE);
      return;
    }
    tab.opener = null;

    setLoading(true);
    try {
      const result = await getArtifactSignedUrl(path);
      if (!result.ok) {
        tab.close();
        toast.error(result.message);
        return;
      }
      const href = safeExternalUrl(result.url);
      if (!href) {
        tab.close();
        toast.error(OPEN_FAILED_MESSAGE);
        return;
      }
      tab.location.href = href;
    } catch {
      tab.close();
      toast.error(OPEN_FAILED_MESSAGE);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      disabled={loading}
      aria-busy={loading || undefined}
      onClick={() => void open()}
    >
      {loading ? <LoaderCircleIcon aria-hidden="true" className="animate-spin motion-reduce:animate-none" /> : null}
      {loading ? "Opening…" : "Open file"}
    </Button>
  );
}
