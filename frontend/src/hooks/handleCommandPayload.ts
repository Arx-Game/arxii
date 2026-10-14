import type { CommandSpec } from '@/game/types';
import type { MyRosterEntry } from '@/roster/types';
import { store } from '@/store/store';
import { setSessionCommands } from '@/store/gameSlice';

/**
 * The `commands` frame: the web-form descriptors are its args, and every name the
 * character can type a command by rides its kwargs as `names` (#4346). A frame with
 * no list (the unpuppet frame clears both) leaves the character with none.
 */
export function handleCommandPayload(
  character: MyRosterEntry['name'],
  commands: CommandSpec[],
  kwargs?: Record<string, unknown>
) {
  // Backend already sends CommandSpec format, no conversion needed
  const names = kwargs?.names;
  const commandNames = Array.isArray(names)
    ? names.filter((name): name is string => typeof name === 'string')
    : [];
  store.dispatch(setSessionCommands({ character, commands, commandNames }));
}
