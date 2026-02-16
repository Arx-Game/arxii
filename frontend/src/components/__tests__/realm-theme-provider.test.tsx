import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, beforeEach } from 'vitest';

import { RealmThemeProvider, useRealmTheme } from '../realm-theme-provider';

// Helper component to expose context values for testing
function ThemeDisplay() {
  const { realmTheme, setRealmTheme } = useRealmTheme();
  return (
    <div>
      <span data-testid="theme">{realmTheme ?? 'none'}</span>
      <button onClick={() => setRealmTheme('arx')}>Set Arx</button>
      <button onClick={() => setRealmTheme('umbros')}>Set Umbros</button>
      <button onClick={() => setRealmTheme(null)}>Clear</button>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-realm');
});

describe('RealmThemeProvider', () => {
  it('starts with no theme by default', () => {
    render(
      <RealmThemeProvider>
        <ThemeDisplay />
      </RealmThemeProvider>
    );
    expect(screen.getByTestId('theme')).toHaveTextContent('none');
  });

  it('applies data-realm attribute to html element', async () => {
    const user = userEvent.setup();
    render(
      <RealmThemeProvider>
        <ThemeDisplay />
      </RealmThemeProvider>
    );

    await user.click(screen.getByText('Set Arx'));
    expect(document.documentElement.getAttribute('data-realm')).toBe('arx');
  });

  it('removes data-realm attribute when theme cleared', async () => {
    const user = userEvent.setup();
    render(
      <RealmThemeProvider>
        <ThemeDisplay />
      </RealmThemeProvider>
    );

    await user.click(screen.getByText('Set Arx'));
    expect(document.documentElement.getAttribute('data-realm')).toBe('arx');

    await user.click(screen.getByText('Clear'));
    expect(document.documentElement.hasAttribute('data-realm')).toBe(false);
  });

  it('persists theme to localStorage', async () => {
    const user = userEvent.setup();
    render(
      <RealmThemeProvider>
        <ThemeDisplay />
      </RealmThemeProvider>
    );

    await user.click(screen.getByText('Set Umbros'));
    expect(localStorage.getItem('realm-theme')).toBe('umbros');
  });

  it('removes from localStorage when cleared', async () => {
    const user = userEvent.setup();
    render(
      <RealmThemeProvider>
        <ThemeDisplay />
      </RealmThemeProvider>
    );

    await user.click(screen.getByText('Set Arx'));
    await user.click(screen.getByText('Clear'));
    expect(localStorage.getItem('realm-theme')).toBeNull();
  });

  it('loads theme from localStorage on mount', () => {
    localStorage.setItem('realm-theme', 'luxen');
    render(
      <RealmThemeProvider>
        <ThemeDisplay />
      </RealmThemeProvider>
    );
    expect(screen.getByTestId('theme')).toHaveTextContent('luxen');
  });

  it('ignores invalid localStorage values', () => {
    localStorage.setItem('realm-theme', 'invalid-theme');
    render(
      <RealmThemeProvider>
        <ThemeDisplay />
      </RealmThemeProvider>
    );
    expect(screen.getByTestId('theme')).toHaveTextContent('none');
  });

  it('uses forcedTheme when provided', () => {
    render(
      <RealmThemeProvider forcedTheme="inferna">
        <ThemeDisplay />
      </RealmThemeProvider>
    );
    expect(screen.getByTestId('theme')).toHaveTextContent('inferna');
  });

  it('prevents setRealmTheme when forcedTheme is active', async () => {
    const user = userEvent.setup();
    render(
      <RealmThemeProvider forcedTheme="inferna">
        <ThemeDisplay />
      </RealmThemeProvider>
    );

    await user.click(screen.getByText('Set Arx'));
    // Should still be inferna, not arx
    expect(screen.getByTestId('theme')).toHaveTextContent('inferna');
  });

  it('cleans up data-realm on unmount', () => {
    const { unmount } = render(
      <RealmThemeProvider forcedTheme="arx">
        <ThemeDisplay />
      </RealmThemeProvider>
    );

    expect(document.documentElement.getAttribute('data-realm')).toBe('arx');
    unmount();
    expect(document.documentElement.hasAttribute('data-realm')).toBe(false);
  });
});

describe('useRealmTheme', () => {
  it('throws when used outside provider', () => {
    // Suppress console.error from React error boundary
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<ThemeDisplay />)).toThrow(
      'useRealmTheme must be used within a RealmThemeProvider'
    );
    consoleSpy.mockRestore();
  });
});
