import type { CommandSpec } from '@/game/types';
import type { MyRosterEntry } from '@/roster/types';
import { store } from '@/store/store';
import { setSessionCommands } from '@/store/gameSlice';

export function handleCommandPayload(character: MyRosterEntry['name'], commands: CommandSpec[]) {
  // Backend already sends CommandSpec format, no conversion needed
  store.dispatch(setSessionCommands({ character, commands }));
}
