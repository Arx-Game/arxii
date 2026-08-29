/**
 * AuthorClueDialog (#3432) — mint a new `Clue` pointer via the `author_clue` REGISTRY
 * action, shared by `PlaceClueDialog` (world-builder "New clue…" affordance, mint-then-place)
 * and `StaffSecretsPanel` ("Author a clue to this secret", pre-targeted).
 *
 * The server is the authority on the SENIOR-GM/staff gate and the staff-only SECRET-target
 * rule (#3432 Decision 1/1a) — `isStaff` here only hides/disables what a refusal would bounce
 * anyway, so a stale `isStaff` prop degrades to an honest server refusal, never a leak.
 */
import { type ReactNode, useEffect, useState } from 'react';

import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useAccount } from '@/store/hooks';
import { useWorldBuilderActor } from '@/world-builder/useWorldBuilderActor';

import { useAuthorClueMutation } from '../queries';

type ClueTargetKind = 'codex' | 'mission' | 'rescue' | 'item' | 'persona_link' | 'secret';

const TARGET_KIND_OPTIONS: { value: ClueTargetKind; label: string }[] = [
  { value: 'codex', label: 'Codex Entry' },
  { value: 'mission', label: 'Mission' },
  { value: 'rescue', label: 'Rescue (a held captive)' },
  { value: 'item', label: 'Item (exact pointer)' },
  { value: 'persona_link', label: 'Persona Link (mask piercing)' },
  { value: 'secret', label: 'Character Secret' },
];

/** target_kind values whose FK invariant needs a second target ref (mirrors the model's
 * DISCRIMINATOR_MAP exceptions — see `world.clues.models.Clue`). */
const SECONDARY_TARGET_LABEL: Partial<Record<ClueTargetKind, string>> = {
  persona_link: 'Linked persona (the other side of the pair)',
  item: 'Exact item instance (optional narrowing)',
};

export interface AuthorClueDialogProps {
  trigger: ReactNode;
  /** Pre-target a SECRET clue at this secret id (`StaffSecretsPanel`'s entry point) — locks
   * target_kind to `secret` and hides the kind/target picker entirely. */
  lockedSecretId?: number;
  /** Called with the new clue's slug on success, so a caller can chain into placement. */
  onCreated?: (slug: string) => void;
}

export function AuthorClueDialog({ trigger, lockedSecretId, onCreated }: AuthorClueDialogProps) {
  const isLocked = lockedSecretId != null;
  // Show the SECRET target kind (server enforces the gate regardless — see file docstring).
  const isStaff = useAccount()?.is_staff ?? false;
  const [open, setOpen] = useState(false);
  const [clueName, setClueName] = useState('');
  const [description, setDescription] = useState('');
  const [targetKind, setTargetKind] = useState<ClueTargetKind>(isLocked ? 'secret' : 'codex');
  const [targetId, setTargetId] = useState(isLocked ? String(lockedSecretId) : '');
  const [targetSecondaryId, setTargetSecondaryId] = useState('');

  const characterId = useWorldBuilderActor();
  const mutation = useAuthorClueMutation(characterId ?? 0);

  useEffect(() => {
    if (!open) return;
    setClueName('');
    setDescription('');
    setTargetKind(isLocked ? 'secret' : 'codex');
    setTargetId(isLocked ? String(lockedSecretId) : '');
    setTargetSecondaryId('');
  }, [open, isLocked, lockedSecretId]);

  const visibleKindOptions = TARGET_KIND_OPTIONS.filter(
    (option) => option.value !== 'secret' || isStaff
  );
  const secondaryLabel = SECONDARY_TARGET_LABEL[targetKind];
  const secondaryRequired = targetKind === 'persona_link';

  const canSubmit =
    clueName.trim() !== '' &&
    description.trim() !== '' &&
    targetId.trim() !== '' &&
    (!secondaryRequired || targetSecondaryId.trim() !== '');

  const handleSubmit = () => {
    if (characterId == null) {
      toast.error('Select a character to author as; clue authoring dispatches through it.');
      return;
    }
    const kwargs: Record<string, unknown> = {
      name: clueName.trim(),
      description: description.trim(),
      target_kind: targetKind,
      target_id: Number(targetId),
    };
    if (targetSecondaryId.trim() !== '') {
      kwargs.target_secondary_id = Number(targetSecondaryId);
    }
    mutation.mutate(kwargs, {
      onSuccess: (result) => {
        if (result.success === false) {
          toast.error(result.message);
          return;
        }
        toast.success(result.message);
        const slug = result.data?.slug;
        if (typeof slug === 'string') onCreated?.(slug);
        setOpen(false);
      },
      onError: (error: Error) => toast.error(error.message),
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Author clue</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="author-clue-name">Name</Label>
            <Input
              id="author-clue-name"
              value={clueName}
              onChange={(e) => setClueName(e.target.value)}
              placeholder="Torn Journal Page"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="author-clue-description">Clue text</Label>
            <Textarea
              id="author-clue-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className="resize-y"
              placeholder="What the player sees when they find this clue."
            />
          </div>
          {!isLocked && (
            <div className="space-y-2">
              <Label htmlFor="author-clue-kind">Target kind</Label>
              <Select
                value={targetKind}
                onValueChange={(value) => setTargetKind(value as ClueTargetKind)}
              >
                <SelectTrigger id="author-clue-kind" aria-label="Target kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {visibleKindOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {!isLocked && (
            <div className="space-y-2">
              <Label htmlFor="author-clue-target">Target id</Label>
              <Input
                id="author-clue-target"
                type="number"
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
              />
            </div>
          )}
          {!isLocked && secondaryLabel && (
            <div className="space-y-2">
              <Label htmlFor="author-clue-target-secondary">{secondaryLabel}</Label>
              <Input
                id="author-clue-target-secondary"
                type="number"
                value={targetSecondaryId}
                onChange={(e) => setTargetSecondaryId(e.target.value)}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            data-testid="author-clue-submit"
            onClick={handleSubmit}
            disabled={!canSubmit || mutation.isPending}
          >
            {mutation.isPending ? 'Authoring…' : 'Author clue'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
