import { useState, useMemo, useCallback } from 'react';
import type { Interaction } from '../types';

export interface Thread {
  key: string;
  type: 'room' | 'place' | 'whisper' | 'target';
  label: string;
  participantPersonas: Array<{ id: number; name: string }>;
  latestTimestamp: string;
  unreadCount: number;
}

export interface ThreadingState {
  threads: Thread[];
  filteredInteractions: Interaction[];
  selectedThreadKey: string;
  enabledThreadKeys: Set<string>;
  hiddenPersonaIds: Map<string, Set<number>>;
  setSelectedThread: (key: string) => void;
  toggleThreadVisibility: (key: string) => void;
  showAll: () => void;
  togglePersonaHidden: (threadKey: string, personaId: number) => void;
  getHiddenPersonaIds: (threadKey: string) => Set<number>;
}

export function getThreadKey(interaction: Interaction): string {
  if (interaction.mode === 'whisper' && interaction.receiver_persona_ids.length > 0) {
    const ids = [interaction.persona.id, ...interaction.receiver_persona_ids].sort((a, b) => a - b);
    return `whisper:${ids.join(',')}`;
  }
  if (interaction.place != null) {
    return `place:${interaction.place}`;
  }
  if (interaction.target_persona_ids.length > 0) {
    const ids = [...interaction.target_persona_ids].sort((a, b) => a - b);
    return `target:${ids.join(',')}`;
  }
  return 'room';
}

function getParticipantPersonas(interactions: Interaction[]): Array<{ id: number; name: string }> {
  const seen = new Map<number, string>();
  for (const interaction of interactions) {
    if (!seen.has(interaction.persona.id)) {
      seen.set(interaction.persona.id, interaction.persona.name);
    }
  }
  return [...seen.entries()].map(([id, name]) => ({ id, name }));
}

function formatPersonaNames(personas: Array<{ name: string }>): string {
  if (personas.length <= 3) return personas.map((p) => p.name).join(', ');
  return `${personas
    .slice(0, 3)
    .map((p) => p.name)
    .join(', ')}...`;
}

function getThreadLabel(
  _key: string,
  type: string,
  interactions: Interaction[],
  roomName: string
): string {
  if (type === 'room') return roomName;
  if (type === 'place') {
    const first = interactions.find((i) => i.place_name);
    return first?.place_name ?? 'Place';
  }
  if (type === 'whisper') {
    const personas = getParticipantPersonas(interactions);
    return `Whisper: ${formatPersonaNames(personas)}`;
  }
  const personas = getParticipantPersonas(interactions);
  return formatPersonaNames(personas);
}

export function useThreading(interactions: Interaction[], roomName: string): ThreadingState {
  const [selectedThreadKey, setSelectedThread] = useState('room');
  const [enabledThreadKeys, setEnabledThreadKeys] = useState<Set<string>>(new Set());
  const [hiddenPersonaIds, setHiddenPersonaIds] = useState<Map<string, Set<number>>>(new Map());
  const isUnfiltered = enabledThreadKeys.size === 0;

  const { threads, threadKeyMap } = useMemo(() => {
    const groups = new Map<string, Interaction[]>();
    const keyMap = new Map<number, string>();
    for (const interaction of interactions) {
      const key = getThreadKey(interaction);
      keyMap.set(interaction.id, key);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(interaction);
    }
    const threadList = [...groups.entries()]
      .map(([key, threadInteractions]) => {
        const type: Thread['type'] =
          key === 'room'
            ? 'room'
            : key.startsWith('place:')
              ? 'place'
              : key.startsWith('whisper:')
                ? 'whisper'
                : 'target';
        return {
          key,
          type,
          label: getThreadLabel(key, type, threadInteractions, roomName),
          participantPersonas: getParticipantPersonas(threadInteractions),
          latestTimestamp: threadInteractions[threadInteractions.length - 1]?.timestamp ?? '',
          unreadCount: 0, // TODO: track per-thread unread count (needs last-viewed timestamp per thread)
        } as Thread;
      })
      .sort((a, b) => {
        if (a.type === 'room') return -1;
        if (b.type === 'room') return 1;
        return b.latestTimestamp.localeCompare(a.latestTimestamp);
      });
    return { threads: threadList, threadKeyMap: keyMap };
  }, [interactions, roomName]);

  const filteredInteractions = useMemo(() => {
    // Fast path: no thread filter and no hidden personas — return interactions as-is (Fix #6)
    if (isUnfiltered && hiddenPersonaIds.size === 0) {
      return interactions;
    }

    let filtered = interactions;

    if (!isUnfiltered) {
      filtered = filtered.filter((i) => {
        const key = threadKeyMap.get(i.id) ?? getThreadKey(i);
        return enabledThreadKeys.has(key);
      });
    }

    if (hiddenPersonaIds.size > 0) {
      filtered = filtered.filter((i) => {
        const threadKey = threadKeyMap.get(i.id) ?? getThreadKey(i);
        const hidden = hiddenPersonaIds.get(threadKey);
        if (hidden && hidden.has(i.persona.id)) return false;
        return true;
      });
    }

    return filtered;
  }, [interactions, enabledThreadKeys, hiddenPersonaIds, isUnfiltered, threadKeyMap]);

  const toggleThreadVisibility = useCallback((key: string) => {
    setEnabledThreadKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
    setSelectedThread(key);
  }, []);

  const showAll = useCallback(() => {
    setEnabledThreadKeys(new Set());
    setSelectedThread('room');
  }, []);

  const togglePersonaHidden = useCallback((threadKey: string, personaId: number) => {
    setHiddenPersonaIds((prev) => {
      const next = new Map(prev);
      const set = new Set(next.get(threadKey) ?? []);
      if (set.has(personaId)) {
        set.delete(personaId);
      } else {
        set.add(personaId);
      }
      next.set(threadKey, set);
      return next;
    });
  }, []);

  const getHiddenPersonaIds = useCallback(
    (threadKey: string) => {
      return hiddenPersonaIds.get(threadKey) ?? new Set<number>();
    },
    [hiddenPersonaIds]
  );

  return {
    threads,
    filteredInteractions,
    selectedThreadKey,
    enabledThreadKeys,
    hiddenPersonaIds,
    setSelectedThread,
    toggleThreadVisibility,
    showAll,
    togglePersonaHidden,
    getHiddenPersonaIds,
  };
}
