import type { EncounterDetail } from '../types';

export interface CommitmentPanelProps {
  encounter: EncounterDetail;
}

/** Observable commitment, reaction, and ally-protection state for coordination. */
export function CommitmentPanel({ encounter }: CommitmentPanelProps) {
  const commitments = encounter.sustained_actions ?? [];
  const protection = encounter.protection_commitments ?? [];
  const reactions = encounter.participants.filter((p) => p.reactions_remaining != null);
  if (commitments.length === 0 && protection.length === 0 && reactions.length === 0) return null;
  return (
    <section
      className="space-y-2 rounded-md border border-border bg-muted/20 p-3"
      data-testid="commitment-panel"
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Commitments & reactions
      </h3>
      {commitments.map((commitment) => (
        <p
          key={commitment.id}
          className="text-xs text-foreground"
          data-testid="sustained-commitment"
        >
          {commitment.participant_name} holds {commitment.subject};{' '}
          {commitment.rounds_until_resolution} round
          {commitment.rounds_until_resolution === 1 ? '' : 's'} remaining
          {commitment.downgrades > 0 ? ` (${commitment.downgrades} erosion)` : ''}.
        </p>
      ))}
      {protection.map((item, index) => (
        <p
          key={`${item.participant_id}-${item.maneuver}-${index}`}
          className="text-xs text-foreground"
          data-testid="protection-commitment"
        >
          {item.participant_name} commits to {item.maneuver === 'cover' ? 'cover' : 'interpose for'}{' '}
          {item.protected_participant_name ?? 'an ally'}.
        </p>
      ))}
      {reactions.map((participant) => (
        <p
          key={participant.id}
          className="text-xs text-muted-foreground"
          data-testid="reaction-availability"
        >
          {participant.character_name}: {participant.reactions_remaining} reaction
          {participant.reactions_remaining === 1 ? '' : 's'} available
        </p>
      ))}
    </section>
  );
}
