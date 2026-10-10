import { useCallback, useSyncExternalStore } from 'react';

/**
 * Staff edit mode's on/off (#3988). In sessionStorage, so it stays on while staff browse
 * from sheet to sheet in this tab and is off in a new one. Every read and write is
 * wrapped: with storage unavailable the toggle still works for the page's lifetime.
 */
const KEY = 'arx.staffEditMode';
const listeners = new Set<() => void>();
let memory = false;

function read(): boolean {
  try {
    return window.sessionStorage.getItem(KEY) === '1';
  } catch {
    return memory;
  }
}

function write(on: boolean): void {
  memory = on;
  try {
    if (on) window.sessionStorage.setItem(KEY, '1');
    else window.sessionStorage.removeItem(KEY);
  } catch {
    // Storage blocked: the in-memory value carries the mode for this page.
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useStaffEditMode(): [boolean, (on: boolean) => void] {
  const on = useSyncExternalStore(subscribe, read, () => false);
  const set = useCallback((next: boolean) => write(next), []);
  return [on, set];
}
