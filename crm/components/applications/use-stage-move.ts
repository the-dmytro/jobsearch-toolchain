"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { changeApplicationStage } from "@/lib/actions/applications";
import { invalidateAfterMutation } from "@/lib/mutations";
import { qk } from "@/lib/query-keys";
import type { CanonicalStage } from "@/lib/stages";

import { mutationMessage, unwrapAction } from "./action-error";
import {
  applyStageChange,
  revertStageChange,
  type StageSnapshot,
} from "./application-model";
import type { ApplicationsBundle } from "./use-applications-query";

type MoveVariables = { applicationId: string; newStage: CanonicalStage };
type MoveContext = {
  applicationId: string;
  previous: StageSnapshot | null;
  optimisticEventId: string;
};

let optimisticCounter = 0;

/**
 * Moves an application to another stage. The board shows the new stage at once (`setQueryData`),
 * and the change is rolled back to the fields it read before the move if the server refuses it.
 * The hook also tracks which applications are saving, so their cards can show a spinner.
 */
export function useStageMove() {
  const queryClient = useQueryClient();
  const [pendingIds, setPendingIds] = useState<ReadonlySet<string>>(() => new Set());

  const mutation = useMutation<void, unknown, MoveVariables, MoveContext>({
    mutationKey: ["application-stage"],
    mutationFn: async ({ applicationId, newStage }) => {
      const result = await changeApplicationStage({ applicationId, newStage });
      unwrapAction(result);
    },
    onMutate: async ({ applicationId, newStage }) => {
      setPendingIds((current) => new Set(current).add(applicationId));
      await queryClient.cancelQueries({ queryKey: qk.applications });
      const before = queryClient.getQueryData<ApplicationsBundle>(qk.applications);
      const found = before?.applications.find((app) => app.id === applicationId);
      const previous: StageSnapshot | null = found
        ? { current_stage: found.current_stage, status: found.status, outcome: found.outcome }
        : null;
      optimisticCounter += 1;
      const optimisticEventId = `optimistic-${applicationId}-${optimisticCounter}`;
      queryClient.setQueryData<ApplicationsBundle>(qk.applications, (current) =>
        current
          ? applyStageChange(current, applicationId, newStage, optimisticEventId, new Date().toISOString())
          : current
      );
      return { applicationId, previous, optimisticEventId };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) {
        const { applicationId, previous, optimisticEventId } = context;
        queryClient.setQueryData<ApplicationsBundle>(qk.applications, (current) =>
          current ? revertStageChange(current, applicationId, previous, optimisticEventId) : current
        );
      }
      toast.error(mutationMessage(error));
    },
    onSettled: (_data, _error, variables) => {
      setPendingIds((current) => {
        const next = new Set(current);
        next.delete(variables.applicationId);
        return next;
      });
      void invalidateAfterMutation(queryClient, { applicationId: variables.applicationId });
    },
  });

  const { mutate } = mutation;
  const move = useCallback(
    (applicationId: string, newStage: CanonicalStage) => {
      mutate({ applicationId, newStage });
    },
    [mutate]
  );

  return { move, pendingIds };
}
