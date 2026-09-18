/**
 * The gossip panel (#1572): work the rumor mill at a social hub — the web face of the telnet
 * `gossip` command. Lists the Level-1 secrets the active character could spread (with their heat in
 * the current region), and offers seek / spread / quiet. Gossip is per active character and
 * location-bound (you must be at a social hub); the services enforce the Gossip-skill + hub gates
 * and surface a message when they aren't met. `viewerId` is the active RosterEntry pk, or null.
 *
 * Drawn in the Reference Sheet's vocabulary (#3898): the three verbs are quiet doors under
 * each rumor rather than bordered buttons, and the rumors are entries on hairlines.
 */

import { useGossipActionMutation, useGossipQuery } from '../queries';
import {
  Entries,
  Entry,
  Ledger,
  QuietDoor,
  Stack,
} from '@/character_sheets/components/sheet/primitives';

export function GossipPanel({ viewerId }: { viewerId: number | null }) {
  const { data, isLoading, isError } = useGossipQuery(viewerId);
  const action = useGossipActionMutation();

  if (viewerId === null) {
    return <Ledger>Choose a character to work the rumor mill.</Ledger>;
  }
  if (isLoading) return <Ledger>Listening…</Ledger>;
  if (isError) {
    return (
      <p className="refsheet-ledger" style={{ color: 'hsl(var(--destructive))' }}>
        The rumor mill could not be read.
      </p>
    );
  }

  const secrets = data ?? [];
  const overheard = action.isSuccess ? action.data : undefined;

  return (
    <Stack>
      <Ledger>What you could put about, here and now.</Ledger>
      <div className="refsheet-doors">
        <QuietDoor
          disabled={action.isPending}
          onClick={() => action.mutate({ action: 'seek', viewer: viewerId })}
        >
          Listen for gossip
        </QuietDoor>
      </div>

      {action.isError && (
        <p className="refsheet-note" style={{ color: 'hsl(var(--destructive))' }}>
          {(action.error as Error).message}
        </p>
      )}
      {overheard?.content && (
        <p className="refsheet-soft italic">You overhear: {overheard.content}</p>
      )}

      {secrets.length === 0 ? (
        <Ledger>You hold no idle gossip worth spreading.</Ledger>
      ) : (
        <Entries>
          {secrets.map((secret) => (
            <Entry
              key={secret.id}
              name={secret.content}
              aside={<span className="refsheet-note">Heat {secret.heat}</span>}
            >
              <div className="refsheet-doors">
                <QuietDoor
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate({ action: 'plant', viewer: viewerId, secret: secret.id })
                  }
                >
                  Spread
                </QuietDoor>
                <QuietDoor
                  disabled={action.isPending}
                  onClick={() =>
                    action.mutate({ action: 'suppress', viewer: viewerId, secret: secret.id })
                  }
                >
                  Quiet
                </QuietDoor>
              </div>
            </Entry>
          ))}
        </Entries>
      )}
    </Stack>
  );
}
