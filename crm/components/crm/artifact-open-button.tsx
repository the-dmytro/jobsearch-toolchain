"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { getArtifactSignedUrl } from "@/lib/actions/artifacts";
import { safeExternalUrl } from "@/lib/safe-url";
import type { Tables } from "@/types/database.types";

export function ArtifactOpenButton({ artifact }: { artifact: Tables<"artifacts"> }) {
  const [loading, setLoading] = useState(false);

  async function open() {
    const path = artifact.storage_path;
    if (!path) {
      toast.error("No storage path on artifact");
      return;
    }
    setLoading(true);
    const res = await getArtifactSignedUrl(path);
    setLoading(false);
    if (!res.ok) {
      toast.error(res.message);
      return;
    }
    const href = safeExternalUrl(res.url);
    if (!href) {
      toast.error("Could not open the file. Try again.");
      return;
    }
    window.open(href, "_blank", "noopener,noreferrer");
  }

  return (
    <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void open()}>
      Open file
    </Button>
  );
}
