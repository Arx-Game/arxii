/**
 * Focus stack hook for the right-sidebar drill navigation.
 *
 * Maintains a LIFO stack of "what am I currently focusing on" entries:
 *   - room (the default / root focus)
 *   - character (when drilling into a character to inspect them)
 *   - item (when drilling into a worn or carried item from a character view)
 *
 * The bottom of the stack is always preserved — `pop` is a no-op at depth 1
 * so the UI always has *something* to render. Use `reset(entry)` to swap the
 * root focus (e.g. when the player moves rooms).
 */

import { useCallback, useState } from 'react';

import type { RoomStatePayload, SceneSummary } from '@/hooks/types';

export type FocusEntry =
  | {
      kind: 'room';
      room: RoomStatePayload['room'];
      sceneSummary: SceneSummary | null;
    }
  | { kind: 'character'; character: { id: number; name: string } }
  | { kind: 'item'; item: { id: number; name: string } };

export interface FocusStackApi {
  current: FocusEntry;
  depth: number;
  push: (entry: FocusEntry) => void;
  pop: () => void;
  reset: (entry: FocusEntry) => void;
}

export function useFocusStack(initial: FocusEntry): FocusStackApi {
  const [stack, setStack] = useState<FocusEntry[]>([initial]);

  const push = useCallback((entry: FocusEntry) => {
    setStack((s) => [...s, entry]);
  }, []);

  const pop = useCallback(() => {
    setStack((s) => (s.length > 1 ? s.slice(0, -1) : s));
  }, []);

  const reset = useCallback((entry: FocusEntry) => {
    setStack([entry]);
  }, []);

  return {
    current: stack[stack.length - 1],
    depth: stack.length,
    push,
    pop,
    reset,
  };
}
