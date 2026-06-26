import { useMemo, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { HeartPulse } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { extractErrorMessage } from '@/lib/errors';
import { useTreatmentCandidates } from '../queries';
import { createActionRequest, TREAT_CONDITION_ACTION_KEY } from '@/scenes/actionQueries';
import type { TreatmentCandidate } from '../api';

interface Props {
  sceneId: string;
  targetPersonaId: number | null;
}

/**
 * Panel listing treatments a helper may offer a target persona (#1486).
 *
 * Fetches candidate (treatment, target_effect) pairs from the treatments
 * discovery endpoint and POSTs an offer via the shared `createActionRequest`
 * path — the same seam ActionPanel uses for every action-request, not a
 * parallel `attemptTreatment`.  The backend creates a pending consent request;
 * the target responds separately.
 *
 * The panel resolves the helper's character ObjectDB pk (for the discovery
 * endpoint's X-Character-ID header) and primary persona id (for the request
 * body) internally from the active roster entry — mirroring how ActionPanel and
 * PersonaContextMenu resolve these, so the parent only supplies the scene id
 * and target persona id.
 */
export function TreatActionPanel({ sceneId, targetPersonaId }: Props) {
  const queryClient = useQueryClient();
  const [offeredRequestId, setOfferedRequestId] = useState<number | null>(null);

  // Resolve the helper's character ObjectDB pk + primary persona from the
  // active roster entry — the same resolution ActionPanel and PersonaContextMenu
  // perform.  characterId backs the X-Character-ID header on the discovery
  // fetch; initiatorPersonaId goes on the action-request body.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName) ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const characterId = activeEntry?.character_id ?? null;
  const initiatorPersonaId = activeEntry?.primary_persona_id ?? null;

  const { data, isLoading } = useTreatmentCandidates(targetPersonaId, characterId);
  const candidates = data?.candidates ?? [];

  const offerTreatment = useMutation({
    mutationFn: (candidate: TreatmentCandidate) => {
      // Mutually exclusive: only the id matching the target effect type is set,
      // so the other key is genuinely absent (mirrors ActionPanel's commitAction
      // conditional-spread pattern — tests assert not.toHaveProperty).
      const targetEffectIdField =
        candidate.target_effect_type === 'condition'
          ? { target_condition_instance_id: candidate.target_effect.id }
          : { target_pending_alteration_id: candidate.target_effect.id };
      return createActionRequest(sceneId, {
        action_key: TREAT_CONDITION_ACTION_KEY,
        initiator_persona: initiatorPersonaId ?? undefined,
        target_persona_id: targetPersonaId ?? undefined,
        treatment_id: candidate.treatment.id,
        ...targetEffectIdField,
        // The backend ignores the client-supplied thread id and uses the matched
        // candidate's thread, but we send it to mirror the candidate. Harmless.
        ...(candidate.bond_thread !== null ? { bond_thread_id: candidate.bond_thread } : {}),
      });
    },
    onSuccess: (response) => {
      setOfferedRequestId(response.request_id ?? null);
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
    },
  });

  // No target selected — muted prompt rather than a fetch.
  if (targetPersonaId === null) {
    return <p className="text-xs text-muted-foreground">Select a target to offer treatment.</p>;
  }

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  if (candidates.length === 0) {
    return <p className="text-sm text-muted-foreground">No treatable conditions.</p>;
  }

  return (
    <div className="space-y-2">
      {candidates.map((candidate) => {
        const treatmentName = candidate.treatment.name;
        const effectName = candidate.target_effect.name ?? candidate.target_effect.character_name;
        return (
          <div
            key={`${candidate.treatment.id}-${candidate.target_effect_type}-${candidate.target_effect.id}`}
            className="flex items-center justify-between gap-2 rounded border border-muted px-2 py-1.5"
          >
            <div className="min-w-0">
              <p className="truncate text-xs font-medium">
                <HeartPulse className="mr-1 inline h-3 w-3" />
                {treatmentName}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                on {effectName ?? 'target'}
                {candidate.bond_thread !== null && (
                  <span className="ml-1 italic">(requires bond thread)</span>
                )}
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={offerTreatment.isPending}
              onClick={() => offerTreatment.mutate(candidate)}
            >
              {offerTreatment.isPending &&
              offerTreatment.variables?.treatment.id === candidate.treatment.id
                ? 'Offering…'
                : 'Offer'}
            </Button>
          </div>
        );
      })}

      {offeredRequestId !== null && offerTreatment.isSuccess && (
        <p className="text-xs text-muted-foreground" data-testid="treat-offer-confirmation">
          Offered — awaiting response (request #{offeredRequestId})
        </p>
      )}

      {offerTreatment.isError && (
        <p className="mt-1 text-xs text-destructive" role="alert">
          {extractErrorMessage(offerTreatment.error)}
        </p>
      )}
    </div>
  );
}
