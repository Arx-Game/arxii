import type { CommandSpec } from '@/game/types';
import { store } from '@/store/store';
import { setSessionCommands } from '@/store/gameSlice';

export function handleCommandPayload(character: string, commands: CommandSpec[]) {
  // Backend already sends CommandSpec format, no conversion needed
  store.dispatch(setSessionCommands({ character, commands }));
}
