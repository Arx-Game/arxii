/**
 * GroupBeatCard — the multiplayer group-decision beat (#1036/#2049).
 *
 * Mirrors BeatCard's shape (framing prose → options → result → continue) but
 * for GROUP_VOTE/JOINT nodes: shows the phase (pick/vote), who has spoken
 * (ballots with character_name), the expiry countdown, and my own options.
 * "Expired" is a client-derived state — the server resolves lazily on next
 * fetch, so when the countdown hits zero we show a "waiting" message and
 * let the next refetch (or the cron backstop) resolve it.
 */
import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import { ApiValidationError, flattenErrorMessage } from '../api';
import { useCastGroupVote, useGroupBeat, useSubmitGroupPick } from '../queries';
import type { GroupBeatView, ResolvedBeat } from '../types';
import { InvitePicker } from './InvitePicker';

interface GroupBeatCardProps {
  instanceId: number;
  /** Stable identifier of the player's current room (refetch key). */
  roomKey: string;
  /** Whether the viewer is the contract holder (shows the invite affordance). */
  isContractHolder?: boolean;
}

export function GroupBeatCard({
  instanceId,
  roomKey,
  isContractHolder = false,
}: GroupBeatCardProps) {
  const { data: result, isLoading } = useGroupBeat(instanceId, roomKey);
  const [resolved, setResolved] = useState<ResolvedBeat | null>(null);

  // If the server resolved the beat (or we captured a resolution), show it.
  const resolvedBeat = resolved ?? result?.resolved ?? null;
  if (resolvedBeat) {
    return <ResolvedView resolved={resolvedBeat} onContinue={() => setResolved(null)} />;
  }

  if (isLoading) {
    return <div className="p-3 text-sm text-muted-foreground">…</div>;
  }

  const beat = result?.group_beat ?? null;
  if (!beat) {
    return (
      <div className="p-3 text-sm text-muted-foreground" data-testid="group-beat-concluded">
        This story has concluded — see your journal for how it ended.
      </div>
    );
  }

  return (
    <GroupBeatView
      instanceId={instanceId}
      beat={beat}
      onResolved={setResolved}
      isContractHolder={isContractHolder}
    />
  );
}

