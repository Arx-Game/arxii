import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ShieldAlert, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchPendingRequests, fetchPendingTargets, respondToRequest } from '../actionQueries';
import type { ActionRequest, PendingActionTarget } from '../actionTypes';

interface Props {
  sceneId: string;
}

/**
 * Plausibility bands — the defender declares how plausible the effect is on
 * their character.  Maps to valid DifficultyChoice values on the backend.
 * A neutral "Accept" (normal) is rendered separately as a plain button.
 */
const PLAUSIBILITY_BANDS = [
  { label: 'It works', value: 'easy' },
  { label: 'Hard but possible', value: 'hard' },
  { label: 'No way', value: 'daunting' },
] as const;

export function ConsentPrompt({ sceneId }: Props) {
  const queryClient = useQueryClient();

  const { data } = useQuery({
    queryKey: ['pending-requests', sceneId],
    queryFn: () => fetchPendingRequests(sceneId),
    refetchInterval: 5_000,
  });

  const respond = useMutation({
    mutationFn: ({
      requestId,
      accept,
      difficulty,
    }: {
      requestId: number;
      accept: boolean;
      difficulty?: string;
    }) => respondToRequest(sceneId, requestId, { accept, difficulty }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
    },
  });

  const { data: targetData } = useQuery({
    queryKey: ['pending-targets', sceneId],
    queryFn: () => fetchPendingTargets(sceneId),
    refetchInterval: 5_000,
  });

  const respondTarget = useMutation({
    mutationFn: ({
      requestId,
      targetPersonaId,
      accept,
      difficulty,
    }: {
      requestId: number;
      targetPersonaId: number;
      accept: boolean;
      difficulty?: string;
    }) =>
      respondToRequest(sceneId, requestId, {
        accept,
        difficulty,
        target_persona_id: targetPersonaId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-targets', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
    },
  });

  const requests = data?.results ?? [];
  const targets = targetData?.results ?? [];

  if (requests.length === 0 && targets.length === 0) return null;

  return (
    <div className="space-y-2">
      {requests.map((req: ActionRequest) => (
        <div
          key={req.id}
          className="flex items-center gap-3 rounded-md border border-amber-500/50 bg-amber-50 px-4 py-3 dark:bg-amber-950/30"
        >
          <ShieldAlert className="h-5 w-5 shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="text-sm font-medium">
              <span className="font-semibold">{req.initiator_name}</span> wants to use{' '}
              <span className="font-semibold">
                {req.action_key}
                {req.technique_name ? ` (${req.technique_name})` : ''}
              </span>{' '}
              on your character.
            </p>
            {req.strain_commitment > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                {req.initiator_name} is committing {req.strain_commitment} strain.
              </p>
            )}
            {req.combat_risk_level && (
              <p className="mt-1 text-xs font-semibold text-red-600 dark:text-red-400">
                The fight before you is {req.combat_risk_level.toUpperCase()} risk — accepting wades
                your character into the combat encounter.
              </p>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              onClick={() => respond.mutate({ requestId: req.id, accept: false })}
              disabled={respond.isPending}
            >
              <X className="mr-1 h-3.5 w-3.5" />
              Deny
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                respond.mutate({ requestId: req.id, accept: true, difficulty: 'normal' })
              }
              disabled={respond.isPending}
            >
              <Check className="mr-1 h-3.5 w-3.5" />
              Accept
            </Button>
            {PLAUSIBILITY_BANDS.map((opt) => (
              <Button
                key={opt.value}
                size="sm"
                variant="secondary"
                onClick={() =>
                  respond.mutate({
                    requestId: req.id,
                    accept: true,
                    difficulty: opt.value,
                  })
                }
                disabled={respond.isPending}
              >
                <Check className="mr-1 h-3.5 w-3.5" />
                {opt.label}
              </Button>
            ))}
          </div>
        </div>
      ))}
      {targets.map((t: PendingActionTarget) => (
        <div
          key={`target-${t.action_target_id}`}
          className="flex items-center gap-3 rounded-md border border-amber-500/50 bg-amber-50 px-4 py-3 dark:bg-amber-950/30"
        >
          <ShieldAlert className="h-5 w-5 shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="text-sm font-medium">
              <span className="font-semibold">{t.initiator_name}</span> wants to use{' '}
              <span className="font-semibold">
                {t.action_key}
                {t.technique_name ? ` (${t.technique_name})` : ''}
              </span>{' '}
              on your character.
            </p>
            {t.strain_commitment > 0 && (
              <p className="mt-1 text-xs text-muted-foreground">
                {t.initiator_name} is committing {t.strain_commitment} strain.
              </p>
            )}
            {t.combat_risk_level && (
              <p className="mt-1 text-xs font-semibold text-red-600 dark:text-red-400">
                The fight before you is {t.combat_risk_level.toUpperCase()} risk — accepting wades
                your character into the combat encounter.
              </p>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                respondTarget.mutate({
                  requestId: t.action_request_id,
                  targetPersonaId: t.target_persona_id,
                  accept: false,
                })
              }
              disabled={respondTarget.isPending}
            >
              <X className="mr-1 h-3.5 w-3.5" />
              Deny
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                respondTarget.mutate({
                  requestId: t.action_request_id,
                  targetPersonaId: t.target_persona_id,
                  accept: true,
                  difficulty: 'normal',
                })
              }
              disabled={respondTarget.isPending}
            >
              <Check className="mr-1 h-3.5 w-3.5" />
              Accept
            </Button>
            {PLAUSIBILITY_BANDS.map((opt) => (
              <Button
                key={opt.value}
                size="sm"
                variant="secondary"
                onClick={() =>
                  respondTarget.mutate({
                    requestId: t.action_request_id,
                    targetPersonaId: t.target_persona_id,
                    accept: true,
                    difficulty: opt.value,
                  })
                }
                disabled={respondTarget.isPending}
              >
                <Check className="mr-1 h-3.5 w-3.5" />
                {opt.label}
              </Button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
