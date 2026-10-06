import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MapPin } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { TargetMenu } from '@/game/target-menu/TargetMenu';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { fetchPlaces, joinPlace, leavePlace } from '../actionQueries';
import type { Place } from '../actionTypes';

interface Props {
  sceneId: string;
  /** Active `/game` viewer key; omitted for legacy SceneDetailPage. */
  character?: string;
  currentPlaceId?: number | null;
  actorId?: number | null;
  accountId?: number | null;
}

export function PlaceBar({
  sceneId,
  character,
  currentPlaceId = null,
  actorId: suppliedActorId,
  accountId: suppliedAccountId,
}: Props) {
  const [localPlaceId, setLocalPlaceId] = useState<number | null>(null);
  const controlled = character !== undefined;
  const selectedPlaceId = controlled ? currentPlaceId : localPlaceId;
  const queryClient = useQueryClient();
  const storeAccountId = useAppSelector((state) => state.auth.account?.id ?? null);
  const accountId = suppliedAccountId ?? storeAccountId;
  const activeCharacter = useAppSelector((state) => state.game.active);
  const { data: roster = [] } = useMyRosterEntriesQuery();
  const actorId =
    suppliedActorId ??
    (character === undefined
      ? roster.find((entry) => entry.name === activeCharacter)?.character_id
      : null) ??
    null;

  const { data, isLoading } = useQuery({
    queryKey: ['scene-places', sceneId, ...(character ? [character] : [])],
    queryFn: () => fetchPlaces(sceneId),
  });

  const join = useMutation({
    mutationFn: (placeId: number) => joinPlace(sceneId, placeId),
    onSuccess: (_data, placeId) => {
      if (!controlled) setLocalPlaceId(placeId);
      // 2026-07 audit: 'scene-messages' matched no query anywhere — the feed's
      // real key is 'scene-interactions' (useSceneInteractions).
      queryClient.invalidateQueries({
        queryKey: ['scene-interactions', sceneId, ...(character ? [character] : [])],
        exact: true,
      });
    },
  });

  const leave = useMutation({
    mutationFn: (placeId: number) => leavePlace(sceneId, placeId),
    onSuccess: () => {
      if (!controlled) setLocalPlaceId(null);
      // 2026-07 audit: 'scene-messages' matched no query anywhere — the feed's
      // real key is 'scene-interactions' (useSceneInteractions).
      queryClient.invalidateQueries({
        queryKey: ['scene-interactions', sceneId, ...(character ? [character] : [])],
        exact: true,
      });
    },
  });

  const places = data?.results ?? [];

  if (isLoading || places.length === 0) return null;

  function handlePlaceClick(place: Place) {
    if (selectedPlaceId === place.id) {
      leave.mutate(place.id);
    } else {
      join.mutate(place.id);
    }
  }

  return (
    <div className="flex items-center gap-2 border-b px-2 py-1.5">
      <MapPin className="h-4 w-4 shrink-0 text-muted-foreground" />
      <span className="text-xs font-medium text-muted-foreground">Places:</span>
      <div className="flex gap-1">
        {places.map((place) => {
          const isCurrent = selectedPlaceId === place.id;
          return (
            <TargetMenu
              key={place.id}
              partition={accountId === null ? '' : `account-${accountId}`}
              actorId={actorId}
              target={{ kind: 'places', target_id: place.id }}
            >
              <Button
                size="sm"
                variant={isCurrent ? 'default' : 'ghost'}
                className={isCurrent ? 'underline underline-offset-2' : ''}
                onClick={() => handlePlaceClick(place)}
                disabled={join.isPending || leave.isPending}
                title={place.description}
              >
                {place.name}
              </Button>
            </TargetMenu>
          );
        })}
      </div>
    </div>
  );
}
