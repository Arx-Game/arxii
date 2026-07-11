import { useMemo } from 'react';
import { FormattedContent } from '@/components/FormattedContent';
import { usePresence } from '@/presence/queries';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';

/**
 * Right-sidebar "Who" tab (#1463): online presence for the web game view.
 *
 * - **Online** — every online character by active persona, with a *coarse* idle marker
 *   (active / idle / away; never exact, so identical idle times can't out alts).
 * - **Where** — characters in public rooms with their coloured area path (rendered through
 *   `FormattedContent`, which parses the Evennia colour codes the backend emits), plus a
 *   "Go there" affordance (#2163) that dispatches the `travel_to` registry action.
 */
export function PresencePanel() {
  const { data, isLoading, isError } = usePresence();

  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const { mutate, isPending } = useDispatchPlayerAction(characterId ?? 0);

  const dispatchTravel = (roomId: number) => {
    mutate({
      ref: { backend: 'registry', registry_key: 'travel_to' },
      kwargs: { target: roomId },
    });
  };

  if (isLoading) {
    return <div className="p-3 text-sm text-muted-foreground">Loading…</div>;
  }
  if (isError || !data) {
    return <div className="p-3 text-sm text-muted-foreground">Couldn&apos;t load presence.</div>;
  }

  return (
    <div className="flex flex-col gap-4 p-3 text-sm">
      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Online</h3>
        {data.who.length === 0 ? (
          <p className="text-muted-foreground">No one is online.</p>
        ) : (
          <ul className="space-y-0.5">
            {data.who.map((entry, i) => (
              <li key={`${entry.name}-${i}`} className="flex items-center justify-between gap-2">
                <span>{entry.name}</span>
                {entry.idle && <span className="text-xs text-muted-foreground">{entry.idle}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Where</h3>
        {data.where.length === 0 ? (
          <p className="text-muted-foreground">No one is out in public spaces.</p>
        ) : (
          <ul className="space-y-1">
            {data.where.map((entry, i) => (
              <li key={`${entry.persona_name}-${i}`}>
                <span className="font-medium">{entry.persona_name}</span>{' '}
                <span className="text-muted-foreground">— </span>
                <FormattedContent content={entry.room_path} />
                <button
                  type="button"
                  className="ml-2 text-xs text-blue-600 hover:underline"
                  onClick={() => dispatchTravel(entry.room_id)}
                  disabled={isPending}
                  data-testid={`go-there-where-${i}`}
                >
                  Go there
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
