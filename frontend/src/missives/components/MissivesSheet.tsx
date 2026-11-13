/**
 * The missives drawer (#3289), opened from the top bar's letter button. Lists the
 * character's letters for this tab's roster entry and opens the compose dialog for a
 * new letter or a reply.
 */
import { useState } from 'react';
import { Mail } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { NO_DESCRIPTION } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AttentionBadge } from '@/game/components/AttentionBadge';
import { useMissiveUnreadCount, useMissivesQuery } from '../queries';
import type { Missive } from '../types';
import { MissiveList } from './MissiveList';
import { MissiveComposeDialog } from './MissiveComposeDialog';

interface MissivesSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** This tab's RosterEntry id (the API's `?entry_id=`). */
  entryId: number;
  /** The acting character (dispatch target). */
  characterId: number;
  activePersonaId: number | null;
}

export function MissivesSheet({
  open,
  onOpenChange,
  entryId,
  characterId,
  activePersonaId,
}: MissivesSheetProps) {
  const [page, setPage] = useState(1);
  const { data } = useMissivesQuery(entryId, page, open);
  const [composing, setComposing] = useState(false);
  const [replyTo, setReplyTo] = useState<Missive | null>(null);

  const closeCompose = () => {
    setComposing(false);
    setReplyTo(null);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent {...NO_DESCRIPTION} side="right" className="w-full overflow-y-auto sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Missives</SheetTitle>
        </SheetHeader>
        <div className="mt-4 space-y-4">
          <Button type="button" size="sm" onClick={() => setComposing(true)}>
            New missive
          </Button>
          {data && (
            <MissiveList
              missives={data.results}
              characterId={characterId}
              onReply={(missive) => {
                setReplyTo(missive);
                setComposing(true);
              }}
            />
          )}
          {data && (data.previous || data.next) && (
            <div className="flex justify-between">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={!data.previous}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Newer
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={!data.next}
                onClick={() => setPage((p) => p + 1)}
              >
                Older
              </Button>
            </div>
          )}
        </div>
        <MissiveComposeDialog
          open={composing}
          onClose={closeCompose}
          characterId={characterId}
          activePersonaId={activePersonaId}
          replyTo={replyTo}
        />
      </SheetContent>
    </Sheet>
  );
}

interface MissivesButtonProps {
  entryId: number;
  characterId: number;
  activePersonaId: number | null;
}

/** Top-bar letter button with the unread count; opens {@link MissivesSheet}. */
export function MissivesButton({ entryId, characterId, activePersonaId }: MissivesButtonProps) {
  const [open, setOpen] = useState(false);
  const unread = useMissiveUnreadCount(entryId);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="relative inline-flex min-h-8 min-w-8 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground"
        title="Missives"
        aria-label={unread > 0 ? `Missives, ${unread} unread` : 'Missives'}
      >
        <Mail className="h-4 w-4" />
        <AttentionBadge direct={unread} ambient={false} />
      </button>
      <MissivesSheet
        open={open}
        onOpenChange={setOpen}
        entryId={entryId}
        characterId={characterId}
        activePersonaId={activePersonaId}
      />
    </>
  );
}
