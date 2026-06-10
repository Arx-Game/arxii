/**
 * E2E-ish coverage for the resolve dialog (#877): real hooks + real dialog,
 * mocked api transport. Asserts the exact payload shapes for both paths.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { AlterationResolveDialog } from '../components/alterations/AlterationResolveDialog';
import type { PendingAlteration } from '../types';

// ---------------------------------------------------------------------------
// Mock the api module (factory style — hoisted before class declarations)
// Real hooks (useAlterationLibrary, useResolveAlteration) run against these
// mocked transport functions.
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  getAlterationLibrary: vi.fn(),
  resolveAlteration: vi.fn(),
  // Inline class so instanceof checks survive hoisting
  AlterationResolveError: class AlterationResolveError extends Error {
    fieldErrors: Record<string, string[]>;
    constructor(message: string, fieldErrors: Record<string, string[]> = {}) {
      super(message);
      this.name = 'AlterationResolveError';
      this.fieldErrors = fieldErrors;
    }
  },
}));

// Mock conditions/api — AlterationAuthorForm will need fetchDamageTypes; harmless now.
vi.mock('@/conditions/api', () => ({
  fetchDamageTypes: vi.fn().mockResolvedValue([]),
}));

// Mock sonner — dialog calls toast.success on successful resolution.
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PENDING: PendingAlteration = {
  id: 7,
  character_id: 3,
  character_name: 'Velenosa',
  status: 'open' as const,
  tier: 3,
  tier_display: 'Touched',
  tier_caps: {
    social_cap: 3,
    weakness_cap: 3,
    resonance_cap: 3,
    visibility_required: false,
  } as unknown as Record<string, unknown>,
  origin_affinity_name: 'Abyssal',
  origin_resonance_name: 'Shadow',
  triggering_scene: null,
  created_at: '2026-06-01T00:00:00Z',
};

const LIBRARY_ENTRY = {
  id: 11,
  name: 'Veins of Night',
  tier: 3,
  player_description: 'Dark veins spider across your forearms when you draw on the abyss.',
  observer_description: 'Faint dark veining is visible along their forearms.',
  origin_affinity_name: 'Abyssal',
  weakness_magnitude: 1,
  resonance_bonus_magnitude: 2,
  social_reactivity_magnitude: 1,
  is_visible_at_rest: false,
};

// ---------------------------------------------------------------------------
// Wrapper — QueryClientProvider only (no Redux; hooks don't read Redux)
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderDialog(open = true) {
  const onOpenChange = vi.fn();
  const { unmount } = render(
    <AlterationResolveDialog pending={PENDING} open={open} onOpenChange={onOpenChange} />,
    { wrapper: createWrapper() }
  );
  return { onOpenChange, unmount };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AlterationResolveDialog — library path', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('submits exactly { library_template_id: 11 } when an entry is selected and accepted', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getAlterationLibrary).mockResolvedValue([LIBRARY_ENTRY]);
    vi.mocked(api.resolveAlteration).mockResolvedValue({
      pending_id: 7,
      character_name: 'Velenosa',
      alteration_name: 'Veins of Night',
      player_description: 'Dark veins spider across your forearms when you draw on the abyss.',
      observer_description: 'Faint dark veining is visible along their forearms.',
      weakness_damage_type_id: null,
      weakness_magnitude: 1,
      resonance_bonus_magnitude: 2,
      social_reactivity_magnitude: 1,
      is_visible_at_rest: false,
    });

    renderDialog();

    // Library entry appears after the query resolves
    await screen.findByText('Veins of Night');

    // Click the entry card to select it
    await user.click(screen.getByText('Veins of Night'));

    // Accept button should now be enabled; click it
    const acceptBtn = screen.getByRole('button', { name: /accept this mark/i });
    await user.click(acceptBtn);

    await waitFor(() => {
      expect(api.resolveAlteration).toHaveBeenCalledWith(7, { library_template_id: 11 });
    });
  });

  it('renders non_field_errors in the error banner on server rejection', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getAlterationLibrary).mockResolvedValue([LIBRARY_ENTRY]);

    const { AlterationResolveError } = await import('../api');
    vi.mocked(api.resolveAlteration).mockRejectedValue(
      new AlterationResolveError('Character already has this condition active.', {
        non_field_errors: ['Character already has this condition active.'],
      })
    );

    renderDialog();

    await screen.findByText('Veins of Night');
    await user.click(screen.getByText('Veins of Night'));
    await user.click(screen.getByRole('button', { name: /accept this mark/i }));

    await screen.findByText('Character already has this condition active.');
  });

  it('shows a "no library entries" message when the library is empty', async () => {
    vi.mocked(api.getAlterationLibrary).mockResolvedValue([]);

    renderDialog();

    await screen.findByText(/no library entries match/i);
  });

  it('Accept button is disabled until an entry is selected', async () => {
    vi.mocked(api.getAlterationLibrary).mockResolvedValue([LIBRARY_ENTRY]);

    renderDialog();

    await screen.findByText('Veins of Night');

    const acceptBtn = screen.getByRole('button', { name: /accept this mark/i });
    expect(acceptBtn).toBeDisabled();
  });
});
