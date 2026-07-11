/**
 * RelationshipWriteupDialog (#2159) — one dialog covering the four positive
 * relationship-building write actions: `impression` (first_impression),
 * `development` (develop), `capstone`, and `redistribute`. Mode is a fixed
 * prop the caller decides contextually (e.g. the card-drawer quick action
 * picks development-vs-impression by checking for an existing relationship
 * first) — this dialog never lets the player switch modes mid-form.
 *
 * Field shape mirrors the write serializers in `world/relationships/serializers.py`
 * (~L340-410): every mode has track(s) + points + title + writeup + visibility;
 * `coloring` is impression-only; `redistribute` swaps the single track picker for
 * source/target track pickers. `target_persona_id` is always the caller-supplied
 * `targetPersonaId` (a `Persona` pk, e.g. `PoseUnitAvatarClickPersona.id` from the
 * card drawer) — a different identifier space than the `CharacterSheet` pk used to
 * look up an existing relationship, bridged server-side by `_resolve_target_sheet`.
 */

import { useState } from 'react';
import { toast } from 'sonner';

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
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
import { extractErrorMessage } from '@/lib/errors';
import {
  useCreateCapstone,
  useCreateDevelopment,
  useCreateFirstImpression,
  useRedistributePoints,
  useRelationshipTracks,
} from '../queries';
import type { components } from '@/generated/api';

export type RelationshipWriteupMode = 'impression' | 'development' | 'capstone' | 'redistribute';

type ColoringEnum = components['schemas']['ColoringEnum'];
type VisibilityFdaEnum = components['schemas']['VisibilityFdaEnum'];

const MODE_LABELS: Record<RelationshipWriteupMode, string> = {
  impression: 'Record an impression',
  development: 'Develop this relationship',
  capstone: 'Record a capstone moment',
  redistribute: 'Redistribute points',
};

const DEFAULT_VISIBILITY: Record<RelationshipWriteupMode, VisibilityFdaEnum> = {
  impression: 'private',
  development: 'private',
  capstone: 'shared',
  redistribute: 'private',
};

const VISIBILITY_LABELS: Record<VisibilityFdaEnum, string> = {
  private: 'Private (just you)',
  shared: 'Shared (the subject can see and commend it)',
  gossip: 'Gossip (word travels)',
  public: 'Public (anyone can see it)',
};

const COLORING_LABELS: Record<ColoringEnum, string> = {
  positive: 'Positive',
  neutral: 'Neutral',
  negative: 'Negative',
};

export interface RelationshipWriteupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: RelationshipWriteupMode;
  /** The target's `Persona` pk — the write payload's `target_persona_id`. */
  targetPersonaId: number;
  targetName: string;
  onSuccess?: () => void;
}

