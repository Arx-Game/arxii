import { useGossipActionMutation, useGossipQuery } from '../queries';

/** The gossip panel (#1572): work the rumor mill at a social hub — the web face of the telnet
 * `gossip` command. Lists the Level-1 secrets the active character could spread (with their heat in
 * the current region), and offers seek / spread / quiet. Gossip is per active character and
 * location-bound (you must be at a social hub); the services enforce the Gossip-skill + hub gates
 * and surface a message when they aren't met. `viewerId` is the active RosterEntry pk, or null. */
export function GossipPanel({ viewerId }: { viewerId: number | null }) {
  const { data, isLoading, isError } = useGossipQuery(viewerId);
  const action = useGossipActionMutation();

  if (viewerId === null) {
    return <p className="text-muted-foreground">Select a character to work the rumor mill.</p>;
  }
  if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (isError) return <p className="text-destructive">Failed to load gossip.</p>;

  const secrets = data ?? [];
  const overheard = action.isSuccess ? action.data : undefined;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Rumors you could spread at this hub.</p>
        <button
          type="button"
          disabled={action.isPending}
          className="rounded border px-2 py-1 text-sm hover:bg-accent disabled:opacity-50"
          onClick={() => action.mutate({ action: 'seek', viewer: viewerId })}
        >
          Listen for gossip
        </button>
      </div>

      {action.isError && (
        <p className="text-sm text-destructive">{(action.error as Error).message}</p>
      )}
      {overheard?.content && (
        <p className="rounded-md border border-dashed p-2 text-sm italic">
          You overhear a rumor: {overheard.content}
        </p>
      )}

      {secrets.length === 0 ? (
        <p className="text-muted-foreground">You hold no idle gossip worth spreading.</p>
      ) : (
        secrets.map((secret) => (
          <div key={secret.id} className="space-y-1 rounded-md border p-3">
            <p>{secret.content}</p>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">Heat here: {secret.heat}</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={action.isPending}
                  className="rounded border px-2 py-1 text-sm hover:bg-accent disabled:opacity-50"
                  onClick={() =>
                    action.mutate({ action: 'plant', viewer: viewerId, secret: secret.id })
                  }
                >
                  Spread
                </button>
                <button
                  type="button"
                  disabled={action.isPending}
                  className="rounded border px-2 py-1 text-sm hover:bg-accent disabled:opacity-50"
                  onClick={() =>
                    action.mutate({ action: 'suppress', viewer: viewerId, secret: secret.id })
                  }
                >
                  Quiet
                </button>
              </div>
            </div>
          </div>
        ))
      )}
    </div>
  );
}
