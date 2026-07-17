/**
 * RoomAuraPicker (#2036) — tag/untag the current room's resonance aura.
 *
 * Mounted in RoomPanel under the same owner-or-tenant standing condition as
 * the "Set as Home" button. Lists the caller's own claimed resonances
 * (reused via `useCharacterResonances`, the same hook `MotifStylePanel`
 * uses) and dispatches `tag_room_resonance` / `untag_room_resonance`
 * through the existing `dispatchRoomBuilder` helper — the same seam
 * `set_primary_home` rides in `RoomPanel.tsx`.
 *
 * Wire contract: `TagRoomResonanceAction` / `UntagRoomResonanceAction`
 * (src/actions/definitions/locations.py) via
 * `POST /api/actions/characters/{characterId}/dispatch/`. Both take a single
 * `resonance_id` kwarg (a resonance pk, not a CharacterResonance row id).
 * Minimal by design (#2036 spec, "frontend resonance-aura picker UI polish
 * pass" is a deferred follow-up) — no read of the room's currently-tagged
 * aura (not exposed by `ForRoomResult` yet), just tag/clear a chosen claimed
 * resonance.
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { dispatchRoomBuilder, type DispatchResult } from '@/buildings/api';
import { buildingKeys } from '@/buildings/queries';
import { useCharacterResonances } from '@/magic/queries';

interface RoomAuraPickerProps {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the acting character. */
  characterId: number;
  roomId: number;
}

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

export function RoomAuraPicker({ characterId, roomId }: RoomAuraPickerProps) {
  const { data: resonances = [], isLoading: resonancesLoading } =
    useCharacterResonances(characterId);
  const queryClient = useQueryClient();
  const [resonanceId, setResonanceId] = useState<number | ''>('');

  const invalidateAndToast = ({ message, success }: DispatchResult) => {
    if (success === false) {
      toast.error(message);
      return;
    }
    toast.success(message);
    queryClient.invalidateQueries({ queryKey: buildingKeys.forRoom(roomId) });
  };

  const tag = useMutation({
    mutationFn: () =>
      dispatchRoomBuilder(characterId, 'tag_room_resonance', { resonance_id: resonanceId }),
    onSuccess: invalidateAndToast,
    onError: (error: Error) => toast.error(error.message),
  });

  const untag = useMutation({
    mutationFn: () =>
      dispatchRoomBuilder(characterId, 'untag_room_resonance', { resonance_id: resonanceId }),
    onSuccess: invalidateAndToast,
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <div className="space-y-2 border-b p-2" data-testid="room-aura-picker">
      <Label htmlFor="room-aura-select">Room Aura</Label>
      {resonancesLoading ? (
        <p className="text-sm text-muted-foreground">Loading claimed resonances…</p>
      ) : resonances.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="room-aura-no-resonances">
          Claim a resonance first to tag this room's aura.
        </p>
      ) : (
        <div className="flex flex-wrap items-end gap-2">
          <select
            id="room-aura-select"
            data-testid="room-aura-select"
            className={`${SELECT_CLASS} min-w-40 flex-1`}
            value={resonanceId}
            onChange={(e) => setResonanceId(e.target.value === '' ? '' : Number(e.target.value))}
          >
            <option value="">Select a resonance…</option>
            {resonances.map((cr) => (
              <option key={cr.resonance} value={cr.resonance}>
                {cr.resonance_name}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={resonanceId === '' || tag.isPending}
            onClick={() => tag.mutate()}
            data-testid="room-aura-tag"
          >
            Tag Aura
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={resonanceId === '' || untag.isPending}
            onClick={() => untag.mutate()}
            data-testid="room-aura-clear"
          >
            Clear Aura
          </Button>
        </div>
      )}
    </div>
  );
}
