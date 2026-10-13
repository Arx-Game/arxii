import { useCallback } from 'react';

import { useGameSocket } from '@/hooks/useGameSocket';
import { useDisconnectEverywhereMutation } from '@/roster/queries';
import type { MyRosterEntry } from '@/roster/types';
import { useCharacterPresence } from '@/roster/useCharacterPresence';

export interface DisconnectCharacter {
  /**
   * The control offers "This connection" and "Every connection" (#4321): only
   * while this tab holds a socket AND the character has another session
   * somewhere. One session means there is nothing to choose; a tab with no
   * socket of its own has no "this connection" to close.
   */
  needsChoice: boolean;
  /** Close this tab's socket only; the server unpuppets when the last one goes. */
  disconnectThis: () => void;
  /** Ask the server to close every session on the character, this tab's included. */
  disconnectEverywhere: () => void;
  /** What a plain "Disconnect Character" press does when there is no choice to make. */
  disconnect: () => void;
}

/**
 * "Disconnect Character" from anywhere (#4321). With a local socket and a
 * single session it is `useGameSocket().disconnect(name)` exactly as before
 * (#3818): a normal close the server answers by unpuppeting. Without a local
 * socket it is the disconnect endpoint, which closes the sessions other tabs
 * or devices hold with the `quit` reason, so each of them leaves the world as
 * a typed `quit` does (`SERVER_QUIT_CLOSE_REASONS`). With both, the caller
 * draws the two choices and routes each here.
 *
 * Callers own what happens after a local close (the world menu goes to the
 * Hall; the chip stays put). After an everywhere close that includes this
 * tab's socket, the close handler in `useGameSocket` already does the rest.
 */
export function useDisconnectCharacter(entry: MyRosterEntry | null): DisconnectCharacter {
  const { hasLocalSocket, sessionCount } = useCharacterPresence(entry);
  const { disconnect: closeLocal } = useGameSocket();
  const { mutate: closeEverywhere } = useDisconnectEverywhereMutation();

  const disconnectThis = useCallback(() => {
    if (entry) closeLocal(entry.name);
  }, [closeLocal, entry]);

  const disconnectEverywhere = useCallback(() => {
    if (entry) closeEverywhere(entry.id);
  }, [closeEverywhere, entry]);

  const needsChoice = hasLocalSocket && sessionCount > 1;
  const disconnect = hasLocalSocket ? disconnectThis : disconnectEverywhere;
  return { needsChoice, disconnectThis, disconnectEverywhere, disconnect };
}
