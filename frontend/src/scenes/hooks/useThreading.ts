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

export interface UseThreadingOpts {
  /** Highest interaction id already seen per thread key (Redux `Session.threadLastSeen`). */
  lastSeenByThread?: Record<string, number>;
  /** The viewing persona's id — its own interactions never count toward its own unread. */
  viewerPersonaId?: number | null;
  /**
   * Highest interaction id present at scene-load time (Redux
   * `Session.sceneBaselineId`, #2156 review fix). Used as the unread
   * threshold for any thread key with no `lastSeenByThread` entry — so a
   * brand-new thread that appears mid-session (no baseline of its own yet)
   * badges unread from its first message, rather than being silently marked
   * seen the moment it's first observed.
   */
  sceneBaselineId?: number | null;
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
  /**
   * Clears the thread filter (enabledThreadKeys), selection, and every
   * per-thread hidden-persona mute (#2156 review fix). `showAll` alone only
   * clears the first two — this is the full reset a scene change or puppet
   * switch needs so a filter/mute picked in the PREVIOUS scene/puppet
   * context doesn't silently strand-hide interactions in a new one that
   * happens to reuse the same thread key (e.g. two puppets in the same
   * room, or a room re-entering an old scene id).
   */
  resetForNewScene: () => void;
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

// Ratified semantics (#2156, review-fixed): a thread key with a real
// `lastSeenByThread` entry counts interactions newer than it, excluding the
// viewer's own (an author never owes themself an unread badge for their own
// words). A thread key with NO entry falls back to the scene-load baseline
// scalar (`sceneBaselineId`) — this is what lets a brand-new thread that
// appears mid-session (a first whisper, say) badge unread starting from its
// very first message, instead of being silently marked "seen" the moment
// it's first observed (the old per-thread-key baseline's bug). With no entry
// AND no baseline (e.g. `/scenes/:id` passing no opts at all) unread is 0,
// exactly as before.
function countUnread(
  threadInteractions: Interaction[],
  threadKey: string,
  lastSeenByThread: Record<string, number> | undefined,
  viewerPersonaId: number | null | undefined,
  sceneBaselineId: number | null | undefined
): number {
  const lastSeen = lastSeenByThread?.[threadKey];
  const threshold = lastSeen !== undefined ? lastSeen : sceneBaselineId;
  if (threshold === undefined || threshold === null) return 0;
  return threadInteractions.filter((i) => {
    if (viewerPersonaId != null && i.persona.id === viewerPersonaId) return false;
    return Number(i.id) > threshold;
  }).length;
}

export function useThreading(
  interactions: Interaction[],
  roomName: string,
  opts?: UseThreadingOpts
): ThreadingState {
  const [selectedThreadKey, setSelectedThread] = useState('room');
  const [enabledThreadKeys, setEnabledThreadKeys] = useState<Set<string>>(new Set());
  const [hiddenPersonaIds, setHiddenPersonaIds] = useState<Map<string, Set<number>>>(new Map());
  const isUnfiltered = enabledThreadKeys.size === 0;
  const lastSeenByThread = opts?.lastSeenByThread;
  const viewerPersonaId = opts?.viewerPersonaId;
  const sceneBaselineId = opts?.sceneBaselineId;

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
          unreadCount: countUnread(
            threadInteractions,
            key,
            lastSeenByThread,
            viewerPersonaId,
            sceneBaselineId
          ),
        } as Thread;
      })
      .sort((a, b) => {
        if (a.type === 'room') return -1;
        if (b.type === 'room') return 1;
        return b.latestTimestamp.localeCompare(a.latestTimestamp);
      });
    return { threads: threadList, threadKeyMap: keyMap };
  }, [interactions, roomName, lastSeenByThread, viewerPersonaId, sceneBaselineId]);

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

  const resetForNewScene = useCallback(() => {
    setEnabledThreadKeys(new Set());
    setSelectedThread('room');
    setHiddenPersonaIds(new Map());
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
    resetForNewScene,
  };
}
