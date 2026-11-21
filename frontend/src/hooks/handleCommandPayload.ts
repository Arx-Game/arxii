import type { MyRosterEntry } from '@/roster/types';
import { store } from '@/store/store';
import { setSessionCommandNames } from '@/store/gameSlice';

/**
 * The `commands` frame: every name the character can type a command by rides its
 * kwargs as `names` (#4346). A frame with no list (the unpuppet frame clears it)
 * leaves the character with none. The frame's args are the server's per-command
 * web-form descriptors; the client does not render forms for telnet commands
 * (ADR-4034), so it ignores them.
 */
export function handleCommandPayload(
  character: MyRosterEntry['name'],
  kwargs?: Record<string, unknown>
) {
  const names = kwargs?.names;
  const commandNames = Array.isArray(names)
    ? names.filter((name): name is string => typeof name === 'string')
    : [];
  store.dispatch(setSessionCommandNames({ character, commandNames }));
}
