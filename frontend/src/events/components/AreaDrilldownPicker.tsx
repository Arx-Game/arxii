import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Loader2, MapPin } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchAreas, fetchAreaRooms } from '../queries';
import type { AreaListItem, AreaRoom } from '../types';

interface AreaDrilldownPickerProps {
  value: number | null;
  onChange: (roomProfileId: number | null) => void;
}

interface BreadcrumbItem {
  id: number;
  name: string;
}

export function AreaDrilldownPicker({ value, onChange }: AreaDrilldownPickerProps) {
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);
  const [selectedRoomName, setSelectedRoomName] = useState<string | null>(null);
  const currentParentId =
    breadcrumbs.length > 0 ? breadcrumbs[breadcrumbs.length - 1].id : undefined;

  const { data: areas = [], isLoading: areasLoading } = useQuery({
    queryKey: ['areas', currentParentId ?? 'root'],
    queryFn: () => fetchAreas(currentParentId),
  });

  // Fetch rooms when we've drilled into an area that has no child areas
  const shouldFetchRooms = currentParentId != null && !areasLoading && areas.length === 0;
  const { data: rooms = [], isLoading: roomsLoading } = useQuery({
    queryKey: ['area-rooms', currentParentId],
    queryFn: () => fetchAreaRooms(currentParentId!),
    enabled: shouldFetchRooms,
  });

  const drillInto = (area: AreaListItem) => {
    setBreadcrumbs((prev) => [...prev, { id: area.id, name: area.name }]);
  };

  const navigateTo = (index: number) => {
    setBreadcrumbs((prev) => prev.slice(0, index + 1));
  };

  const goToRoot = () => {
    setBreadcrumbs([]);
  };

  const selectRoom = (room: AreaRoom) => {
    setSelectedRoomName(room.name);
    onChange(room.id);
  };

  // Show selected state
  if (value && selectedRoomName) {
    return (
      <div className="flex items-center gap-2 rounded-md border p-2">
        <MapPin className="h-4 w-4 text-muted-foreground" />
        <span className="flex-1 text-sm">{selectedRoomName}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setSelectedRoomName(null);
            onChange(null);
          }}
        >
          Change
        </Button>
      </div>
    );
  }

  const isLoading = areasLoading || roomsLoading;

  return (
    <div className="rounded-md border">
      {/* Breadcrumbs */}
      {breadcrumbs.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 border-b px-3 py-2 text-sm">
          <button
            type="button"
            onClick={goToRoot}
            className="text-muted-foreground hover:text-foreground"
          >
            All
          </button>
          {breadcrumbs.map((crumb, idx) => (
            <span key={crumb.id} className="flex items-center gap-1">
              <ChevronRight className="h-3 w-3 text-muted-foreground" />
              <button
                type="button"
                onClick={() => navigateTo(idx)}
                className={
                  idx === breadcrumbs.length - 1
                    ? 'font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                }
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="max-h-64 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : shouldFetchRooms ? (
          rooms.length === 0 ? (
            <p className="px-3 py-4 text-center text-sm text-muted-foreground">
              No public rooms in this area.
            </p>
          ) : (
            rooms.map((room) => (
              <button
                key={room.id}
                type="button"
                onClick={() => selectRoom(room)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <MapPin className="h-4 w-4 text-muted-foreground" />
                <span>{room.name}</span>
              </button>
            ))
          )
        ) : areas.length === 0 ? (
          <p className="px-3 py-4 text-center text-sm text-muted-foreground">No areas found.</p>
        ) : (
          areas.map((area) => (
            <button
              key={area.id}
              type="button"
              onClick={() => drillInto(area)}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
            >
              <div>
                <span className="font-medium">{area.name}</span>
                <span className="ml-2 text-xs text-muted-foreground">{area.level_display}</span>
              </div>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                {area.children_count > 0 && <span>{area.children_count}</span>}
                <ChevronRight className="h-4 w-4" />
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
