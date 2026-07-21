import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ShieldAlert, Check, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  fetchPendingRequests,
  fetchPendingTargets,
  respondToRequest,
  toastDispositionMessage,
} from '../actionQueries';
import type {
  ActionRequest,
  BoonReadPayload,
  PendingActionTarget,
  StakesSummary,
} from '../actionTypes';

interface Props {
  sceneId: string;
}

/**
 * Plausibility bands — the defender declares how plausible the effect is on
 * their character.  Maps to valid DifficultyChoice values on the backend.
 * A neutral "Accept" (normal) is rendered separately as a plain button.
 */
const PLAUSIBILITY_BANDS = [
  { label: 'It works', value: 'easy', icon: Check },
  { label: 'Hard but possible', value: 'hard', icon: Check },
  { label: 'No way', value: 'daunting', icon: ShieldAlert },
] as const;

const RESIST_EFFORT_OPTIONS = [
  { label: 'Low effort', value: 'low' },
  { label: 'Medium effort', value: 'medium' },
  { label: 'High effort', value: 'high' },
  { label: 'Extreme effort', value: 'extreme' },
] as const;

interface ConsentCardProps {
  cardKey: string;
  initiatorName: string;
  actionKey: string;
  techniqueName?: string | null;
  strainCommitment: number;
  combatRiskLevel?: string | null;
  combatStakes?: StakesSummary[] | null;
  /** The structured ask on a boon request (#2540) — what granting costs you. */
  boon?: BoonReadPayload | null;
  resistEffort: string;
  onResistChange: (v: string) => void;
  onDeny: () => void;
  onDenyBlock: () => void;
  onAccept: (difficulty: string) => void;
  isPending: boolean;
}

