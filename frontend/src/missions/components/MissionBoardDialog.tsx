/**
 * MissionBoardDialog (#3044) — the classic notice-board front door on web.
 *
 * Boards are room objects with an active BOARD-kind MissionGiver bound to
 * them (#2044) — a plain examinable object, not a dedicated typeclass (see
 * `MissionGiver`'s docstring). `ObjectsList` opens this dialog when the room
 * payload flags an object `is_mission_board`. Lists the viewer's eligible
 * postings (name + summary — `BoardPostingSerializer` carries no party-size
 * field, so this only shows what the API actually returns) and takes one via
 * the existing `POST /api/missions/boards/<pk>/take/` endpoint. The take
 * itself is the entire "accept" step; the report-in loop (#3040) is a
 * separate, later affordance reached from the journal.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import { ApiValidationError, flattenErrorMessage } from '../api';
import { useBoardPostings, useTakeBoardPosting } from '../queries';

interface MissionBoardDialogProps {
  boardObjectId: number;
  boardName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MissionBoardDialog({
  boardObjectId,
  boardName,
  open,
  onOpenChange,
}: MissionBoardDialogProps) {
  const [takenInstanceId, setTakenInstanceId] = useState<number | null>(null);
  const postings = useBoardPostings(open ? boardObjectId : null);
  const take = useTakeBoardPosting(boardObjectId);

  const handleTake = (templateId: number) => {
    take.mutate(templateId, {
      onSuccess: (result) => {
        toast.success('Posting taken.');
        setTakenInstanceId(result.instance_id);
      },
      onError: (error: Error) => {
        toast.error(
          error instanceof ApiValidationError
            ? flattenErrorMessage(error.fieldErrors)
            : error.message
        );
      },
    });
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setTakenInstanceId(null);
        onOpenChange(next);
      }}
    >
      <DialogContent data-testid="mission-board-dialog">
        <DialogHeader>
          <DialogTitle>{boardName}</DialogTitle>
          <DialogDescription>Postings you&apos;re eligible to take.</DialogDescription>
        </DialogHeader>

        {postings.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading postings…</p>
        ) : postings.data && postings.data.results.length > 0 ? (
          <ul className="space-y-2" data-testid="board-postings-list">
            {postings.data.results.map((posting) => (
              <li
                key={posting.template_id}
                className="flex items-start justify-between gap-3 rounded-md border p-3"
              >
                <div>
                  <p className="text-sm font-medium">{posting.name}</p>
                  {posting.summary ? (
                    <p className="text-xs text-muted-foreground">{posting.summary}</p>
                  ) : null}
                </div>
                <Button
                  size="sm"
                  disabled={take.isPending}
                  onClick={() => handleTake(posting.template_id)}
                  data-testid={`take-posting-${posting.template_id}`}
                >
                  Take
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No postings for you right now.</p>
        )}

        {takenInstanceId != null ? (
          <p className="text-sm" data-testid="board-take-journal-link">
            Taken —{' '}
            <Link to="/missions/journal" className="underline">
              open your journal
            </Link>{' '}
            to begin.
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
