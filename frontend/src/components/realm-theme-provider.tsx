/**
 * RealmThemeProvider — manages realm-specific visual themes.
 *
 * Applies a `data-realm` attribute to <html> that overrides CSS custom
 * properties. Works alongside next-themes (which handles light/dark mode).
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

export const REALM_THEMES = [
  'default',
  'arx',
  'umbros',
  'luxen',
  'inferna',
  'ariwn',
  'aythirmok',
] as const;

export type RealmTheme = (typeof REALM_THEMES)[number];

interface RealmThemeContextValue {
  /** Current active realm theme, or null if no theme is applied. */
  realmTheme: RealmTheme | null;
  /** Set the realm theme. Pass null to remove theming entirely. */
  setRealmTheme: (theme: RealmTheme | null) => void;
  /**
   * Force a realm theme at runtime, overriding both the stored choice and the
   * `forcedTheme` prop. Pass `undefined` to clear the force — the provider
   * re-reads localStorage and restores the user's stored realm (it does not
   * simply fall back to whatever value happened to be in state).
   */
  setForcedRealm: (theme: RealmTheme | undefined) => void;
  /** Whether plain mode is active (disables all realm theming). */
  plainMode: boolean;
  /** Toggle plain mode on or off. */
  setPlainMode: (enabled: boolean) => void;
}

const RealmThemeContext = createContext<RealmThemeContextValue | undefined>(undefined);

const STORAGE_KEY = 'realm-theme';
const PLAIN_MODE_KEY = 'plain-mode';
const DATA_ATTR = 'data-realm';
const PLAIN_ATTR = 'data-plain-mode';

interface RealmThemeProviderProps {
  children: React.ReactNode;
  /** If provided, overrides localStorage. Used for contextual theming (CG, character pages). */
  forcedTheme?: RealmTheme | null;
}

export function RealmThemeProvider({ children, forcedTheme }: RealmThemeProviderProps) {
  // The underlying stored/prop-driven theme selection. This is what
  // `setRealmTheme` writes to and what localStorage backs; the `forcedTheme`
  // prop's forcing behavior lives here, unchanged from before.
  const [storedTheme, setStoredThemeState] = useState<RealmTheme | null>(() => {
    if (forcedTheme !== undefined) return forcedTheme;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && isValidRealmTheme(stored)) return stored;
    } catch {
      // localStorage unavailable
    }
    return null;
  });

  // A runtime override layer set imperatively via context (`setForcedRealm`),
  // independent of the `forcedTheme` prop and of `storedTheme`. Always starts
  // undefined — `storedTheme`'s own initializer already returns `forcedTheme`
  // when the prop is set, so `realmTheme = forcedRealm ?? storedTheme`
  // resolves correctly at mount without seeding this from the prop. Seeding
  // it from the prop would make it sticky: if the prop later changed to a
  // different value, the sync effect below would update `storedTheme` but
  // this state would still win the `??`, leaving the rendered realm stuck.
  const [forcedRealm, setForcedRealmState] = useState<RealmTheme | undefined>(undefined);

  const setForcedRealm = useCallback(
    (theme: RealmTheme | undefined) => {
      if (theme !== undefined) {
        setForcedRealmState(theme);
        return;
      }
      // Clearing the force: don't just drop back to whatever `storedTheme`
      // happens to hold in state — re-read localStorage directly, so the
      // user's stored realm is restored even if `storedTheme` went stale
      // while the force was active (e.g. another tab changed it). This also
      // preserves an active `forcedTheme` PROP: the prop keeps `storedTheme`
      // pinned to its own value (see the sync effect below), so a stored
      // localStorage value never overrides it here.
      setForcedRealmState(undefined);
      if (forcedTheme !== undefined) return;
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        setStoredThemeState(stored && isValidRealmTheme(stored) ? stored : null);
      } catch {
        setStoredThemeState(null);
      }
    },
    [forcedTheme]
  );

  // The effective theme actually rendered: the runtime force wins, then the
  // stored/prop-driven selection.
  const realmTheme = forcedRealm ?? storedTheme;

  const [plainMode, setPlainModeState] = useState<boolean>(() => {
    try {
      return localStorage.getItem(PLAIN_MODE_KEY) === 'true';
    } catch {
      return false;
    }
  });

  const setRealmTheme = useCallback(
    (theme: RealmTheme | null) => {
      // Don't override if a forced theme is set
      if (forcedTheme !== undefined) return;
      setStoredThemeState(theme);
      try {
        if (theme) {
          localStorage.setItem(STORAGE_KEY, theme);
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      } catch {
        // localStorage unavailable
      }
    },
    [forcedTheme]
  );

  const setPlainMode = useCallback((enabled: boolean) => {
    setPlainModeState(enabled);
    try {
      if (enabled) {
        localStorage.setItem(PLAIN_MODE_KEY, 'true');
      } else {
        localStorage.removeItem(PLAIN_MODE_KEY);
      }
    } catch {
      // localStorage unavailable
    }
  }, []);

  // Sync forced theme changes
  useEffect(() => {
    if (forcedTheme !== undefined) {
      setStoredThemeState(forcedTheme);
    }
  }, [forcedTheme]);

  // Apply data-realm attribute to <html> (skipped in plain mode)
  useEffect(() => {
    const root = document.documentElement;
    if (realmTheme && !plainMode) {
      root.setAttribute(DATA_ATTR, realmTheme);
    } else {
      root.removeAttribute(DATA_ATTR);
    }
    return () => {
      root.removeAttribute(DATA_ATTR);
    };
  }, [realmTheme, plainMode]);

  // Apply data-plain-mode attribute to <html>
  useEffect(() => {
    const root = document.documentElement;
    if (plainMode) {
      root.setAttribute(PLAIN_ATTR, '');
    } else {
      root.removeAttribute(PLAIN_ATTR);
    }
    return () => {
      root.removeAttribute(PLAIN_ATTR);
    };
  }, [plainMode]);

  return (
    <RealmThemeContext.Provider
      value={{ realmTheme, setRealmTheme, setForcedRealm, plainMode, setPlainMode }}
    >
      {children}
    </RealmThemeContext.Provider>
  );
}

export function useRealmTheme() {
  const context = useContext(RealmThemeContext);
  if (!context) {
    throw new Error('useRealmTheme must be used within a RealmThemeProvider');
  }
  return context;
}

function isValidRealmTheme(value: string): value is RealmTheme {
  return (REALM_THEMES as readonly string[]).includes(value);
}
