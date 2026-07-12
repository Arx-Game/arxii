/**
 * BattleMapPage — the strategic battle map (#2009).
 *
 * Route: /scenes/:id/battle
 *
 * Layout mirrors the `grid-cols-[1fr_360px]` C-frame shell CombatRail uses
 * on /scenes/:id (#2197; formerly the now-deleted CombatScenePage's own
 * route): a header (battle name/round/per-side victory points) over the
 * grid — the React Flow canvas on the left, the selected place's detail
 * panel on the right.
 *
 * A Scene has at most one Battle (useBattleForSceneQuery, Task 3's 1:1
 * lookup); once resolved, useBattleDetailQuery fetches the full aggregate
 * (sides/places/units/participants) the canvas and panel both read from.
 */

import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { cn } from '@/lib/utils';

import { BattleMapCanvas } from '../components/BattleMapCanvas';
import { PlaceDetailPanel } from '../components/PlaceDetailPanel';
import { StagingPanel } from '../components/StagingPanel';
import { useBattleDetailQuery, useBattleForSceneQuery } from '../queries';
import type { BattleRoundSummary } from '../types';

export function BattleMapPage() {
  const { id = '' } = useParams();
  const sceneId = Number(id);
  const sceneIdValid = id !== '' && !Number.isNaN(sceneId);

  const [selectedPlaceId, setSelectedPlaceId] = useState<number | null>(null);

  const {
    data: battle,
    isLoading: battleLoading,
    isError: battleErrored,
  } = useBattleForSceneQuery(sceneIdValid ? sceneId : null);

  const {
    data: detail,
    isLoading: detailLoading,
    isError: detailErrored,
  } = useBattleDetailQuery(battle?.id ?? null);

  if (!sceneIdValid) {
    return (
      <div className="p-4 text-sm text-destructive" data-testid="battle-map-invalid-scene">
        Invalid scene.
      </div>
    );
  }

  if (battleLoading) {
    return (
      <div className="p-4 text-sm text-muted-foreground" data-testid="battle-map-loading">
        Loading battle…
      </div>
    );
  }

  if (battleErrored) {
    return (
      <div className="p-4 text-sm text-destructive" data-testid="battle-map-error">
        Failed to load the battle for this scene.
      </div>
    );
  }

  if (!battle) {
    return (
      <div className="p-6" data-testid="battle-map-empty">
        <p className="text-center text-sm text-muted-foreground">No battle for this scene.</p>
        <div className="mx-auto mt-4 max-w-sm">
          <StagingPanel sceneId={sceneId} battle={null} detail={null} />
        </div>
      </div>
    );
  }

  if (detailErrored) {
    return (
      <div className="p-4 text-sm text-destructive" data-testid="battle-map-detail-error">
        Failed to load the battle map.
      </div>
    );
  }

  if (detailLoading || !detail) {
    return (
      <div className="p-4 text-sm text-muted-foreground" data-testid="battle-map-detail-loading">
        Loading battle map…
      </div>
    );
  }

  const round = detail.round as BattleRoundSummary | null;
  const selectedPlace = detail.places.find((place) => place.id === selectedPlaceId) ?? null;

  return (
    <div className="flex h-full flex-col" data-testid="battle-map-page">
      <div className="shrink-0 px-4 pt-4" data-testid="battle-map-header">
        <h2 className="text-lg font-semibold text-foreground">{detail.name}</h2>
        <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
          <span data-testid="battle-map-round">
            {round ? `Round ${round.number} (${round.status})` : 'No active round'}
          </span>
          {detail.sides.map((side) => (
            <span key={side.id} data-testid="battle-map-side-vp">
              {side.covenant_name ?? side.role ?? 'Side'}: {side.victory_points ?? 0}/
              {side.victory_threshold ?? 0} VP
            </span>
          ))}
        </div>
      </div>

      <div
        className={cn('grid min-h-0 flex-1 grid-cols-[1fr_360px] gap-4 px-4 pb-4')}
        data-testid="battle-map-grid"
      >
        <div className="min-h-0" data-testid="battle-map-canvas-column">
          <BattleMapCanvas
            detail={detail}
            selectedPlaceId={selectedPlaceId}
            onSelectPlace={setSelectedPlaceId}
          />
        </div>
        <div className="min-h-0 space-y-4 overflow-y-auto" data-testid="battle-map-panel-column">
          <StagingPanel sceneId={sceneId} battle={battle} detail={detail} />
          <PlaceDetailPanel
            place={selectedPlace}
            sides={detail.sides}
            units={detail.units}
            participants={detail.participants}
          />
        </div>
      </div>
    </div>
  );
}
