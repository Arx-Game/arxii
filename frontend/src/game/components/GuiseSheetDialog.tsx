/**
 * GuiseSheetDialog — author a cover persona's fabricated bio (#1682).
 *
 * The web face of the #1270 Guise Sheet: a cover/established persona needs its
 * OWN concept/quote/answers/background so the absence of a bio doesn't
 * instantly out it as fake. Prefills from the persona's current guise fields;
 * saving writes the full four-field state (clearing a field is a real edit).
 * Never offered for the PRIMARY face — the real bio lives on the sheet.
 *
 * "How this face looks" (#4033, #4889) sits above the bio: the face's portrait (picked,
 * uploaded or removed at once) and, for a persona, its own description, saved with the
 * sheet. The same dialog opens on an alternate self from the form switcher; a self with no
 * persona has no description or bio, so it shows only the portrait.
 */

import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import { PersonaAvatar } from '@/components/PersonaAvatar';
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

import { extractErrorMessage } from '@/lib/errors';

import type { SwitchableAlternateSelf } from '../formQueries';
import {
  useFacePortraitMutation,
  useSetFaceDescriptionMutation,
  type FaceTarget,
  type PortraitChange,
} from '../faceQueries';
import { useSetPersonaProfileMutation, type SwitchablePersona } from '../personaQueries';
import { FacePortraitPicker } from './FacePortraitPicker';

