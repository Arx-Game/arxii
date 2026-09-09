import { useCallback, useState } from 'react';

export interface PlayPreferences {
  proseSize: number;
  proseFamily: 'sans' | 'serif';
  measure: number;
}
export const DEFAULT_PLAY_PREFERENCES: PlayPreferences = {
  proseSize: 14,
  proseFamily: 'sans',
  measure: 90,
};
const STORAGE_KEY = 'arx:play-preferences:v1';

export function loadPlayPreferences(): PlayPreferences {
  try {
    const value = JSON.parse(
      window.localStorage.getItem(STORAGE_KEY) ?? 'null'
    ) as Partial<PlayPreferences> | null;
    if (!value) return DEFAULT_PLAY_PREFERENCES;
    return {
      proseSize: Math.min(20, Math.max(12, Number(value.proseSize) || 14)),
      proseFamily: value.proseFamily === 'serif' ? 'serif' : 'sans',
      measure: Math.min(110, Math.max(72, Number(value.measure) || 90)),
    };
  } catch {
    return DEFAULT_PLAY_PREFERENCES;
  }
}

export function savePlayPreferences(preferences: PlayPreferences): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    /* tab-only fallback */
  }
}

export function usePlayPreferences() {
  const [preferences, setPreferences] = useState(loadPlayPreferences);
  const update = useCallback((patch: Partial<PlayPreferences>) => {
    setPreferences((current) => {
      const next = { ...current, ...patch };
      savePlayPreferences(next);
      return next;
    });
  }, []);
  return { preferences, update };
}
