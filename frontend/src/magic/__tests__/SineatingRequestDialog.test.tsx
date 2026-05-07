/**
 * SineatingRequestDialog tests
 *
 * Covers: render gating, form validation, submit body shape, onSuccess,
 * error banner, and cancel behaviour.
 *
 * Note on Radix Select: Opening SelectContent in jsdom triggers
 * scrollIntoView behaviour that requires the global polyfill in
 * src/test/setup.ts. Tests that need to select a value use
 * userEvent.click on the trigger followed by finding the item in the list.
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { SineatingRequestDialog } from '../components/SineatingRequestDialog';
import type { useRequestSineating } from '../queries';
import type { useCharacterResonances } from '../queries';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useRequestSineating: vi.fn(),
  useCharacterResonances: vi.fn(),
}));

vi.mock('@/scenes/queries', () => ({
  fetchScenes: vi.fn(),
}));

vi.mock('@/events/queries', () => ({
  searchPersonas: vi.fn(),
}));

import * as magicQueries from '../queries';
import * as scenesQueries from '@/scenes/queries';
import * as eventsQueries from '@/events/queries';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const defaultProps = {
  sinnerSheetId: 10,
  hollowCurrent: 30,
  hollowMax: 50,
  open: true,
  onOpenChange: vi.fn(),
  onSuccess: vi.fn(),
};

const mockResonances = [
  {
    id: 3,
    character_sheet: 10,
    resonance: 3,
    resonance_name: 'Starfire',
    resonance_detail: { id: 3, name: 'Starfire' },
    balance: 50,
    lifetime_earned: 200,
    claimed_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 4,
    character_sheet: 10,
    resonance: 4,
    resonance_name: 'Moonveil',
    resonance_detail: { id: 4, name: 'Moonveil' },
    balance: 20,
    lifetime_earned: 80,
    claimed_at: '2026-01-01T00:00:00Z',
  },
];

const mockScenes = {
  results: [
    {
      id: 5,
      name: 'The Whispering Grove',
      description: '',
      date_started: '',
      participants: [],
    },
  ],
};

function setupMocks(overrides?: { isPending?: boolean; isError?: boolean; error?: Error }) {
  const mutate = vi.fn();
  const mutation = {
    mutate,
    isPending: overrides?.isPending ?? false,
    isError: overrides?.isError ?? false,
    error: overrides?.error ?? null,
    reset: vi.fn(),
  };

  vi.mocked(magicQueries.useRequestSineating).mockReturnValue(
    mutation as unknown as ReturnType<typeof useRequestSineating>
  );

  vi.mocked(magicQueries.useCharacterResonances).mockReturnValue({
    data: mockResonances,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useCharacterResonances>);

  vi.mocked(scenesQueries.fetchScenes).mockResolvedValue(mockScenes);

  return { mutate };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SineatingRequestDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Render gating
  // -------------------------------------------------------------------------

  it('renders dialog content when open=true', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    expect(screen.getByText(/request sineating/i)).toBeInTheDocument();
  });

  it('does not render dialog content when open=false', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} open={false} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByText(/request sineating/i)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Available units shown in description
  // -------------------------------------------------------------------------

  it('shows available capacity derived from hollowMax - hollowCurrent', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} hollowCurrent={30} hollowMax={50} />, {
      wrapper: createWrapper(),
    });

    // Available units = 50 - 30 = 20; displayed inside the dialog description
    const availableEl = screen.getByTestId('available-units');
    expect(availableEl).toHaveTextContent('20');
  });

  // -------------------------------------------------------------------------
  // 3. Submit button disabled initially (no fields filled)
  // -------------------------------------------------------------------------

  it('submit button is disabled when no fields are filled', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    const submitButton = screen.getByTestId('sineating-request-submit');
    expect(submitButton).toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // 4. Units validation: units must be >= 1
  // -------------------------------------------------------------------------

  it('submit button stays disabled when units = 0 (only units filled)', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    const unitsInput = screen.getByTestId('sineating-units-input');
    fireEvent.change(unitsInput, { target: { value: '0' } });

    const submitButton = screen.getByTestId('sineating-request-submit');
    // Still disabled — other fields not set and units invalid
    expect(submitButton).toBeDisabled();
  });

  it('submit button stays disabled when units > hollowMax - hollowCurrent', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} hollowCurrent={30} hollowMax={50} />, {
      wrapper: createWrapper(),
    });

    // max = 20; entering 21 should be invalid
    const unitsInput = screen.getByTestId('sineating-units-input');
    fireEvent.change(unitsInput, { target: { value: '21' } });

    const submitButton = screen.getByTestId('sineating-request-submit');
    expect(submitButton).toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // 5. Sineater persona search shows results and selection updates input
  // -------------------------------------------------------------------------

  it('shows persona search results after typing and selecting fills the field', async () => {
    setupMocks();
    vi.mocked(eventsQueries.searchPersonas).mockResolvedValue([{ id: 20, name: 'Rael' }]);

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    const sineaterInput = screen.getByTestId('sineater-search-input');
    await userEvent.type(sineaterInput, 'Rae');

    await waitFor(() => {
      expect(screen.getByText('Rael')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Rael'));

    // After selection, input should show the persona name
    expect(sineaterInput).toHaveValue('Rael');
    // Dropdown should be gone
    expect(screen.queryByText('Rael')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 6. Resonance and scene selects render with options
  // -------------------------------------------------------------------------

  it('renders resonance select trigger', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('resonance-select-trigger')).toBeInTheDocument();
  });

  it('renders scene select trigger', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('scene-select-trigger')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 7. Submit fires mutate with correct body
  // -------------------------------------------------------------------------

  it('submitting fires useRequestSineating().mutate with the correct body shape', async () => {
    const { mutate } = setupMocks();
    vi.mocked(eventsQueries.searchPersonas).mockResolvedValue([{ id: 20, name: 'Rael' }]);

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    // Select sineater via search
    const sineaterInput = screen.getByTestId('sineater-search-input');
    await userEvent.type(sineaterInput, 'Rae');
    await waitFor(() => screen.getByText('Rael'));
    fireEvent.click(screen.getByText('Rael'));

    // Open resonance select and pick Starfire
    const resonanceTrigger = screen.getByTestId('resonance-select-trigger');
    await userEvent.click(resonanceTrigger);
    await waitFor(() => screen.getByRole('option', { name: 'Starfire' }));
    await userEvent.click(screen.getByRole('option', { name: 'Starfire' }));

    // Open scene select and pick the scene
    const sceneTrigger = screen.getByTestId('scene-select-trigger');
    await userEvent.click(sceneTrigger);
    await waitFor(() => screen.getByRole('option', { name: 'The Whispering Grove' }));
    await userEvent.click(screen.getByRole('option', { name: 'The Whispering Grove' }));

    // Set units
    const unitsInput = screen.getByTestId('sineating-units-input');
    fireEvent.change(unitsInput, { target: { value: '5' } });

    // Submit should now be enabled
    const submitButton = screen.getByTestId('sineating-request-submit');
    await waitFor(() => expect(submitButton).not.toBeDisabled());

    fireEvent.click(submitButton);

    expect(mutate).toHaveBeenCalledWith(
      {
        actor_sheet_id: 10,
        sineater_sheet_id: 20,
        resonance_id: 3,
        max_units: 5,
        scene_id: 5,
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      })
    );
  });

  // -------------------------------------------------------------------------
  // 8. onSuccess + onOpenChange(false) on mutation success
  // -------------------------------------------------------------------------

  it('calls onSuccess and onOpenChange(false) on mutation success', async () => {
    const { mutate } = setupMocks();
    const onSuccess = vi.fn();
    const onOpenChange = vi.fn();
    vi.mocked(eventsQueries.searchPersonas).mockResolvedValue([{ id: 20, name: 'Rael' }]);

    // Make mutate invoke its onSuccess callback immediately
    mutate.mockImplementation((_body: unknown, callbacks: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.();
    });

    render(
      <SineatingRequestDialog
        {...defaultProps}
        onSuccess={onSuccess}
        onOpenChange={onOpenChange}
      />,
      { wrapper: createWrapper() }
    );

    // Set up sineater
    const sineaterInput = screen.getByTestId('sineater-search-input');
    await userEvent.type(sineaterInput, 'Rae');
    await waitFor(() => screen.getByText('Rael'));
    fireEvent.click(screen.getByText('Rael'));

    // Set resonance
    const resonanceTrigger = screen.getByTestId('resonance-select-trigger');
    await userEvent.click(resonanceTrigger);
    await waitFor(() => screen.getByRole('option', { name: 'Starfire' }));
    await userEvent.click(screen.getByRole('option', { name: 'Starfire' }));

    // Set scene
    const sceneTrigger = screen.getByTestId('scene-select-trigger');
    await userEvent.click(sceneTrigger);
    await waitFor(() => screen.getByRole('option', { name: 'The Whispering Grove' }));
    await userEvent.click(screen.getByRole('option', { name: 'The Whispering Grove' }));

    // Set units
    const unitsInput = screen.getByTestId('sineating-units-input');
    fireEvent.change(unitsInput, { target: { value: '3' } });

    const submitButton = screen.getByTestId('sineating-request-submit');
    await waitFor(() => expect(submitButton).not.toBeDisabled());
    fireEvent.click(submitButton);

    expect(onSuccess).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // -------------------------------------------------------------------------
  // 9. Error banner
  // -------------------------------------------------------------------------

  it('shows error banner when mutation is in error state', () => {
    setupMocks({
      isError: true,
      error: new Error('Hollow is full'),
    });

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('sineating-error-banner')).toBeInTheDocument();
    expect(screen.getByText('Hollow is full')).toBeInTheDocument();
  });

  it('does not show error banner when mutation has no error', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('sineating-error-banner')).not.toBeInTheDocument();
  });

  it('shows generic error message when error has no message', () => {
    const emptyError = new Error('');
    setupMocks({ isError: true, error: emptyError });

    render(<SineatingRequestDialog {...defaultProps} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('sineating-error-banner')).toBeInTheDocument();
    expect(screen.getByText('Failed to send Sineating request')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Cancel calls onOpenChange(false)
  // -------------------------------------------------------------------------

  it('Cancel button calls onOpenChange(false)', () => {
    setupMocks();
    const onOpenChange = vi.fn();

    render(<SineatingRequestDialog {...defaultProps} onOpenChange={onOpenChange} />, {
      wrapper: createWrapper(),
    });

    const cancelButton = screen.getByTestId('sineating-cancel-button');
    fireEvent.click(cancelButton);

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // -------------------------------------------------------------------------
  // 11. Hollow at max disables units input
  // -------------------------------------------------------------------------

  it('shows capacity message when hollow is at max', () => {
    setupMocks();

    render(<SineatingRequestDialog {...defaultProps} hollowCurrent={50} hollowMax={50} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText(/hollow is already at maximum capacity/i)).toBeInTheDocument();
    expect(screen.getByTestId('sineating-units-input')).toBeDisabled();
  });
});
