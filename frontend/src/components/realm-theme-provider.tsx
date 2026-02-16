/**
 * RealmThemeProvider — manages realm-specific visual themes.
 *
 * Applies a `data-realm` attribute to <html> that overrides CSS custom
 * properties. Works alongside next-themes (which handles light/dark mode).
 */

import { createContext, useCallback, useContext, useEffect, useState } from 'react';

export type RealmTheme = 'default' | 'arx' | 'umbros' | 'luxen' | 'inferna' | 'ariwn' | 'aythirmok';

interface RealmThemeContextValue {
  /** Current active realm theme, or null if no theme is applied. */
  realmTheme: RealmTheme | null;
  /** Set the realm theme. Pass null to remove theming entirely. */
  setRealmTheme: (theme: RealmTheme | null) => void;
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
  const [realmTheme, setRealmThemeState] = useState<RealmTheme | null>(() => {
    if (forcedTheme !== undefined) return forcedTheme;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && isValidRealmTheme(stored)) return stored;
    } catch {
      // localStorage unavailable
    }
    return null;
  });

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
      setRealmThemeState(theme);
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
      setRealmThemeState(forcedTheme);
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
    <RealmThemeContext.Provider value={{ realmTheme, setRealmTheme, plainMode, setPlainMode }}>
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
  return ['default', 'arx', 'umbros', 'luxen', 'inferna', 'ariwn', 'aythirmok'].includes(value);
}
