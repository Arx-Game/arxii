/**
 * MarkingsEditor (#2985) — CG appearance-stage authoring for body markings.
 *
 * Tattoos, scars, brands, birthmarks, runes: each a row on the draft
 * (`/api/character-creation/draft-markings/`), materialized onto the
 * character's true form at finalization. Optional — no stage validation
 * reads these. Self-contained CRUD (react-query) rather than riding the
 * draft PATCH, since rows are structured records, not draft_data blobs.
 */

import { Button } from '@/components/ui/button';
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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  createDraftMarking,
  deleteDraftMarking,
  listDraftMarkings,
  type DraftMarkingCreate,
} from '../api';

const MARKING_KINDS = [
  { value: 'tattoo', label: 'Tattoo' },
  { value: 'scar', label: 'Scar' },
  { value: 'brand', label: 'Brand' },
  { value: 'birthmark', label: 'Birthmark' },
  { value: 'rune', label: 'Rune' },
];

const BODY_REGIONS = [
  { value: 'head', label: 'Head' },
  { value: 'face', label: 'Face' },
  { value: 'neck', label: 'Neck' },
  { value: 'shoulders', label: 'Shoulders' },
  { value: 'torso', label: 'Torso' },
  { value: 'back', label: 'Back' },
  { value: 'waist', label: 'Waist' },
  { value: 'left_arm', label: 'Left Arm' },
  { value: 'right_arm', label: 'Right Arm' },
  { value: 'left_hand', label: 'Left Hand' },
  { value: 'right_hand', label: 'Right Hand' },
  { value: 'left_leg', label: 'Left Leg' },
  { value: 'right_leg', label: 'Right Leg' },
  { value: 'feet', label: 'Feet' },
];

const EMPTY_FORM: DraftMarkingCreate = {
  body_region: 'torso',
  kind: 'tattoo',
  name: '',
  description: '',
};

const MARKINGS_QUERY_KEY = ['draft-markings'] as const;

export function MarkingsEditor() {
  const queryClient = useQueryClient();
  const { data: markings = [] } = useQuery({
    queryKey: MARKINGS_QUERY_KEY,
    queryFn: listDraftMarkings,
  });
  const [form, setForm] = useState<DraftMarkingCreate>(EMPTY_FORM);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: MARKINGS_QUERY_KEY });
  const addMutation = useMutation({
    mutationFn: createDraftMarking,
    onSuccess: () => {
      setForm(EMPTY_FORM);
      void invalidate();
    },
  });
  const removeMutation = useMutation({
    mutationFn: deleteDraftMarking,
    onSuccess: () => void invalidate(),
  });

  const regionLabel = (value: string) =>
    BODY_REGIONS.find((r) => r.value === value)?.label ?? value;
  const kindLabel = (value: string) => MARKING_KINDS.find((k) => k.value === value)?.label ?? value;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Markings</h3>
        <p className="text-sm text-muted-foreground">
          Tattoos, scars, brands, birthmarks — what your character&apos;s skin remembers. Clothing
          conceals a marking at the regions it covers; revealing garments and the in-game reveal
          bare it. Optional.
        </p>
      </div>

      {markings.length > 0 && (
        <ul className="space-y-2">
          {markings.map((marking) => (
            <li
              key={marking.id}
              className="flex items-start justify-between gap-2 rounded-md border p-3"
            >
              <div className="min-w-0">
                <div className="text-sm font-medium">
                  {marking.name}
                  <span className="ml-2 text-xs text-muted-foreground">
                    {kindLabel(marking.kind)} · {regionLabel(marking.body_region)}
                  </span>
                </div>
                {marking.description && (
                  <p className="mt-1 text-xs text-muted-foreground">{marking.description}</p>
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeMutation.mutate(marking.id)}
                disabled={removeMutation.isPending}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="marking-kind">Kind</Label>
          <Select value={form.kind} onValueChange={(kind) => setForm((f) => ({ ...f, kind }))}>
            <SelectTrigger id="marking-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MARKING_KINDS.map((kind) => (
                <SelectItem key={kind.value} value={kind.value}>
                  {kind.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="marking-region">Where</Label>
          <Select
            value={form.body_region}
            onValueChange={(body_region) => setForm((f) => ({ ...f, body_region }))}
          >
            <SelectTrigger id="marking-region">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {BODY_REGIONS.map((region) => (
                <SelectItem key={region.value} value={region.value}>
                  {region.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="marking-name">Name</Label>
          <Input
            id="marking-name"
            value={form.name}
            maxLength={100}
            placeholder="a coiled serpent tattoo"
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
        </div>
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="marking-description">Description (shown on close inspection)</Label>
          <Textarea
            id="marking-description"
            value={form.description}
            rows={2}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
        </div>
        <div className="sm:col-span-2">
          <Button
            type="button"
            size="sm"
            disabled={!form.name.trim() || addMutation.isPending}
            onClick={() => addMutation.mutate({ ...form, name: form.name.trim() })}
          >
            Add marking
          </Button>
        </div>
      </div>
    </div>
  );
}