export function RelationshipWriteupDialog({
  open,
  onOpenChange,
  mode,
  targetPersonaId,
  targetName,
  onSuccess,
}: RelationshipWriteupDialogProps) {
  const { data: tracks = [] } = useRelationshipTracks();

  const [trackId, setTrackId] = useState<number | null>(null);
  const [sourceTrackId, setSourceTrackId] = useState<number | null>(null);
  const [targetTrackId, setTargetTrackId] = useState<number | null>(null);
  const [points, setPoints] = useState('');
  const [title, setTitle] = useState('');
  const [writeup, setWriteup] = useState('');
  const [coloring, setColoring] = useState<ColoringEnum>('neutral');
  const [visibility, setVisibility] = useState<VisibilityFdaEnum>(DEFAULT_VISIBILITY[mode]);
  const [localError, setLocalError] = useState<string | null>(null);

  const createFirstImpression = useCreateFirstImpression();
  const createDevelopment = useCreateDevelopment();
  const createCapstone = useCreateCapstone();
  const redistributePoints = useRedistributePoints();
  const isPending =
    createFirstImpression.isPending ||
    createDevelopment.isPending ||
    createCapstone.isPending ||
    redistributePoints.isPending;

  function resetForm() {
    setTrackId(null);
    setSourceTrackId(null);
    setTargetTrackId(null);
    setPoints('');
    setTitle('');
    setWriteup('');
    setColoring('neutral');
    setVisibility(DEFAULT_VISIBILITY[mode]);
    setLocalError(null);
  }

  function handleOpenChange(next: boolean) {
    if (!next) resetForm();
    onOpenChange(next);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);

    const parsedPoints = Number(points);
    if (points.trim() === '' || Number.isNaN(parsedPoints) || parsedPoints < 0) {
      setLocalError('Points must be zero or a positive number.');
      return;
    }
    if (title.trim() === '') {
      setLocalError('A title is required.');
      return;
    }
    if (writeup.trim() === '') {
      setLocalError('A writeup is required.');
      return;
    }
    if (mode === 'redistribute') {
      if (sourceTrackId == null || targetTrackId == null) {
        setLocalError('Choose both a source and a target track.');
        return;
      }
    } else if (trackId == null) {
      setLocalError('Choose a track.');
      return;
    }

    const shared = {
      target_persona_id: targetPersonaId,
      points: parsedPoints,
      title: title.trim(),
      writeup: writeup.trim(),
      visibility,
    };

    const onMutationSuccess = (result: { message: string }) => {
      toast.success(result.message || 'Recorded.');
      handleOpenChange(false);
      onSuccess?.();
    };
    const onMutationError = (err: unknown) => {
      toast.error(extractErrorMessage(err, 'Failed to record this.'));
    };

    if (mode === 'impression') {
      createFirstImpression.mutate(
        { ...shared, track_id: trackId as number, coloring },
        { onSuccess: onMutationSuccess, onError: onMutationError }
      );
    } else if (mode === 'development') {
      createDevelopment.mutate(
        // xp_awarded: no formula exists yet to compute it (docs/roadmap/relationships.md
        // "XP reward formula"); the field defaults to 0 server-side, matching that gap.
        { ...shared, track_id: trackId as number, xp_awarded: 0 },
        { onSuccess: onMutationSuccess, onError: onMutationError }
      );
    } else if (mode === 'capstone') {
      createCapstone.mutate(
        { ...shared, track_id: trackId as number },
        { onSuccess: onMutationSuccess, onError: onMutationError }
      );
    } else {
      redistributePoints.mutate(
        {
          ...shared,
          source_track_id: sourceTrackId as number,
          target_track_id: targetTrackId as number,
        },
        { onSuccess: onMutationSuccess, onError: onMutationError }
      );
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {MODE_LABELS[mode]}: {targetName}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'redistribute' ? (
            <>
              <div className="space-y-1">
                <Label htmlFor="writeup-source-track">From track</Label>
                <Select
                  value={sourceTrackId != null ? String(sourceTrackId) : ''}
                  onValueChange={(v) => setSourceTrackId(Number(v))}
                >
                  <SelectTrigger id="writeup-source-track">
                    <SelectValue placeholder="Select a track" />
                  </SelectTrigger>
                  <SelectContent>
                    {tracks.map((track) => (
                      <SelectItem key={track.id} value={String(track.id)}>
                        {track.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="writeup-target-track">To track</Label>
                <Select
                  value={targetTrackId != null ? String(targetTrackId) : ''}
                  onValueChange={(v) => setTargetTrackId(Number(v))}
                >
                  <SelectTrigger id="writeup-target-track">
                    <SelectValue placeholder="Select a track" />
                  </SelectTrigger>
                  <SelectContent>
                    {tracks.map((track) => (
                      <SelectItem key={track.id} value={String(track.id)}>
                        {track.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </>
          ) : (
            <div className="space-y-1">
              <Label htmlFor="writeup-track">Track</Label>
              <Select
                value={trackId != null ? String(trackId) : ''}
                onValueChange={(v) => setTrackId(Number(v))}
              >
                <SelectTrigger id="writeup-track">
                  <SelectValue placeholder="Select a track" />
                </SelectTrigger>
                <SelectContent>
                  {tracks.map((track) => (
                    <SelectItem key={track.id} value={String(track.id)}>
                      {track.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-1">
            <Label htmlFor="writeup-points">Points</Label>
            <Input
              id="writeup-points"
              type="number"
              min={0}
              value={points}
              onChange={(e) => setPoints(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="writeup-title">Title</Label>
            <Input id="writeup-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>

          <div className="space-y-1">
            <Label htmlFor="writeup-text">Writeup</Label>
            <Textarea
              id="writeup-text"
              value={writeup}
              onChange={(e) => setWriteup(e.target.value)}
              rows={4}
            />
          </div>

          {mode === 'impression' && (
            <div className="space-y-1">
              <Label htmlFor="writeup-coloring">Coloring</Label>
              <Select value={coloring} onValueChange={(v) => setColoring(v as ColoringEnum)}>
                <SelectTrigger id="writeup-coloring">
                  <SelectValue placeholder="Coloring" />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(COLORING_LABELS) as ColoringEnum[]).map((value) => (
                    <SelectItem key={value} value={value}>
                      {COLORING_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-1">
            <Label htmlFor="writeup-visibility">Who can see this</Label>
            <Select value={visibility} onValueChange={(v) => setVisibility(v as VisibilityFdaEnum)}>
              <SelectTrigger id="writeup-visibility">
                <SelectValue placeholder="Visibility" />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(VISIBILITY_LABELS) as VisibilityFdaEnum[]).map((value) => (
                  <SelectItem key={value} value={value}>
                    {VISIBILITY_LABELS[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {localError && <p className="text-sm text-destructive">{localError}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              Record
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
