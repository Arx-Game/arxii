import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { MapPin } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchPlaces, joinPlace, leavePlace } from '../actionQueries';
import type { Place } from '../actionTypes';

interface Props {
  sceneId: string;
}

export function PlaceBar({ sceneId }: Props) {
  const [currentPlaceId, setCurrentPlaceId] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['scene-places', sceneId],
    queryFn: () => fetchPlaces(sceneId),
  });

  const join = useMutation({
    mutationFn: (placeId: number) => joinPlace(sceneId, placeId),
    onSuccess: (_data, placeId) => {
      setCurrentPlaceId(placeId);
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
    },
  });

  const leave = useMutation({
    mutationFn: (placeId: number) => leavePlace(sceneId, placeId),
    onSuccess: () => {
      setCurrentPlaceId(null);
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
    },
  });

  const places = data?.results ?? [];

  if (isLoading || places.length === 0) return null;

  function handlePlaceClick(place: Place) {
    if (currentPlaceId === place.id) {
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
          const isCurrent = currentPlaceId === place.id;
          return (
            <Button
              key={place.id}
              size="sm"
              variant={isCurrent ? 'default' : 'ghost'}
              className={isCurrent ? 'underline underline-offset-2' : ''}
              onClick={() => handlePlaceClick(place)}
              disabled={join.isPending || leave.isPending}
              title={place.description}
            >
              {place.name}
            </Button>
          );
        })}
      </div>
    </div>
  );
}
