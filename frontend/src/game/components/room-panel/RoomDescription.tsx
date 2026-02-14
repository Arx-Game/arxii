import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface RoomDescriptionProps {
  description: string;
}

export function RoomDescription({ description }: RoomDescriptionProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b px-3 py-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-1 text-xs font-semibold uppercase text-muted-foreground"
      >
        {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        Description
      </button>
      {expanded && (
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
      )}
    </div>
  );
}
