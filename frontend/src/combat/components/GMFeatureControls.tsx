/**
 * GMFeatureControls (#4675, slice 3 of #4651): the GM tab's Add feature control.
 *
 * Shown only when the GM's available actions carry the one `gm_attach_feature` entry
 * (the server's own GM gate). Pick a place from the encounter's places, a feature type
 * and, optionally, the square it is drawn on; the control dispatches the entry with
 * those as kwargs. Each place's features are listed with a Remove button
 * (`gm_detach_feature`). Both refresh the encounter, the scene and the actions, so the
 * map and the stunts show the change before the next poll.
 */

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  combatKeys,
  useCombatEncounter,
  useDispatchPlayerAction,
  useFeatureTypes,
} from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import type { DispatchActionRequest } from '@/combat/types';
import { availableActionsKeys, useAvailableActionsQuery } from '@/scenes/actionQueries';
import type { ActionRef } from '@/scenes/actionTypes';
import { sceneKeys } from '@/scenes/queries';

export interface GMFeatureControlsProps {
  sceneId: number;
  encounterId: number;
  characterId: number;
}

const SELECT_CLASS = 'w-full rounded border border-border bg-background px-2 py-1 text-xs';

function detachRef(featureId: number): ActionRef {
  return {
    backend: 'registry',
    challenge_instance_id: null,
    approach_id: null,
    technique_id: null,
    registry_key: 'gm_detach_feature',
    feature_id: featureId,
  };
}

/** A whole number from an input, or null when it is blank or not a number. */
function squareNumber(text: string): number | null {
  if (text.trim() === '') return null;
  const value = Number(text);
  return Number.isInteger(value) ? value : null;
}

export function GMFeatureControls({ sceneId, encounterId, characterId }: GMFeatureControlsProps) {
  const { data: encounter } = useCombatEncounter(encounterId);
  const { data: actions } = useAvailableActionsQuery(characterId);
  const attach = (actions?.results ?? []).find(
    (a) => a.ref.backend === 'registry' && a.ref.registry_key === 'gm_attach_feature'
  );
  const { data: featureTypes = [], isError: featureTypesFailed } = useFeatureTypes(
    attach !== undefined
  );
  const { mutateAsync: dispatchAction, isPending } = useDispatchPlayerAction(characterId);
  const queryClient = useQueryClient();

  const [placeId, setPlaceId] = useState('');
  const [typeId, setTypeId] = useState('');
  const [squareX, setSquareX] = useState('');
  const [squareY, setSquareY] = useState('');

  if (!attach || !encounter) return null;
  const places = encounter.position_nodes ?? [];
  if (places.length === 0) return null;

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) }).catch(() => {});
    queryClient.invalidateQueries({ queryKey: sceneKeys.detail(sceneId) }).catch(() => {});
    queryClient
      .invalidateQueries({ queryKey: availableActionsKeys.forCharacter(characterId) })
      .catch(() => {});
  };

  const send = (request: DispatchActionRequest, onDone?: () => void) => {
    dispatchAction(request)
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Refused.');
          return;
        }
        if (result.message) toast.success(result.message);
        onDone?.();
        refresh();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Failed.');
      });
  };

  const x = squareNumber(squareX);
  const y = squareNumber(squareY);
  // A square is both numbers or neither.
  const squareOk = (squareX.trim() === '' && squareY.trim() === '') || (x !== null && y !== null);
  const canAdd = placeId !== '' && typeId !== '' && squareOk && !isPending;

  const handleAdd = () => {
    const kwargs: Record<string, number> = {
      position_id: Number(placeId),
      feature_type_id: Number(typeId),
    };
    if (x !== null && y !== null) {
      kwargs.square_x = x;
      kwargs.square_y = y;
    }
    send({ ref: attach.ref, kwargs }, () => {
      setSquareX('');
      setSquareY('');
    });
  };

  const placed = places.flatMap((place) =>
    (place.features ?? []).map((feature) => ({ place, feature }))
  );

  return (
    <div className="space-y-2" data-testid="gm-feature-controls">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Features
      </p>
      <select
        aria-label="Place"
        className={SELECT_CLASS}
        value={placeId}
        onChange={(e) => setPlaceId(e.target.value)}
      >
        <option value="">Place</option>
        {places.map((place) => (
          <option key={place.id} value={place.id}>
            {place.name}
          </option>
        ))}
      </select>
      {featureTypesFailed && (
        <p role="alert" className="text-xs text-destructive">
          Feature types could not be loaded.
        </p>
      )}
      <select
        aria-label="Feature"
        className={SELECT_CLASS}
        value={typeId}
        onChange={(e) => setTypeId(e.target.value)}
      >
        <option value="">Feature</option>
        {featureTypes.map((type) => (
          <option key={type.id} value={type.id}>
            {type.name}
          </option>
        ))}
      </select>
      <div className="flex items-center gap-2">
        <input
          aria-label="Square x"
          inputMode="numeric"
          placeholder="x"
          className={`${SELECT_CLASS} w-16`}
          value={squareX}
          onChange={(e) => setSquareX(e.target.value)}
        />
        <input
          aria-label="Square y"
          inputMode="numeric"
          placeholder="y"
          className={`${SELECT_CLASS} w-16`}
          value={squareY}
          onChange={(e) => setSquareY(e.target.value)}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={!canAdd}
          onClick={handleAdd}
        >
          Add feature
        </Button>
      </div>
      {placed.length > 0 && (
        <ul className="space-y-1">
          {placed.map(({ place, feature }) => (
            <li
              key={feature.id}
              className="flex items-center justify-between gap-2 text-xs"
              data-testid={`gm-feature-${feature.id}`}
            >
              <span>
                {feature.name} · {place.name}
              </span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={`Remove ${feature.name} from ${place.name}`}
                disabled={isPending}
                onClick={() => send({ ref: detachRef(feature.id), kwargs: {} })}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
