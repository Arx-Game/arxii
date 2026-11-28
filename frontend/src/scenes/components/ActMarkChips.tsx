/**
 * ActMarkChips (#5327): the chips a marked pose carries, one per resonance it marked,
 * "<Resonance> · <act label>". The room reads the chip and never the amount. Once staff or the
 * scene's GM undid the reward the chip is struck through and says who undid it. Staff and the
 * scene's GM (`can_undo`, never a scene co-owner) also get "Undo reward" on a mark not yet undone.
 *
 * Wire contract: `act_marks` on the feed row and on the live frame; undo is
 * `POST /api/magic/resonance-grants/<id>/undo/`.
 */

import { cn } from '@/lib/utils';
import { useUndoResonanceGrant } from '../queries';
import type { ActMark, Interaction } from '../types';

interface ActMarkChipsProps {
  interaction: Interaction;
  sceneId: string;
  /** False on a read-only line, which never offers Undo. */
  interactive?: boolean;
}

/** Who undid the reward, in the words the room reads. */
function undoneLine(mark: ActMark): string {
  if (mark.undone_by === 'staff') return 'Reward undone by staff';
  if (mark.undone_by === 'gm') return "Reward undone by the scene's GM";
  return 'Reward undone';
}

function UndoRewardButton({ mark, sceneId }: { mark: ActMark; sceneId: string }) {
  const undo = useUndoResonanceGrant(sceneId);
  return (
    <>
      <button
        type="button"
        disabled={undo.isPending}
        onClick={() => undo.mutate(mark.grant_id)}
        data-testid={`undo-reward-${mark.grant_id}`}
        className="self-start text-xs text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
      >
        Undo reward
      </button>
      {undo.error && (
        <span data-testid="undo-reward-error" className="text-xs text-destructive">
          {undo.error.message}
        </span>
      )}
    </>
  );
}

export function ActMarkChips({ interaction, sceneId, interactive = true }: ActMarkChipsProps) {
  const marks = interaction.act_marks ?? [];
  if (marks.length === 0) return null;

  return (
    <div className="mt-1 flex flex-col items-start gap-1" data-testid="act-mark-chips">
      {marks.map((mark) => (
        <div key={mark.grant_id} className="flex flex-wrap items-center gap-1.5">
          <span
            data-testid={`act-mark-${mark.grant_id}`}
            className={cn(
              'inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300',
              mark.undone && 'line-through opacity-70'
            )}
          >
            {mark.resonance_name} · {mark.act_label}
          </span>
          {mark.undone && (
            <span className="text-xs text-muted-foreground" data-testid="act-mark-undone">
              {undoneLine(mark)}
            </span>
          )}
          {interactive && mark.can_undo && !mark.undone && (
            <UndoRewardButton mark={mark} sceneId={sceneId} />
          )}
        </div>
      ))}
    </div>
  );
}
