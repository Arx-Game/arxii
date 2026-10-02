/**
 * PreparedTextDialog — a table GM (or staff) prepares a character's next
 * Crossing text and Audere surge line (#4101 Task 11, demo Screen 6).
 *
 * The Crossing fields (Vision/Manifestation/Deed title) and the Audere surge
 * line are two separate backend rows (`CharacterCrossingText` /
 * `CharacterSurgeText`); Save creates-or-patches each independently, in
 * parallel, on one submit.
 */
import { useEffect, useState } from 'react';
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

  useEffect(() => {
    setVisionText(crossing?.vision_text ?? '');
    setManifestationText(crossing?.manifestation_text ?? '');
    setDeedTitle(crossing?.deed_title ?? '');
  }, [crossing]);

  useEffect(() => {
    setSurgeText(surge?.surge_text ?? '');
  }, [surge]);

  const preparedByLabel = crossing
    ? PREPARED_BY_ROLE_LABEL[crossing.prepared_by_role]
    : `Staff, or ${characterName}'s table GM`;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    saveCrossing.mutate({
      id: crossing?.id,
      vision_text: visionText,
      manifestation_text: manifestationText,
      deed_title: deedTitle,
    });
    saveSurge.mutate({ id: surge?.id, surge_text: surgeText });
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
              onChange={(e) => setVisionText(e.target.value)}
              rows={3}
              className="resize-y"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="prepared-text-manifestation">Manifestation (room)</Label>
            <Textarea
              id="prepared-text-manifestation"
              value={manifestationText}
              onChange={(e) => setManifestationText(e.target.value)}
              rows={3}
              className="resize-y"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="prepared-text-deed-title">Deed title</Label>
            <Input
              id="prepared-text-deed-title"
              value={deedTitle}
              onChange={(e) => setDeedTitle(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="prepared-text-prepared-by">Prepared by</Label>
            <p id="prepared-text-prepared-by" className="text-sm text-muted-foreground">
              {preparedByLabel}
            </p>
          </div>
          <div className="space-y-1 border-t pt-4">
            <Label htmlFor="prepared-text-surge">Audere surge</Label>
            <Textarea
              id="prepared-text-surge"
              value={surgeText}
              onChange={(e) => setSurgeText(e.target.value)}
              rows={3}
              className="resize-y"
            />
          </div>
          {saveErrorMessage && (
            <p role="alert" className="text-sm text-destructive">
              {saveErrorMessage}
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
