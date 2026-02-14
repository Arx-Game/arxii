import { Users } from 'lucide-react';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import type { RoomStateObject } from '@/hooks/types';

interface CharactersListProps {
  characters: RoomStateObject[];
}

export function CharactersList({ characters }: CharactersListProps) {
  return (
    <div className="border-b px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <Users className="h-3 w-3" />
        Characters ({characters.length})
      </div>
      {characters.length > 0 ? (
        <ul className="space-y-1">
          {characters.map((char) => (
            <li key={char.dbref} className="flex items-center gap-2">
              <Avatar className="h-5 w-5">
                {char.thumbnail_url ? (
                  <AvatarImage src={char.thumbnail_url} alt={char.name} />
                ) : null}
                <AvatarFallback className="text-[8px]">
                  {char.name.slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <span className="text-xs">{char.name}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">Nobody else here.</p>
      )}
    </div>
  );
}
