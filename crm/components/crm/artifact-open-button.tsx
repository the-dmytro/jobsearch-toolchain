"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { getArtifactSignedUrl } from "@/lib/actions/artifacts";
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
    const res = await getArtifactSignedUrl(path, artifact.storage_bucket ?? undefined);
    setLoading(false);
    if ("error" in res && res.error) {
      toast.error(res.error);
      return;
    }
    if ("url" in res && res.url) {
      window.open(res.url, "_blank", "noopener,noreferrer");
    }
  }

  return (
    <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void open()}>
      Open file
    </Button>
  );
}
