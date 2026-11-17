/**
 * ClaimRow (#5181): the optional "Claim" row of a pose and of a journal entry. A kindled deed
 * sets some resonance aside; switching Claim on collects it with the writing. Each resonance
 * with something waiting has a tick, all ticked to begin with, and an unticked one is left for
 * later. Renders nothing while nothing is waiting.
 *
 * Wire contract: `unclaimed` on GET /api/magic/kindled-resonances/ (KindledResonanceViewSet);
 * the request fields come from `claimFields` in `claiming.ts`.
 */

import { cn } from '@/lib/utils';
import { toggleClaim, toggleClaimResonance, type ClaimDraft } from '@/magic/claiming';
import { useWaitingClaims } from '@/magic/queries';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the writer; null while unknown. */
  characterSheetId: number | null;
  value: ClaimDraft;
  onChange: (value: ClaimDraft) => void;
  className?: string;
}

export function ClaimRow({ characterSheetId, value, onChange, className }: Props) {
  const waiting = useWaitingClaims(characterSheetId);
  if (waiting.length === 0) return null;

  return (
    <div
      className={cn('space-y-2 rounded border border-border px-3 py-2', className)}
      data-testid="claim-row"
    >
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-pressed={value.on}
          onClick={() => onChange(toggleClaim(value))}
          data-testid="claim-toggle"
          className={cn(
            'min-h-8 cursor-pointer rounded-full border px-3 py-1 text-xs',
            value.on
              ? 'border-foreground bg-foreground text-background'
              : 'border-border bg-transparent text-foreground hover:bg-accent'
          )}
        >
          Claim
        </button>
        {value.on &&
          waiting.map((row) => (
            <label key={row.id} className="flex cursor-pointer items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                checked={!value.left.includes(row.id)}
                onChange={() => onChange(toggleClaimResonance(value, row.id))}
                data-testid={`claim-resonance-${row.id}`}
              />
              {row.unclaimed} {row.name}
            </label>
          ))}
      </div>
    </div>
  );
}
