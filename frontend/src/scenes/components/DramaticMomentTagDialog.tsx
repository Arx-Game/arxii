/**
 * DramaticMomentTagDialog — GM control to tag a pose as a dramatic moment (#1139).
 *
 * Opens a dialog with a picker for authored DramaticMomentType values and
 * POSTs a tag for the given interaction via the magic dramatic-moment-tags API.
 * A second picker names the resonance the tag pays (#5327): any resonance, in the poser's
 * aura or not. It shows the moment type's own resonance until the GM picks another, and only
 * a pick of the GM's own goes to the server as `resonance`.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { fetchDramaticMomentTypes, postDramaticMomentTag } from '../queries';
import { sceneFeedSceneKey } from '@/scenes/sceneFeedCache';
import { useResonanceCatalog } from '@/magic/queries';

interface DramaticMomentTagDialogProps {
  /** Whether the dialog is open. */
  open: boolean;
  /** Callback to close the dialog. */
  onClose: () => void;
  /** The interaction (pose) id to tag. */
  interactionId: number;
  /** Scene id — used to invalidate the scene-interactions cache after tagging. */
  sceneId: string;
}

export function DramaticMomentTagDialog({
  open,
  onClose,
  interactionId,
  sceneId,
}: DramaticMomentTagDialogProps) {
  const queryClient = useQueryClient();
  const [selectedTypeId, setSelectedTypeId] = useState<string>('');
  // The GM's own resonance pick; null leaves the moment type's resonance showing and paying.
  const [pickedResonanceId, setPickedResonanceId] = useState<string | null>(null);
  const { data: resonances = [] } = useResonanceCatalog();

  const { data: momentTypes = [], isLoading } = useQuery({
    queryKey: ['dramatic-moment-types'],
    queryFn: fetchDramaticMomentTypes,
    // Only fetch when the dialog is open
    enabled: open,
  });

  const selectedType = momentTypes.find((type) => String(type.id) === selectedTypeId);
  const shownResonanceId =
    pickedResonanceId ?? (selectedType ? String(selectedType.resonance) : '');

  function reset() {
    setSelectedTypeId('');
    setPickedResonanceId(null);
  }

  const tagMutation = useMutation({
    mutationFn: () =>
      postDramaticMomentTag({
        moment_type: Number(selectedTypeId),
        interaction: interactionId,
        ...(pickedResonanceId !== null ? { resonance: Number(pickedResonanceId) } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: sceneFeedSceneKey(sceneId) });
      onClose();
      reset();
    },
  });

  function handleOpenChange(isOpen: boolean) {
    if (!isOpen) {
      onClose();
      reset();
    }
  }

  function handleSubmit() {
    if (!selectedTypeId) return;
    tagMutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent {...NO_DESCRIPTION}>
        <DialogHeader>
          <DialogTitle>Tag Dramatic Moment</DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading moment types…</p>
        ) : (
          <Select value={selectedTypeId} onValueChange={setSelectedTypeId}>
            <SelectTrigger data-testid="moment-type-select">
              <SelectValue placeholder="Choose a moment type" />
            </SelectTrigger>
            <SelectContent>
              {momentTypes.map((type) => (
                <SelectItem key={type.id} value={String(type.id)}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {resonances.length > 0 && (
          <Select value={shownResonanceId} onValueChange={setPickedResonanceId}>
            <SelectTrigger data-testid="moment-resonance-select" aria-label="Resonance">
              <SelectValue placeholder="Choose a resonance" />
            </SelectTrigger>
            <SelectContent>
              {resonances.map((resonance) => (
                <SelectItem key={resonance.id} value={String(resonance.id)}>
                  {resonance.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {tagMutation.isError && (
          <p className="text-sm text-destructive">
            {tagMutation.error.message || 'Failed to tag moment. Please try again.'}
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={tagMutation.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!selectedTypeId || tagMutation.isPending}
            data-testid="tag-moment-submit"
          >
            {tagMutation.isPending ? 'Tagging…' : 'Tag Moment'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