interface GuiseSheetDialogProps {
  /** The face's persona; null for an alternate self that wears none. */
  persona: SwitchablePersona | null;
  /** Set when the dialog was opened on an alternate self: its portrait is the one written. */
  alternateSelf?: SwitchableAlternateSelf | null;
  characterSheetId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GuiseSheetDialog({
  persona,
  alternateSelf = null,
  characterSheetId,
  open,
  onOpenChange,
}: GuiseSheetDialogProps) {
  const save = useSetPersonaProfileMutation(characterSheetId);
  const saveDescription = useSetFaceDescriptionMutation(characterSheetId);
  const portrait = useFacePortraitMutation(characterSheetId);
  const [concept, setConcept] = useState(persona?.guise_concept ?? '');
  const [quote, setQuote] = useState(persona?.guise_quote ?? '');
  const [neverDo, setNeverDo] = useState(persona?.guise_never_do ?? '');
  const [protect, setProtect] = useState(persona?.guise_protect ?? '');
  const [fear, setFear] = useState(persona?.guise_fear ?? '');
  const [background, setBackground] = useState(persona?.guise_background ?? '');
  const [description, setDescription] = useState(persona?.description ?? '');
  const [pickerOpen, setPickerOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Re-prefill whenever the dialog opens (the persona's saved bio may have changed).
  useEffect(() => {
    if (open) {
      setConcept(persona?.guise_concept ?? '');
      setQuote(persona?.guise_quote ?? '');
      setNeverDo(persona?.guise_never_do ?? '');
      setProtect(persona?.guise_protect ?? '');
      setFear(persona?.guise_fear ?? '');
      setBackground(persona?.guise_background ?? '');
      setDescription(persona?.description ?? '');
      save.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- prefill only on open/persona change
  }, [open, persona?.id, alternateSelf?.id]);

  const personaTarget: FaceTarget | null = persona
    ? { kind: 'persona', personaId: persona.id }
    : null;
  const target: FaceTarget | null = alternateSelf
    ? { kind: 'alternate', alternateSelfId: alternateSelf.id }
    : personaTarget;
  const faceName = persona?.name ?? alternateSelf?.display_name ?? 'this face';
  const guiseTitle =
    persona && !alternateSelf
      ? `Guise sheet: ${faceName}`
      : `Face: ${alternateSelf?.display_name || faceName}`;
  const hasPortrait = alternateSelf ? alternateSelf.has_portrait : (persona?.has_portrait ?? false);
  const portraitUrl = alternateSelf
    ? alternateSelf.thumbnail_url
    : (persona?.thumbnail_media_url ?? persona?.thumbnail_url ?? null);

  const changePortrait = (change: PortraitChange) => {
    if (!target) return;
    portrait.mutate(
      { target, change },
      {
        onSuccess: () => setPickerOpen(false),
        onError: (err) => toast.error(extractErrorMessage(err, 'The portrait could not be saved.')),
      }
    );
  };

  const saving = save.isPending || saveDescription.isPending;

  const submit = async () => {
    if (!persona) return;
    try {
      if (description !== persona.description) {
        await saveDescription.mutateAsync({ personaId: persona.id, description });
      }
      await save.mutateAsync({
        personaId: persona.id,
        body: { concept, quote, never_do: neverDo, protect, fear, background },
      });
      onOpenChange(false);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Could not save the guise sheet.'));
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{guiseTitle}</DialogTitle>
          {persona && !alternateSelf && (
            <DialogDescription>
              The bio this cover identity presents to the world. A guise with no story outs itself;
              give it one.
            </DialogDescription>
          )}
        </DialogHeader>
        <div className="space-y-3">
          <section className="space-y-2 border-b pb-3" aria-label="How this face looks">
            <h3 className="text-sm font-semibold">How this face looks</h3>
            <div className="flex items-start gap-3">
              <PersonaAvatar
                source={{ name: faceName, thumbnailMediaUrl: portraitUrl }}
                size="lg"
                className="h-[4.5rem] w-[4.5rem]"
              />
              <div className="flex flex-col items-start gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={portrait.isPending}
                  onClick={() => setPickerOpen(true)}
                >
                  Choose a picture
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={portrait.isPending}
                  onClick={() => fileInput.current?.click()}
                >
                  Upload a picture
                </Button>
                {hasPortrait && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="border-destructive/40 text-destructive hover:text-destructive"
                    disabled={portrait.isPending}
                    onClick={() => changePortrait({ kind: 'clear' })}
                  >
                    Remove portrait
                  </Button>
                )}
                <input
                  ref={fileInput}
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  className="sr-only"
                  aria-label="Upload a portrait file"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) changePortrait({ kind: 'upload', file });
                    event.target.value = '';
                  }}
                />
              </div>
            </div>
            {persona && (
              <div className="space-y-1">
                <Label htmlFor="guise-description">Description</Label>
                <Textarea
                  id="guise-description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={4}
                  maxLength={4000}
                />
              </div>
            )}
          </section>
          {persona && (
            <>
              <div className="space-y-1">
                <Label htmlFor="guise-concept">Concept</Label>
                <Input
                  id="guise-concept"
                  value={concept}
                  onChange={(e) => setConcept(e.target.value)}
                  placeholder="Wandering scholar of little consequence"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="guise-quote">Quote</Label>
                <Input
                  id="guise-quote"
                  value={quote}
                  onChange={(e) => setQuote(e.target.value)}
                  placeholder="A motto this identity lives by"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="guise-never-do">What would you never do?</Label>
                <Input
                  id="guise-never-do"
                  value={neverDo}
                  onChange={(e) => setNeverDo(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="guise-protect">What would you protect at all costs?</Label>
                <Input
                  id="guise-protect"
                  value={protect}
                  onChange={(e) => setProtect(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="guise-fear">What are you deathly afraid of?</Label>
                <Input id="guise-fear" value={fear} onChange={(e) => setFear(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="guise-background">Background</Label>
                <Textarea
                  id="guise-background"
                  value={background}
                  onChange={(e) => setBackground(e.target.value)}
                  rows={4}
                />
              </div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={saving}>
            {persona ? 'Cancel' : 'Close'}
          </Button>
          {persona && (
            <Button onClick={submit} disabled={saving}>
              {saving ? 'Saving…' : 'Save guise sheet'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
      <FacePortraitPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onPick={(mediaId) => changePortrait({ kind: 'pick', mediaId })}
        onUpload={(file) => changePortrait({ kind: 'upload', file })}
        busy={portrait.isPending}
      />
    </Dialog>
  );
}