function ResolvedView({
  resolved,
  onContinue,
}: {
  resolved: ResolvedBeat;
  onContinue: () => void;
}) {
  return (
    <div className="space-y-2 rounded border bg-card p-3" data-testid="group-beat-result">
      {resolved.outcome_name ? <Badge variant="outline">{resolved.outcome_name}</Badge> : null}
      <p className="whitespace-pre-wrap text-sm">{resolved.story_text}</p>
      {resolved.is_terminal ? (
        <p className="whitespace-pre-wrap text-sm italic text-muted-foreground">
          {resolved.epilogue || 'The story concludes.'}
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={onContinue}>
          Continue
        </Button>
      </div>
    </div>
  );
}

function GroupBeatView({
  instanceId,
  beat,
  onResolved,
  isContractHolder,
}: {
  instanceId: number;
  beat: GroupBeatView;
  onResolved: (beat: ResolvedBeat) => void;
  isContractHolder: boolean;
}) {
  const submitPick = useSubmitGroupPick();
  const castVote = useCastGroupVote();
  const { expired, secondsLeft } = useCountdown(beat.expires_at);

  const phaseLabel = expired ? 'expired' : beat.phase === 'vote' ? 'voting' : 'picking';

  return (
    <div className="space-y-2 rounded border bg-card p-3" data-testid="group-beat-card">
      <div className="flex items-center justify-between gap-2">
        <Badge variant="secondary" data-testid="group-beat-phase">
          {phaseLabel}
        </Badge>
        {!expired && beat.expires_at ? (
          <span className="text-xs text-muted-foreground" data-testid="group-beat-countdown">
            {formatCountdown(secondsLeft)}
          </span>
        ) : null}
      </div>

      {beat.flavor_text ? <p className="whitespace-pre-wrap text-sm">{beat.flavor_text}</p> : null}

      <ParticipantRow beat={beat} />

      {beat.options.length === 0 ? (
        <p className="text-xs text-muted-foreground" data-testid="group-beat-not-here">
          Nothing presents itself here — this story waits somewhere else.
        </p>
      ) : (
        <div className="space-y-1" data-testid="group-beat-options">
          {beat.options.map((option) => (
            <GroupOptionButton
              key={`${option.option_id}-${option.approach_id ?? 'authored'}`}
              option={option}
              phase={beat.phase}
              pickPending={submitPick.isPending}
              votePending={castVote.isPending}
              onPick={() =>
                submitPick.mutate(
                  { instanceId, option_id: option.option_id, approach_id: option.approach_id },
                  { onSuccess: (data) => data.resolved && onResolved(data.resolved) }
                )
              }
              onVote={() =>
                castVote.mutate(
                  { instanceId, option_id: option.option_id },
                  { onSuccess: (data) => data.resolved && onResolved(data.resolved) }
                )
              }
            />
          ))}
        </div>
      )}

      {submitPick.error ? (
        <p className="text-xs text-destructive" data-testid="group-beat-error">
          {submitPick.error instanceof ApiValidationError
            ? flattenErrorMessage(submitPick.error.fieldErrors)
            : submitPick.error.message}
        </p>
      ) : null}
      {castVote.error ? (
        <p className="text-xs text-destructive" data-testid="group-beat-error">
          {castVote.error instanceof ApiValidationError
            ? flattenErrorMessage(castVote.error.fieldErrors)
            : castVote.error.message}
        </p>
      ) : null}

      {expired ? (
        <p className="text-xs text-muted-foreground" data-testid="group-beat-expired">
          The window closed — waiting for the server to resolve.
        </p>
      ) : null}

      {isContractHolder ? <InvitePicker instanceId={instanceId} /> : null}
    </div>
  );
}

function GroupOptionButton({
  option,
  phase,
  pickPending,
  votePending,
  onPick,
  onVote,
}: {
  option: GroupBeatView['options'][number];
  phase: string;
  pickPending: boolean;
  votePending: boolean;
  onPick: () => void;
  onVote: () => void;
}) {
  const pending = phase === 'vote' ? votePending : pickPending;
  return (
    <Button
      size="sm"
      variant="outline"
      className="h-auto w-full justify-between whitespace-normal py-1.5 text-left"
      disabled={pending}
      onClick={phase === 'vote' ? onVote : onPick}
      data-testid={`group-option-${option.option_id}`}
    >
      <span>{option.label}</span>
      {option.check_type_name ? (
        <span className="ml-2 shrink-0 text-xs text-muted-foreground">
          {option.check_type_name}
          {option.base_risk > 0 ? ` · risk ${option.base_risk}` : ''}
        </span>
      ) : null}
    </Button>
  );
}

function ParticipantRow({ beat }: { beat: GroupBeatView }) {
  return (
    <div className="flex flex-wrap gap-2" data-testid="group-beat-participants">
      {beat.ballots.map((ballot) => {
        const hasSpoken =
          beat.phase === 'vote'
            ? ballot.voted_option_id !== null
            : ballot.picked_option_id !== null;
        return (
          <span
            key={ballot.character_id}
            className={`text-xs ${hasSpoken ? 'text-muted-foreground' : 'font-medium text-foreground'}`}
          >
            {ballot.character_name}
            {hasSpoken ? ' ✓' : ' …'}
          </span>
        );
      })}
    </div>
  );
}

/**
 * Countdown hook — ticks every second from the ISO deadline.
 * Returns { expired: true } when the deadline has passed.
 */
function useCountdown(expiresAt: string | null): { expired: boolean; secondsLeft: number } {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!expiresAt) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [expiresAt]);

  if (!expiresAt) return { expired: false, secondsLeft: 0 };

  const deadline = Date.parse(expiresAt);
  if (Number.isNaN(deadline)) return { expired: false, secondsLeft: 0 };

  const secondsLeft = Math.max(0, Math.floor((deadline - now) / 1000));
  return { expired: secondsLeft <= 0, secondsLeft };
}

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}
