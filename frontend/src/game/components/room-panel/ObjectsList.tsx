import { useState } from 'react';
import { ChevronDown, ChevronRight, Package } from 'lucide-react';
import { toast } from 'sonner';

import type { RoomStateObject } from '@/hooks/types';
import { Button } from '@/components/ui/button';
import { FormattedContent } from '@/components/FormattedContent';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { dbrefToId } from '@/lib/dbref';
import { MissionBoardDialog } from '@/missions/components/MissionBoardDialog';

interface ObjectsListProps {
  objects: RoomStateObject[];
  /** The active puppet's ObjectDB pk — required to dispatch examine (#3044). */
  characterId?: number | null;
}

/**
 * Room objects panel (#3044). Rows expand on click to dispatch `look` through
 * the same `action.run()` seam telnet's `CmdLook` uses — the object's own
 * `maybe_dispatch_on_examine`/mission hooks fire identically to telnet, and
 * the returned description renders in place. A row flagged `is_mission_board`
 * (an object with an active BOARD-kind MissionGiver, #2044) also gets a
 * "View Board" button opening `MissionBoardDialog` — the notice-board front
 * door, kept separate from plain examine so taking a posting doesn't require
 * parsing free text out of the description.
 */
export function ObjectsList({ objects, characterId }: ObjectsListProps) {
  const [expandedDbref, setExpandedDbref] = useState<string | null>(null);
  const [examineText, setExamineText] = useState<Record<string, string>>({});
  const [boardDbref, setBoardDbref] = useState<string | null>(null);
  const { mutate: dispatchLook, isPending } = useDispatchPlayerAction(characterId ?? 0);

  if (objects.length === 0) return null;

  const boardObject = objects.find((obj) => obj.dbref === boardDbref) ?? null;

  const handleToggle = (obj: RoomStateObject) => {
    const nowOpen = expandedDbref !== obj.dbref;
    setExpandedDbref(nowOpen ? obj.dbref : null);
    if (!nowOpen || examineText[obj.dbref] !== undefined || characterId == null) {
      return;
    }
    dispatchLook(
      {
        ref: { backend: 'registry', registry_key: 'look' },
        kwargs: { target: dbrefToId(obj.dbref) },
      },
      {
        onSuccess: (result) => {
          if (isDispatchFailure(result)) {
            toast.error(result.message ?? `Couldn't examine ${obj.name}.`);
            return;
          }
          setExamineText((prev) => ({ ...prev, [obj.dbref]: result.message ?? '' }));
        },
        onError: () => toast.error(`Couldn't examine ${obj.name}.`),
      }
    );
  };

  return (
    <div className="px-3 py-2">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <Package className="h-3 w-3" />
        Objects ({objects.length})
      </div>
      <ul className="space-y-1">
        {objects.map((obj) => {
          const isExpanded = expandedDbref === obj.dbref;
          return (
            <li key={obj.dbref} className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="flex flex-1 items-center gap-2 text-left"
                  onClick={() => handleToggle(obj)}
                  data-testid={`examine-toggle-${obj.dbref}`}
                >
                  {isExpanded ? (
                    <ChevronDown className="h-3 w-3 shrink-0" />
                  ) : (
                    <ChevronRight className="h-3 w-3 shrink-0" />
                  )}
                  {obj.thumbnail_url ? (
                    <img
                      src={obj.thumbnail_url}
                      alt={obj.name}
                      className="h-5 w-5 rounded object-cover"
                    />
                  ) : (
                    <div className="h-5 w-5 shrink-0 rounded bg-muted" />
                  )}
                  <span className="text-xs">{obj.name}</span>
                </button>
                {obj.is_mission_board ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-6 shrink-0 px-2 text-xs"
                    onClick={() => setBoardDbref(obj.dbref)}
                    data-testid={`open-board-${obj.dbref}`}
                  >
                    View Board
                  </Button>
                ) : null}
              </div>
              {isExpanded ? (
                <div
                  className="ml-5 whitespace-pre-wrap text-xs text-muted-foreground"
                  data-testid={`examine-text-${obj.dbref}`}
                >
                  {examineText[obj.dbref] === undefined ? (
                    isPending ? (
                      'Looking…'
                    ) : (
                      'Cannot examine right now.'
                    )
                  ) : (
                    <FormattedContent content={examineText[obj.dbref]} />
                  )}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {boardObject ? (
        <MissionBoardDialog
          boardObjectId={dbrefToId(boardObject.dbref)}
          boardName={boardObject.name}
          open
          onOpenChange={(next) => {
            if (!next) setBoardDbref(null);
          }}
        />
      ) : null}
    </div>
  );
}
