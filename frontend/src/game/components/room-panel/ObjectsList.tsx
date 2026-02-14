import { Package } from 'lucide-react';
import type { RoomStateObject } from '@/hooks/types';

interface ObjectsListProps {
  objects: RoomStateObject[];
}

export function ObjectsList({ objects }: ObjectsListProps) {
  if (objects.length === 0) return null;

  return (
    <div className="px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <Package className="h-3 w-3" />
        Objects ({objects.length})
      </div>
      <ul className="space-y-1">
        {objects.map((obj) => (
          <li key={obj.dbref} className="flex items-center gap-2">
            {obj.thumbnail_url ? (
              <img
                src={obj.thumbnail_url}
                alt={obj.name}
                className="h-5 w-5 rounded object-cover"
              />
            ) : (
              <div className="h-5 w-5 rounded bg-muted" />
            )}
            <span className="text-xs">{obj.name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
