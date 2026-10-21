/**
 * KeepsakeSection - the item panel's "Keep as a keepsake" row (#4530).
 *
 * Shows the trophy chip for an item won on a deed, what the item already stands for (and when
 * it starts to count), and the way to keep it or let it go. The form itself is the dialog.
 * Nothing here says what a keepsake is worth: the player's words are theirs and are never
 * scored, and the points come from the subject.
 */

import { useState } from 'react';
import { Heart } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useKeepsakeState, useReleaseKeepsake } from '../hooks/useKeepsake';
import type { ItemInstance } from '../types';
import { KeepsakeDialog } from './KeepsakeDialog';

interface KeepsakeSectionProps {
  item: ItemInstance;
  /** The character holding the item; the actions dispatch as them. */
  characterId: number;
}

function countsText(countsNow: boolean, waitDays: number, createdAt: string): string {
  if (countsNow) return 'It counts now.';
  const start = new Date(createdAt).getTime() + waitDays * 24 * 60 * 60 * 1000;
  return `It starts to count on ${new Date(start).toLocaleDateString()}.`;
}

export function KeepsakeSection({ item, characterId }: KeepsakeSectionProps) {
  const [open, setOpen] = useState(false);
  const { data } = useKeepsakeState(item.id);
  const release = useReleaseKeepsake(characterId);

  if (!data) return null;
  const { keepsake, trophy_of: trophyOf, status } = data;

  function handleRelease() {
    release.mutate(item.id, {
      onSuccess: (result) => {
        if (result.success === false) {
          toast.error(result.message);
          return;
        }
        toast.success(result.message);
      },
      onError: (error: Error) => toast.error(error.message),
    });
  }

  return (
    <div className="flex flex-col gap-2" data-testid="keepsake-section">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Keepsake
      </h4>
      {trophyOf.length > 0 && (
        <div className="flex flex-wrap gap-1.5" data-testid="trophy-chips">
          {trophyOf.map((title) => (
            <Badge key={title} variant="secondary">
              Trophy of {title}
            </Badge>
          ))}
        </div>
      )}
      {keepsake ? (
        <div className="space-y-1.5 text-sm" data-testid="keepsake-current">
          <p>
            Kept as a keepsake of <b>{keepsake.subject_name}</b>.{' '}
            <span className="text-muted-foreground">
              {countsText(data.counts_now, status.wait_days, keepsake.created_at)}
            </span>
          </p>
          <p className="whitespace-pre-wrap text-muted-foreground">{keepsake.text}</p>
          <p className="text-xs text-muted-foreground">
            {keepsake.shown_on_examine
              ? 'Your words show when someone examines it.'
              : 'Your words are private; only the game masters see them.'}
          </p>
          <Button
            size="sm"
            variant="outline"
            onClick={handleRelease}
            disabled={release.isPending}
            data-testid="keepsake-release"
          >
            Release keepsake
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setOpen(true)}
            disabled={status.used >= status.limit}
            data-testid="keepsake-open"
          >
            <Heart className="mr-1.5 h-3.5 w-3.5" />
            Keep as a keepsake
          </Button>
          <span className="text-xs text-muted-foreground">
            Keepsakes: {status.used} of {status.limit} used.
          </span>
        </div>
      )}
      <KeepsakeDialog
        open={open}
        onOpenChange={setOpen}
        item={item}
        characterId={characterId}
        state={data}
      />
    </div>
  );
}
