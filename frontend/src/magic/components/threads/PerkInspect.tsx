/**
 * PerkInspect (#5123, Screen 2 of the approved demo): what one resonance's perks on a
 * pulled thread are made of.
 *
 * Opened from "Inspect perks" on a payer. For each perk it names the amount (the authored
 * value times the level multiplier), where it comes from (the resonance's pull perk for this
 * kind of thread, at this tier), and the thread level the perk was read at. The leading
 * resonance reads the thread's full level; any other reads lower, and a held resonance the
 * thread never took in pays an ordinary pull with no perks.
 */
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { effectLabel, effectValue, levelReadLine, perkWords } from '../../burn';
import type { PayerOption, Thread } from '../../types';

interface PerkInspectProps {
  thread: Thread;
  option: PayerOption;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PerkInspect({ thread, option, open, onOpenChange }: PerkInspectProps) {
  const threadName = thread.name.trim() || `Thread #${thread.id}`;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent {...NO_DESCRIPTION} className="max-w-md" data-testid="perk-inspect">
        <DialogHeader>
          <DialogTitle>
            {option.resonance_name} through {threadName}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          {option.effects.length === 0 ? (
            <p data-testid="perk-inspect-none">No perks on this thread.</p>
          ) : (
            option.effects.map((effect, index) => (
              <section key={`${effect.kind}-${index}`} data-testid={`perk-inspect-${index}`}>
                <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {effectLabel(effect)}
                </h4>
                <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
                  <dt className="text-muted-foreground">Amount</dt>
                  <dd className="tabular-nums">{effectValue(effect) || 'none'}</dd>
                  {effect.authored_value !== null && (
                    <>
                      <dt className="text-muted-foreground">Worked out</dt>
                      <dd className="tabular-nums">
                        {effect.authored_value} x {effect.level_multiplier}
                      </dd>
                    </>
                  )}
                  <dt className="text-muted-foreground">From</dt>
                  <dd>
                    {option.resonance_name} pull perk for {perkWords(thread.target_kind)} threads,
                    tier {effect.source_tier}
                  </dd>
                  <dt className="text-muted-foreground">Thread level used</dt>
                  <dd>{levelReadLine(thread, option)}</dd>
                </dl>
                {effect.inactive && effect.inactive_reason && (
                  <p className="mt-1 text-muted-foreground">{effect.inactive_reason}</p>
                )}
                {effect.narrative_snippet && (
                  <p className="mt-1 italic text-muted-foreground">{effect.narrative_snippet}</p>
                )}
              </section>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
