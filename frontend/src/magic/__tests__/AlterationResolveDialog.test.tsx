/**
 * E2E-ish coverage for the resolve dialog (#877): real hooks + real dialog,
 * mocked api transport. Asserts the exact payload shapes for both paths.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
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

// Mock conditions/api — AlterationAuthorForm needs fetchDamageTypes.
vi.mock('@/conditions/api', () => ({
  fetchDamageTypes: vi.fn(),
}));

// Mock sonner — dialog calls toast.success on successful resolution.
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as api from '../api';
import * as conditionsApi from '@/conditions/api';

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

const TIER4_PENDING: PendingAlteration = {
  ...PENDING,
  id: 8,
  tier: 4,
  tier_display: 'Marked Profoundly',
  tier_caps: {
    social_cap: 5,
    weakness_cap: 5,
    resonance_cap: 5,
    visibility_required: true,
  } as unknown as Record<string, unknown>,
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

function renderDialog(pending = PENDING, open = true) {
  const onOpenChange = vi.fn();
  const { unmount } = render(
    <AlterationResolveDialog pending={pending} open={open} onOpenChange={onOpenChange} />,
    { wrapper: createWrapper() }
  );
  return { onOpenChange, unmount };
}

// Opens the "Author your own" tab and returns the user instance.
async function openAuthorTab(user: ReturnType<typeof userEvent.setup>) {
  const authorTab = screen.getByRole('tab', { name: /author your own/i });
  await user.click(authorTab);
}

// ---------------------------------------------------------------------------
// Tests — library path
// ---------------------------------------------------------------------------

describe('AlterationResolveDialog — library path', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(conditionsApi.fetchDamageTypes).mockResolvedValue([{ id: 1, name: 'Spirit' }]);
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

    // The library tab is active; scope queries to its panel to avoid collision
    // with the forceMount'd author tab (both panels are in the DOM).
    const libraryPanel = screen.getByRole('tabpanel', { name: /choose from the library/i });

    // Click the entry card to select it
    await user.click(within(libraryPanel).getByText('Veins of Night'));

    // Accept button should now be enabled; click it
    const acceptBtn = within(libraryPanel).getByRole('button', { name: /accept this mark/i });
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
    const libraryPanel = screen.getByRole('tabpanel', { name: /choose from the library/i });
    await user.click(within(libraryPanel).getByText('Veins of Night'));
    await user.click(within(libraryPanel).getByRole('button', { name: /accept this mark/i }));

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

    const libraryPanel = screen.getByRole('tabpanel', { name: /choose from the library/i });
    const acceptBtn = within(libraryPanel).getByRole('button', { name: /accept this mark/i });
    expect(acceptBtn).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Tests — author-from-scratch path
// ---------------------------------------------------------------------------

describe('AlterationResolveDialog — author path', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getAlterationLibrary).mockResolvedValue([]);
    vi.mocked(conditionsApi.fetchDamageTypes).mockResolvedValue([{ id: 1, name: 'Spirit' }]);
  });

  it('submits the full scratch payload with defaults', async () => {
    const user = userEvent.setup();
    vi.mocked(api.resolveAlteration).mockResolvedValue({
      pending_id: 7,
      character_name: 'Velenosa',
      alteration_name: 'Voice of Many',
      player_description: '',
      observer_description: '',
      weakness_damage_type_id: null,
      weakness_magnitude: 0,
      resonance_bonus_magnitude: 0,
      social_reactivity_magnitude: 0,
      is_visible_at_rest: false,
    });

    renderDialog();
    await openAuthorTab(user);

    const authorPanel = screen.getByRole('tabpanel', { name: /author your own/i });

    // Wait for damage types to load
    await within(authorPanel).findByLabelText(/weakness damage type/i);

    // Fill in name
    const nameInput = within(authorPanel).getByLabelText(/^name$/i);
    await user.clear(nameInput);
    await user.type(nameInput, 'Voice of Many');

    // Fill in player description (must be ≥40 chars)
    const playerDesc = within(authorPanel).getByLabelText(/how it feels to you/i);
    const playerText =
      'The voices of the abyss whisper through your mind constantly, shaping your thoughts.';
    await user.clear(playerDesc);
    await user.type(playerDesc, playerText);

    // Fill in observer description (must be ≥40 chars)
    const observerDesc = within(authorPanel).getByLabelText(/what others see/i);
    const observerText =
      'Their eyes occasionally flicker with dark light when they speak with authority.';
    await user.clear(observerDesc);
    await user.type(observerDesc, observerText);

    // Submit
    const submitBtn = within(authorPanel).getByRole('button', { name: /bind this mark/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(api.resolveAlteration).toHaveBeenCalledWith(7, {
        name: 'Voice of Many',
        player_description: playerText,
        observer_description: observerText,
        weakness_damage_type_id: null,
        weakness_magnitude: 0,
        resonance_bonus_magnitude: 0,
        social_reactivity_magnitude: 0,
        is_visible_at_rest: false,
      });
    });
  });

  it('blocks submit until both descriptions hit 40 chars', async () => {
    const user = userEvent.setup();

    renderDialog();
    await openAuthorTab(user);

    const authorPanel = screen.getByRole('tabpanel', { name: /author your own/i });

    // Wait for form to render
    await within(authorPanel).findByLabelText(/^name$/i);

    const nameInput = within(authorPanel).getByLabelText(/^name$/i);
    await user.type(nameInput, 'Voice of Many');

    // Short player description — too short
    const playerDesc = within(authorPanel).getByLabelText(/how it feels to you/i);
    await user.type(playerDesc, 'Too short.');

    // Submit should be disabled
    const submitBtn = within(authorPanel).getByRole('button', { name: /bind this mark/i });
    expect(submitBtn).toBeDisabled();
  });

  it('requires damage type when weakness > 0', async () => {
    const user = userEvent.setup();

    renderDialog();
    await openAuthorTab(user);

    const authorPanel = screen.getByRole('tabpanel', { name: /author your own/i });

    // Wait for damage types to load
    await within(authorPanel).findByLabelText(/weakness damage type/i);

    // Fill fields with valid content
    const nameInput = within(authorPanel).getByLabelText(/^name$/i);
    await user.type(nameInput, 'Voice of Many');

    const playerDesc = within(authorPanel).getByLabelText(/how it feels to you/i);
    await user.type(
      playerDesc,
      'The voices of the abyss whisper through your mind constantly, shaping your thoughts.'
    );

    const observerDesc = within(authorPanel).getByLabelText(/what others see/i);
    await user.type(
      observerDesc,
      'Their eyes occasionally flicker with dark light when they speak with authority.'
    );

    // Set weakness magnitude to 1 — now damage type is required
    const weaknessMag = within(authorPanel).getByLabelText(/weakness magnitude/i);
    await user.selectOptions(weaknessMag, '1');

    // Submit should be disabled (no damage type selected)
    const submitBtn = within(authorPanel).getByRole('button', { name: /bind this mark/i });
    expect(submitBtn).toBeDisabled();

    // Pick damage type 'Spirit'
    const damageTypeSelect = within(authorPanel).getByLabelText(/weakness damage type/i);
    await user.selectOptions(damageTypeSelect, '1');

    // Submit should now be enabled
    await waitFor(() => {
      expect(submitBtn).not.toBeDisabled();
    });
  });

  it('offers magnitudes only up to caps', async () => {
    const user = userEvent.setup();

    renderDialog();
    await openAuthorTab(user);

    const authorPanel = screen.getByRole('tabpanel', { name: /author your own/i });

    // Wait for form fields
    await within(authorPanel).findByLabelText(/social reactivity/i);

    const socialSelect = within(authorPanel).getByLabelText(/social reactivity/i);

    // Options 0, 1, 2, 3 should be present (cap is 3)
    await user.selectOptions(socialSelect, '0');
    await user.selectOptions(socialSelect, '1');
    await user.selectOptions(socialSelect, '2');
    await user.selectOptions(socialSelect, '3');

    // Option '4' should NOT exist in the select
    const options = Array.from(socialSelect.querySelectorAll('option'));
    const optionValues = options.map((o) => o.value);
    expect(optionValues).not.toContain('4');
    expect(optionValues).toContain('3');
  });

  it('forces visibility at tier 4', async () => {
    const user = userEvent.setup();

    renderDialog(TIER4_PENDING);
    await openAuthorTab(user);

    const authorPanel = screen.getByRole('tabpanel', { name: /author your own/i });

    // Wait for form
    await within(authorPanel).findByLabelText(/visible at rest/i);

    const visibilitySwitch = within(authorPanel).getByLabelText(/visible at rest/i);

    // Should be checked
    expect(visibilitySwitch).toBeChecked();

    // Should be disabled
    expect(visibilitySwitch).toBeDisabled();

    // Helper copy should be visible
    expect(
      within(authorPanel).getByText(/an alteration this profound cannot be hidden/i)
    ).toBeInTheDocument();
  });

  it('preserves authored prose when switching to the library tab and back', async () => {
    const user = userEvent.setup();

    renderDialog();
    await openAuthorTab(user);

    const authorPanel = screen.getByRole('tabpanel', { name: /author your own/i });

    // Wait for form
    await within(authorPanel).findByLabelText(/^name$/i);

    // Type values into all three text fields
    const nameInput = within(authorPanel).getByLabelText(/^name$/i);
    await user.type(nameInput, 'Scar of the Deep');

    const playerDesc = within(authorPanel).getByLabelText(/how it feels to you/i);
    const playerText =
      'Cold tendrils of void consciousness brush the edges of your perception at all hours.';
    await user.type(playerDesc, playerText);

    const observerDesc = within(authorPanel).getByLabelText(/what others see/i);
    const observerText =
      'A faint aura of wrongness clings to their silhouette, noticed but hard to name.';
    await user.type(observerDesc, observerText);

    // Switch away to the library tab
    const libraryTab = screen.getByRole('tab', { name: /choose from the library/i });
    await user.click(libraryTab);

    // Switch back to the author tab
    const authorTab = screen.getByRole('tab', { name: /author your own/i });
    await user.click(authorTab);

    // All three values must still be present
    expect(within(authorPanel).getByLabelText(/^name$/i)).toHaveValue('Scar of the Deep');
    expect(within(authorPanel).getByLabelText(/how it feels to you/i)).toHaveValue(playerText);
    expect(within(authorPanel).getByLabelText(/what others see/i)).toHaveValue(observerText);
  });
});
