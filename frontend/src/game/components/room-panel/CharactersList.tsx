import { Users } from 'lucide-react';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import type { RoomStateObject } from '@/hooks/types';

interface CharactersListProps {
  characters: RoomStateObject[];
  onCharacterClick?: (character: RoomStateObject) => void;
}

export function CharactersList({ characters, onCharacterClick }: CharactersListProps) {
  return (
    <div className="border-b px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <Users className="h-3 w-3" />
        Characters ({characters.length})
      </div>
      {characters.length > 0 ? (
        <ul className="space-y-1">
          {characters.map((char) => {
            const content = (
              <>
                <Avatar className="h-5 w-5">
                  {char.thumbnail_url ? (
                    <AvatarImage src={char.thumbnail_url} alt={char.name} />
                  ) : null}
                  <AvatarFallback className="text-[8px]">
                    {char.name.slice(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <span className="text-xs">{char.name}</span>
              </>
            );

            return (
              <li key={char.dbref}>
                {onCharacterClick ? (
                  <button
                    type="button"
                    onClick={() => onCharacterClick(char)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-1 py-0.5 text-left',
                      'transition-colors hover:bg-accent focus-visible:outline-none',
                      'focus-visible:ring-2 focus-visible:ring-ring'
                    )}
                  >
                    {content}
                  </button>
                ) : (
                  <div className="flex items-center gap-2">{content}</div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-xs text-muted-foreground">Nobody else here.</p>
      )}
    </div>
  );
}
