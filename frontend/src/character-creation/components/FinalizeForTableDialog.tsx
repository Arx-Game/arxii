/**
 * FinalizeForTableDialog — a player-GM finalizes their own completed draft
 * directly onto the Available roster for a table they own (#3268).
 *
 * Non-staff sibling of the staff "Add to Roster" button in `ReviewStage`:
 * since `finalize-gm` also mints a `Story` tied to the target table, the GM
 * picks which of their active GM-role tables to attach it to and names the
 * story. On success, shows a panel naming the character and linking to the
 * specific table instead of immediately redirecting — the player-GM stays in
 * control of when the draft is cleared (see `useFinalizeDraftForTable`'s doc
 * comment and the unmount-cleanup effect below).
 */

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { bulletinErrorsFrom, type BulletinFieldErrors } from '@/tables/bulletinErrors';
import { FormErrors } from '@/tables/components/FieldError';
import type { GMTable } from '@/tables/types';
import type { FinalizeForTableResponse } from '../api';
import { characterCreationKeys, useFinalizeDraftForTable } from '../queries';

interface FinalizeForTableDialogProps {
  draftId: number;
  /** Active GM tables owned by the requesting account (`viewer_role === 'gm'`). */
  tables: GMTable[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function FinalizeForTableDialog({
  draftId,
  tables,
  open,
  onOpenChange,
}: FinalizeForTableDialogProps) {
  const queryClient = useQueryClient();
  const finalize = useFinalizeDraftForTable();

  const [tableId, setTableId] = useState('');
  const [storyTitle, setStoryTitle] = useState('');
  const [storyDescription, setStoryDescription] = useState('');
  const [fieldErrors, setFieldErrors] = useState<BulletinFieldErrors>({});
  const [result, setResult] = useState<FinalizeForTableResponse | null>(null);

  // Mirrors `result` for the unmount-cleanup effect below, which needs a
  // synchronous read of "did this finalize succeed" without depending on
  // `result` (a dependency would re-run the effect, and re-subscribing an
  // unmount handler on every render defeats the point — it must only ever
  // run once, on the component's actual teardown).
  const resultRef = useRef<FinalizeForTableResponse | null>(null);
  useEffect(() => {
    resultRef.current = result;
  }, [result]);

  function resetForm() {
    setTableId('');
    setStoryTitle('');
    setStoryDescription('');
    setFieldErrors({});
    setResult(null);
  }

  /** Clears the finalized draft from cache once the player has seen the result. */
  function clearFinalizedDraft() {
    queryClient.setQueryData(characterCreationKeys.draft(), null);
  }

  function handleOpenChange(next: boolean) {
    if (!next && result) {
      clearFinalizedDraft();
    }
    onOpenChange(next);
    if (!next) resetForm();
  }

  // Route-level safety net (#3268 review fix): this dialog stays mounted
  // across open/close (its parent, `ReviewStage`, only toggles the `open`
  // prop), so `handleOpenChange` above catches the in-dialog dismissal path
  // (X button, Cancel, "Go to My Table"). But a player can also leave via
  // browser Back or any other router nav that unmounts `ReviewStage` (and
  // this dialog with it) without `handleOpenChange` ever running — e.g.
  // right after a successful finalize, before they click through. Without
  // this, the already-finalized draft stays cached (`staleTime` is 5 min —
  // see `queryClient.ts`), and a return to /characters/create resurrects a
  // phantom draft whose actions all 404 server-side. This effect's cleanup
  // fires on every unmount path, so it clears the cache whenever the dialog
  // goes away having actually finalized, regardless of how the player left.
  // (`clearFinalizedDraft` intentionally omitted from deps: it must run its
  // cleanup only on the component's final unmount, not on every re-render.)
  useEffect(() => {
    return () => {
      if (resultRef.current) {
        clearFinalizedDraft();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
    finalize.mutate(
      {
        draftId,
        payload: {
          target_table: parseInt(tableId, 10),
          story_title: storyTitle.trim(),
          story_description: storyDescription.trim() || undefined,
        },
      },
      {
        onSuccess: (data) => setResult(data),
        onError: (err: unknown) => setFieldErrors(bulletinErrorsFrom(err)),
      }
    );
  }

  const isValid = tableId !== '' && storyTitle.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Finalize for My Table</DialogTitle>
          <DialogDescription>
            Create this character directly on the Available roster for one of your GM tables, with a
            new story tied to it.
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className="space-y-4">
            <p className="text-sm">{result.message}</p>
            <DialogFooter>
              <Button asChild onClick={clearFinalizedDraft}>
                <Link to={`/tables/${tableId}`}>Go to My Table</Link>
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="finalize-table">Table *</Label>
              <Select value={tableId} onValueChange={setTableId}>
                <SelectTrigger id="finalize-table">
                  <SelectValue placeholder="Select a table" />
                </SelectTrigger>
                <SelectContent>
                  {tables.map((table) => (
                    <SelectItem key={table.id} value={String(table.id)}>
                      {table.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1">
              <Label htmlFor="finalize-story-title">Story Title *</Label>
              <Input
                id="finalize-story-title"
                value={storyTitle}
                onChange={(e) => setStoryTitle(e.target.value)}
                placeholder="e.g. The Salt Road"
                required
                aria-describedby={
                  fieldErrors.story_title ? 'finalize-story-title-error' : undefined
                }
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="finalize-story-description">
                Story Description{' '}
                <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="finalize-story-description"
                value={storyDescription}
                onChange={(e) => setStoryDescription(e.target.value)}
                placeholder="What's this story about?"
                rows={3}
                className="resize-y"
              />
            </div>

            <FormErrors errors={fieldErrors} />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!isValid || finalize.isPending}>
                {finalize.isPending ? 'Finalizing…' : 'Finalize for My Table'}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