function ConsentCard({
  initiatorName,
  actionKey,
  techniqueName,
  strainCommitment,
  combatRiskLevel,
  combatStakes,
  boon,
  resistEffort,
  onResistChange,
  onDeny,
  onDenyBlock,
  onAccept,
  isPending,
}: ConsentCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-amber-500/50 bg-amber-50 px-4 py-3 dark:bg-amber-950/30">
      <ShieldAlert className="h-5 w-5 shrink-0 text-amber-600" />
      <div className="flex-1">
        <p className="text-sm font-medium">
          <span className="font-semibold">{initiatorName}</span> wants to use{' '}
          <span className="font-semibold">
            {actionKey}
            {techniqueName ? ` (${techniqueName})` : ''}
          </span>{' '}
          on your character.
        </p>
        {boon && (
          <p className="mt-1 text-xs font-semibold text-amber-700 dark:text-amber-300">
            {boon.kind === 'money' &&
              `They ask for ${boon.sum_tier ? `a ${boon.sum_tier} sum — ` : ''}${boon.amount} coppers.`}
            {boon.kind === 'deed' && `They ask a deed of you: "${boon.deed_text}"`}
            {(boon.kind === 'held_item' || boon.kind === 'vault_item') &&
              `They ask for ${boon.item_name ?? 'an item'}${boon.kind === 'vault_item' ? ' from your vault' : ''}.`}
          </p>
        )}
        {strainCommitment > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            {initiatorName} is committing {strainCommitment} strain.
          </p>
        )}
        {combatRiskLevel && (
          <p className="mt-1 text-xs font-semibold text-red-600 dark:text-red-400">
            The fight before you is {combatRiskLevel.toUpperCase()} risk — accepting wades your
            character into the combat encounter.
          </p>
        )}
        {combatStakes && combatStakes.length > 0 && (
          <div className="mt-1 space-y-1">
            {combatStakes.map((summary) => (
              <div
                key={summary.stakes.map((stake) => stake.id).join('-')}
                className="text-xs text-red-700 dark:text-red-300"
              >
                <p className="font-semibold">
                  Stakes on the table (effective risk {summary.effective_risk.toUpperCase()}):
                </p>
                <ul className="ml-4 list-disc">
                  {summary.stakes.map((stake) => (
                    <li key={stake.id}>
                      <span className="font-medium">{stake.severity_label}:</span>{' '}
                      {stake.player_summary}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        <Select value={resistEffort} onValueChange={onResistChange}>
          <SelectTrigger className="h-8 w-[160px] text-xs" aria-label="Dig in (costs stamina)">
            <SelectValue placeholder="Dig in (costs stamina)" />
          </SelectTrigger>
          <SelectContent>
            {RESIST_EFFORT_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" onClick={onDeny} disabled={isPending}>
          <X className="mr-1 h-3.5 w-3.5" />
          Deny
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onDenyBlock}
          disabled={isPending}
          title="Deny and bar this person from this kind of action toward you"
        >
          <ShieldAlert className="mr-1 h-3.5 w-3.5" />
          Deny &amp; block
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={() => onAccept('normal')}
          disabled={isPending}
        >
          <Check className="mr-1 h-3.5 w-3.5" />
          Accept
        </Button>
        {PLAUSIBILITY_BANDS.map((opt) => {
          const Icon = opt.icon;
          return (
            <Button
              key={opt.value}
              size="sm"
              variant="secondary"
              onClick={() => onAccept(opt.value)}
              disabled={isPending}
            >
              <Icon className="mr-1 h-3.5 w-3.5" />
              {opt.label}
            </Button>
          );
        })}
      </div>
    </div>
  );
}

export function ConsentPrompt({ sceneId }: Props) {
  const queryClient = useQueryClient();

  // Per-card resist effort state, keyed by a string ID.
  // Primary requests: key = `req-${id}`, targets: key = `target-${action_target_id}`
  const [resistEffort, setResistEffort] = useState<Record<string, string>>({});

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
      resist_effort,
      blacklist_actor,
    }: {
      requestId: number;
      accept: boolean;
      difficulty?: string;
      resist_effort?: string;
      blacklist_actor?: boolean;
    }) =>
      respondToRequest(sceneId, requestId, { accept, difficulty, resist_effort, blacklist_actor }),
    onSuccess: (data) => {
      toastDispositionMessage(data);
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
      // 2026-07 audit: 'scene-messages' matched no query anywhere — the feed's
      // real key is 'scene-interactions' (useSceneInteractions).
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] });
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
      resist_effort,
      blacklist_actor,
    }: {
      requestId: number;
      targetPersonaId: number;
      accept: boolean;
      difficulty?: string;
      resist_effort?: string;
      blacklist_actor?: boolean;
    }) =>
      respondToRequest(sceneId, requestId, {
        accept,
        difficulty,
        resist_effort,
        blacklist_actor,
        target_persona_id: targetPersonaId,
      }),
    onSuccess: (data) => {
      toastDispositionMessage(data);
      queryClient.invalidateQueries({ queryKey: ['pending-targets', sceneId] });
      // 2026-07 audit: 'scene-messages' matched no query anywhere — the feed's
      // real key is 'scene-interactions' (useSceneInteractions).
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] });
    },
  });

  const requests = data?.results ?? [];
  const targets = targetData?.results ?? [];

  if (requests.length === 0 && targets.length === 0) return null;

  return (
    <div className="space-y-2">
      {requests.map((req: ActionRequest) => {
        const cardKey = `req-${req.id}`;
        const selectedResist = resistEffort[cardKey] ?? '';
        return (
          <ConsentCard
            key={req.id}
            cardKey={cardKey}
            initiatorName={req.initiator_name}
            actionKey={req.action_key}
            techniqueName={req.technique_name}
            strainCommitment={req.strain_commitment}
            combatRiskLevel={req.combat_risk_level}
            combatStakes={req.combat_stakes}
            boon={req.boon}
            resistEffort={selectedResist}
            onResistChange={(val) => setResistEffort((prev) => ({ ...prev, [cardKey]: val }))}
            onDeny={() => respond.mutate({ requestId: req.id, accept: false })}
            onDenyBlock={() =>
              respond.mutate({ requestId: req.id, accept: false, blacklist_actor: true })
            }
            onAccept={(difficulty) =>
              respond.mutate({
                requestId: req.id,
                accept: true,
                difficulty,
                resist_effort: selectedResist !== '' ? selectedResist : undefined,
              })
            }
            isPending={respond.isPending}
          />
        );
      })}
      {targets.map((t: PendingActionTarget) => {
        const cardKey = `target-${t.action_target_id}`;
        const selectedResist = resistEffort[cardKey] ?? '';
        return (
          <ConsentCard
            key={`target-${t.action_target_id}`}
            cardKey={cardKey}
            initiatorName={t.initiator_name}
            actionKey={t.action_key}
            techniqueName={t.technique_name}
            strainCommitment={t.strain_commitment}
            combatRiskLevel={t.combat_risk_level}
            combatStakes={t.combat_stakes}
            resistEffort={selectedResist}
            onResistChange={(val) => setResistEffort((prev) => ({ ...prev, [cardKey]: val }))}
            onDeny={() =>
              respondTarget.mutate({
                requestId: t.action_request_id,
                targetPersonaId: t.target_persona_id,
                accept: false,
              })
            }
            onDenyBlock={() =>
              respondTarget.mutate({
                requestId: t.action_request_id,
                targetPersonaId: t.target_persona_id,
                accept: false,
                blacklist_actor: true,
              })
            }
            onAccept={(difficulty) =>
              respondTarget.mutate({
                requestId: t.action_request_id,
                targetPersonaId: t.target_persona_id,
                accept: true,
                difficulty,
                resist_effort: selectedResist !== '' ? selectedResist : undefined,
              })
            }
            isPending={respondTarget.isPending}
          />
        );
      })}
    </div>
  );
}
