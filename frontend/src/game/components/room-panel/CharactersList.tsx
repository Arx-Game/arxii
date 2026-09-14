import { Users } from 'lucide-react';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import type { RoomStateObject } from '@/hooks/types';
import { UnseenPresenceRow } from './UnseenPresenceRow';

interface CharactersListProps {
  characters: RoomStateObject[];
  /**
   * The viewing character (#3856), listed first with a "you" tag. The room
   * state's `characters` excludes the viewer, so this is supplied separately;
   * absent when no character is active.
   */
  viewer?: { name: string; thumbnailUrl: string | null } | null;
  /** Pressing the "you" row: the panel sends a look at yourself. */
  onViewerClick?: () => void;
  onCharacterClick?: (character: RoomStateObject) => void;
  /** #3288 — true when a concealed occupant is here; renders the identity-free row. */
  hasUnseenPresence?: boolean;
  /** The viewer's active persona pk, for the unseen-presence report affordance. */
  viewerPersonaId?: number | null;
}

export function CharactersList({
  characters,
  viewer = null,
  onViewerClick,
  onCharacterClick,
  hasUnseenPresence = false,
  viewerPersonaId = null,
}: CharactersListProps) {
  return (
    <div className="border-b px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <Users className="h-3 w-3" />
        Characters ({characters.length + (viewer ? 1 : 0)})
      </div>
      {viewer && (
        <ul className="mb-1 space-y-1">
          <li>
            <button
              type="button"
              onClick={onViewerClick}
              className={cn(
                'flex min-h-11 w-full items-center gap-2 rounded-md px-2 py-2 text-left',
                'transition-colors hover:bg-accent focus-visible:outline-none',
                'focus-visible:ring-2 focus-visible:ring-ring'
              )}
            >
              <Avatar className="h-5 w-5">
                {viewer.thumbnailUrl ? (
                  <AvatarImage src={viewer.thumbnailUrl} alt={viewer.name} />
                ) : null}
                <AvatarFallback className="text-[8px]">
                  {viewer.name.slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <span className="text-xs">{viewer.name}</span>
              {/* Plain uppercase text at the row's end, as the demo draws it; no chip. */}
              <span className="ml-auto text-[0.7rem] uppercase tracking-[0.06em] text-muted-foreground">
                you
              </span>
            </button>
          </li>
        </ul>
      )}
      {hasUnseenPresence && (
        <ul className="mb-1 space-y-1">
          <UnseenPresenceRow viewerPersonaId={viewerPersonaId} />
        </ul>
      )}
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
                      'flex min-h-11 w-full items-center gap-2 rounded-md px-2 py-2 text-left',
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
