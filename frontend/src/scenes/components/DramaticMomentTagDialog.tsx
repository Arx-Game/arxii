/**
 * DramaticMomentTagDialog — GM control to tag a pose as a dramatic moment (#1139).
 *
 * Opens a dialog with a picker for authored DramaticMomentType values and
 * POSTs a tag for the given interaction via the magic dramatic-moment-tags API.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
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

  const { data: momentTypes = [], isLoading } = useQuery({
    queryKey: ['dramatic-moment-types'],
    queryFn: fetchDramaticMomentTypes,
    // Only fetch when the dialog is open
    enabled: open,
  });

  const tagMutation = useMutation({
    mutationFn: () =>
      postDramaticMomentTag({
        moment_type: Number(selectedTypeId),
        interaction: interactionId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] });
      onClose();
      setSelectedTypeId('');
    },
  });

  function handleOpenChange(isOpen: boolean) {
    if (!isOpen) {
      onClose();
      setSelectedTypeId('');
    }
  }

  function handleSubmit() {
    if (!selectedTypeId) return;
    tagMutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Tag Dramatic Moment</DialogTitle>
          <DialogDescription>
            Select a moment type to award to the character who posed this.
          </DialogDescription>
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

        {tagMutation.isError && (
          <p className="text-sm text-destructive">Failed to tag moment. Please try again.</p>
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
