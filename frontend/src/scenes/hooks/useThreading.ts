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
  activeThreadKey: string;
  visibleThreadKeys: Set<string>;
  hiddenPersonaIds: Map<string, Set<number>>;
  setActiveThread: (key: string) => void;
  toggleThreadVisibility: (key: string) => void;
  showAll: () => void;
  togglePersonaHidden: (threadKey: string, personaId: number) => void;
  getHiddenPersonaIds: (threadKey: string) => Set<number>;
}

export function getThreadKey(interaction: Interaction): string {
  if (interaction.mode === 'whisper' && interaction.receiver_persona_ids.length > 0) {
    const ids = [...interaction.receiver_persona_ids].sort((a, b) => a - b);
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
  const [activeThreadKey, setActiveThread] = useState('room');
  const [visibleThreadKeys, setVisibleThreadKeys] = useState<Set<string>>(new Set());
  const [hiddenPersonaIds, setHiddenPersonaIds] = useState<Map<string, Set<number>>>(new Map());
  const showingAll = visibleThreadKeys.size === 0;

  const threads = useMemo(() => {
    const groups = new Map<string, Interaction[]>();
    for (const interaction of interactions) {
      const key = getThreadKey(interaction);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(interaction);
    }
    return [...groups.entries()]
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
          unreadCount: 0,
        } as Thread;
      })
      .sort((a, b) => {
        if (a.type === 'room') return -1;
        if (b.type === 'room') return 1;
        return b.latestTimestamp.localeCompare(a.latestTimestamp);
      });
  }, [interactions, roomName]);

  const filteredInteractions = useMemo(() => {
    let filtered = interactions;

    if (!showingAll) {
      filtered = filtered.filter((i) => visibleThreadKeys.has(getThreadKey(i)));
    }

    filtered = filtered.filter((i) => {
      const threadKey = getThreadKey(i);
      const hidden = hiddenPersonaIds.get(threadKey);
      if (hidden && hidden.has(i.persona.id)) return false;
      return true;
    });

    return filtered;
  }, [interactions, visibleThreadKeys, hiddenPersonaIds, showingAll]);

  const toggleThreadVisibility = useCallback((key: string) => {
    setVisibleThreadKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
    setActiveThread(key);
  }, []);

  const showAll = useCallback(() => {
    setVisibleThreadKeys(new Set());
    setActiveThread('room');
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
    activeThreadKey,
    visibleThreadKeys,
    hiddenPersonaIds,
    setActiveThread,
    toggleThreadVisibility,
    showAll,
    togglePersonaHidden,
    getHiddenPersonaIds,
  };
}
