import { render } from '@testing-library/react';
import { describe, expect, it, beforeEach, vi } from 'vitest';

import type { RealmTheme } from '../realm-theme-provider';
import { ThemeBackground } from '../theme-background';

// Mock useRealmTheme to control the theme value in tests
const mockUseRealmTheme = vi.fn();
vi.mock('../realm-theme-provider', async () => {
  const actual = await vi.importActual('../realm-theme-provider');
  return {
    ...actual,
    useRealmTheme: () => mockUseRealmTheme(),
  };
});

beforeEach(() => {
  mockUseRealmTheme.mockReset();
});

describe('ThemeBackground', () => {
  it('renders nothing when no theme is active', () => {
    mockUseRealmTheme.mockReturnValue({ realmTheme: null, plainMode: false });
    const { container } = render(<ThemeBackground />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a background div when theme is active', () => {
    mockUseRealmTheme.mockReturnValue({ realmTheme: 'arx', plainMode: false });
    const { container } = render(<ThemeBackground />);
    expect(container.firstChild).not.toBeNull();
  });

  it('is hidden from screen readers', () => {
    mockUseRealmTheme.mockReturnValue({ realmTheme: 'arx', plainMode: false });
    render(<ThemeBackground />);
    const bg = document.querySelector('[aria-hidden="true"]');
    expect(bg).not.toBeNull();
  });

  it('is non-interactive (pointer-events-none)', () => {
    mockUseRealmTheme.mockReturnValue({ realmTheme: 'arx', plainMode: false });
    const { container } = render(<ThemeBackground />);
    expect(container.firstChild).toHaveClass('pointer-events-none');
  });

  it.each(['default', 'arx', 'umbros', 'luxen', 'inferna', 'ariwn', 'aythirmok'] as RealmTheme[])(
    'renders a div for %s theme',
    (theme) => {
      mockUseRealmTheme.mockReturnValue({ realmTheme: theme, plainMode: false });
      const { container } = render(<ThemeBackground />);
      const div = container.firstChild as HTMLElement;
      expect(div).not.toBeNull();
      expect(div.tagName).toBe('DIV');
      expect(div).toHaveClass('fixed', 'inset-0', 'pointer-events-none');
    }
  );

  it('renders nothing when plain mode is active', () => {
    mockUseRealmTheme.mockReturnValue({ realmTheme: 'arx', plainMode: true });
    const { container } = render(<ThemeBackground />);
    expect(container.firstChild).toBeNull();
  });
});
