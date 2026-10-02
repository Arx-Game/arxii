/**
 * PreparedTextDialog — a table GM (or staff) prepares a character's next
 * Crossing text and Audere surge line (#4101 Task 11, demo Screen 6).
 *
 * The Crossing fields (Vision/Manifestation/Deed title) and the Audere surge
 * line are two separate backend rows (`CharacterCrossingText` /
 * `CharacterSurgeText`); Save creates-or-patches each independently, in
 * parallel, on one submit. Fix round 1 (#4101 Task 11):
 * - Saving an all-blank row with no existing id is skipped entirely (a GM who
 *   only fills in the surge must not mint an empty Crossing row, and vice
 *   versa); updating an EXISTING row to blank still saves.
 * - A save failure invalidates both queries, so a race (e.g. the Crossing
 *   fired between load and save) refetches the real current state instead of
 *   leaving the dialog retrying against a now-stale "unused" row forever.
 * - The form seeds from server data only once per mount, the first time each
 *   query resolves — a later refetch (the invalidation above, or an ordinary
 *   background refetch) never overwrites text the GM is mid-edit on.
 * - A successful save shows a transient "Saved." `role="status"` line.
 */
import { useEffect, useRef, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  usePreparedCrossingText,
  usePreparedSurgeText,
  useSavePreparedCrossingText,
  useSavePreparedSurgeText,
  type PreparedByRole,
} from '../preparedTextQueries';

const PREPARED_BY_ROLE_LABEL: Record<PreparedByRole, string> = {
  staff: 'Staff',
  table_gm: 'Table GM',
};

export interface PreparedTextDialogProps {
  characterSheetId: number;
  characterName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PreparedTextDialog({
  characterSheetId,
  characterName,
  open,
  onOpenChange,
}: PreparedTextDialogProps) {
  const { data: crossing } = usePreparedCrossingText(characterSheetId);
  const { data: surge } = usePreparedSurgeText(characterSheetId);
  const saveCrossing = useSavePreparedCrossingText(characterSheetId);
  const saveSurge = useSavePreparedSurgeText(characterSheetId);

  const [visionText, setVisionText] = useState('');
  const [manifestationText, setManifestationText] = useState('');
  const [deedTitle, setDeedTitle] = useState('');
  const [surgeText, setSurgeText] = useState('');
  const [justSaved, setJustSaved] = useState(false);

  // Seed from server data only ONCE per dialog open -- a later refetch (the
  // on-failure invalidation below, or any background refetch) must never
  // stomp text the GM is mid-edit on. `data` is `undefined` while loading and
  // resolves to the row or `null`, so `!== undefined` is "this query has
  // answered at least once."
  const crossingSeeded = useRef(false);
  const surgeSeeded = useRef(false);

  useEffect(() => {
    if (open) {
      crossingSeeded.current = false;
      surgeSeeded.current = false;
    }
  }, [open]);

  useEffect(() => {
    if (!crossingSeeded.current && crossing !== undefined) {
      setVisionText(crossing?.vision_text ?? '');
      setManifestationText(crossing?.manifestation_text ?? '');
      setDeedTitle(crossing?.deed_title ?? '');
      crossingSeeded.current = true;
    }
  }, [crossing]);

  useEffect(() => {
    if (!surgeSeeded.current && surge !== undefined) {
      setSurgeText(surge?.surge_text ?? '');
      surgeSeeded.current = true;
    }
  }, [surge]);

  const preparedByLabel = crossing
    ? PREPARED_BY_ROLE_LABEL[crossing.prepared_by_role]
    : `Staff, or ${characterName}'s table GM`;

  function editField<T>(setter: (value: T) => void) {
    return (value: T) => {
      setJustSaved(false);
      setter(value);
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setJustSaved(false);

    const crossingBlank = !visionText.trim() && !manifestationText.trim() && !deedTitle.trim();
    const surgeBlank = !surgeText.trim();

    const tasks: Promise<unknown>[] = [];
    // An all-blank row with no existing id is skipped -- never mint an empty
    // Crossing/surge record just because the GM only filled in the other
    // half of the dialog. An EXISTING row still saves even when cleared back
    // to blank (that is a deliberate "clear it" edit, not a no-op).
    if (crossing?.id != null || !crossingBlank) {
      tasks.push(
        saveCrossing.mutateAsync({
          id: crossing?.id,
          vision_text: visionText,
          manifestation_text: manifestationText,
          deed_title: deedTitle,
        })
      );
    }
    if (surge?.id != null || !surgeBlank) {
      tasks.push(saveSurge.mutateAsync({ id: surge?.id, surge_text: surgeText }));
    }
    if (tasks.length === 0) return;

    const results = await Promise.allSettled(tasks);
    if (results.every((r) => r.status === 'fulfilled')) {
      setJustSaved(true);
    }
  }

  const saving = saveCrossing.isPending || saveSurge.isPending;
  const saveErrorMessage =
    (saveCrossing.error as Error | null)?.message ?? (saveSurge.error as Error | null)?.message;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Crossing text for {characterName}</DialogTitle>
          <DialogDescription>
            Prepared for {characterName}&apos;s next Audere Majora crossing and Audere surges.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="prepared-text-character">Character</Label>
            <Input id="prepared-text-character" value={characterName} readOnly disabled />
          </div>
          <div className="space-y-1">
            <Label htmlFor="prepared-text-vision">Vision (private)</Label>
            <Textarea
              id="prepared-text-vision"
              value={visionText}
              onChange={(e) => editField(setVisionText)(e.target.value)}
              rows={3}
              className="resize-y"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="prepared-text-manifestation">Manifestation (room)</Label>
            <Textarea
              id="prepared-text-manifestation"
              value={manifestationText}
              onChange={(e) => editField(setManifestationText)(e.target.value)}
              rows={3}
              className="resize-y"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="prepared-text-deed-title">Deed title</Label>
            <Input
              id="prepared-text-deed-title"
              value={deedTitle}
              onChange={(e) => editField(setDeedTitle)(e.target.value)}
            />
          </div>
          {/* Not an input -- plain read-only text, never a `<Label htmlFor>`
              pointing at a non-focusable element. */}
          <dl className="space-y-1">
            <dt className="text-sm font-medium leading-none">Prepared by</dt>
            <dd className="text-sm text-muted-foreground">{preparedByLabel}</dd>
          </dl>
          <div className="space-y-1 border-t pt-4">
            <Label htmlFor="prepared-text-surge">Audere surge</Label>
            <Textarea
              id="prepared-text-surge"
              value={surgeText}
              onChange={(e) => editField(setSurgeText)(e.target.value)}
              rows={3}
              className="resize-y"
            />
          </div>
          {saveErrorMessage && (
            <p role="alert" className="text-sm text-destructive">
              {saveErrorMessage}
            </p>
          )}
          {justSaved && !saveErrorMessage && (
            <p role="status" className="text-sm text-muted-foreground">
              Saved.
            </p>
          )}
          <DialogFooter>
            <Button type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
