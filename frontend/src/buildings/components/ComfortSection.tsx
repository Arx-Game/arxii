import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { useRoomComfortQuery } from '../queries';
import type { RoomBuilderActionKey } from '../types';

interface ComfortSectionProps {
  roomId: number;
  characterId: number;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

/**
 * The owner build-HUD (#1514): per-axis pressure vs mitigation vs residual,
 * placed fixtures, and the add-fixture picker — "COLD +6, −4 (hearth) = +2;
 * add insulation."
 */
export function ComfortSection({ roomId, characterId, runAction }: ComfortSectionProps) {
  const comfort = useRoomComfortQuery(roomId, characterId);
  const [pendingKind, setPendingKind] = useState('');

  if (comfort.isLoading) {
    return <p className="text-xs text-muted-foreground">Reading the room's comfort…</p>;
  }
  if (comfort.isError || !comfort.data) {
    return null;
  }
  const data = comfort.data;
  const bitingAxes = data.axes.filter(
    (axis) => axis.pressure > 0 || axis.mitigation > 0 || axis.sheltered
  );

  return (
    <div className="flex flex-col gap-2" data-testid="comfort-section">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold">Comfort</h4>
        <Badge variant={data.level >= 5 ? 'secondary' : 'destructive'}>Level {data.level}</Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        Enclosure: {data.enclosure.replace('_', ' ')} · Amenity +{data.amenity}
      </p>
      {bitingAxes.length === 0 && (
        <p className="text-xs text-muted-foreground">Nothing bites here.</p>
      )}
      {bitingAxes.map((axis) => (
        <div key={axis.key} className="flex items-center justify-between text-xs">
          <span className="uppercase tracking-wide">{axis.key}</span>
          <span>
            +{axis.pressure} − {axis.mitigation}
            {axis.sheltered ? ' (sheltered)' : ''} ={' '}
            <span className={axis.net > 0 ? 'font-semibold text-destructive' : ''}>
              {axis.net} residual
            </span>
          </span>
        </div>
      ))}

      <h5 className="mt-1 text-xs font-semibold">Fixtures</h5>
      {data.fixtures.length === 0 && (
        <p className="text-xs text-muted-foreground">No fixtures placed.</p>
      )}
      {data.fixtures.map((fixture) => (
        <div key={fixture.id} className="flex items-center justify-between text-xs">
          <span>{fixture.kind}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              runAction('remove_room_fixture', { room_id: roomId, kind: fixture.kind })
            }
          >
            ✕
          </Button>
        </div>
      ))}
      <div className="flex items-center gap-1.5">
        <Select value={pendingKind} onValueChange={setPendingKind}>
          <SelectTrigger className="h-8 flex-1">
            <SelectValue placeholder="Add a fixture…" />
          </SelectTrigger>
          <SelectContent>
            {data.fixture_kinds.map((kind) => (
              <SelectItem key={kind.id} value={kind.name}>
                {kind.name}
                {kind.affinities.length > 0 &&
                  ` (${kind.affinities
                    .map((affinity) => `${affinity.value} ${affinity.key}`)
                    .join(', ')})`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="outline"
          disabled={!pendingKind}
          onClick={() => {
            runAction('place_room_fixture', { room_id: roomId, kind: pendingKind });
            setPendingKind('');
          }}
        >
          Place
        </Button>
      </div>
    </div>
  );
}
