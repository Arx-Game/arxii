/**
 * RitualsListPage tests
 *
 * Covers: renders all rituals, loading state, empty state,
 * clicking Perform opens dialog, and dialog receives correct characterSheetId.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { RitualsListPage } from '../pages/RitualsListPage';
import type { RitualWithSchema } from '../types';

// ---------------------------------------------------------------------------
// Mock useRituals
// ---------------------------------------------------------------------------

const mockUseRituals = vi.fn();
vi.mock('@/rituals/queries', () => ({
  useRituals: () => mockUseRituals(),
}));

// ---------------------------------------------------------------------------
// Mock RitualPerformDialog — capture props for assertion
// ---------------------------------------------------------------------------

const mockDialogProps: { ritual?: RitualWithSchema; characterSheetId?: number } = {};
vi.mock('../components/RitualPerformDialog', () => ({
  RitualPerformDialog: (props: {
    ritual: RitualWithSchema;
    characterSheetId: number;
    open: boolean;
    onOpenChange: (open: boolean) => void;
  }) => {
    mockDialogProps.ritual = props.ritual;
    mockDialogProps.characterSheetId = props.characterSheetId;
    if (!props.open) return null;
    return (
      <div data-testid="mock-ritual-perform-dialog">
        <span data-testid="dialog-ritual-name">{props.ritual.name}</span>
        <span data-testid="dialog-character-sheet-id">{props.characterSheetId}</span>
        <button onClick={() => props.onOpenChange(false)}>Close dialog</button>
      </div>
    );
  },
}));

// ---------------------------------------------------------------------------
// Mock Redux auth — provide a character for characterSheetId
// ---------------------------------------------------------------------------

// Default state used by most tests (one available character with id 99).
const defaultAuthState = {
  auth: {
    account: {
      id: 1,
      username: 'testuser',
      available_characters: [
        {
          id: 99,
          name: 'Test Character',
          character_type: 'PC',
          roster_status: 'active',
          personas: [],
          last_location: null,
          portrait_url: null,
          currently_puppeted_in_session: true,
        },
      ],
      pending_applications: [],
    },
  },
};

// Mutable auth state so individual tests can override it.
let currentAuthState = defaultAuthState;

vi.mock('react-redux', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-redux')>();
  return {
    ...actual,
    useSelector: vi.fn((selector: (state: unknown) => unknown) => selector(currentAuthState)),
  };
});

// ---------------------------------------------------------------------------
// Sample ritual data
// ---------------------------------------------------------------------------

const ritual1: RitualWithSchema = {
  id: 1,
  name: 'Soul Tether',
  description: 'Binds a soul to this plane.',
  narrative_prose: 'The sineater reaches across the veil.',
  input_schema: null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

const ritual2: RitualWithSchema = {
  id: 2,
  name: 'Blood Rite',
  description: 'A dangerous ritual of binding.',
  narrative_prose: null,
  input_schema: null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RitualsListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDialogProps.ritual = undefined;
    mockDialogProps.characterSheetId = undefined;
    // Reset auth state to the default (one character with id 99) before each test.
    currentAuthState = defaultAuthState;
  });

  // 1. Renders all rituals from useRituals()
  it('renders all rituals returned by useRituals()', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [ritual1, ritual2] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getByText('Soul Tether')).toBeInTheDocument();
    expect(screen.getByText('Blood Rite')).toBeInTheDocument();
  });

  // 2. Loading state shows skeleton
  it('shows a loading indicator when isLoading is true', () => {
    mockUseRituals.mockReturnValue({
      isLoading: true,
      data: undefined,
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getAllByTestId('ritual-card-skeleton').length).toBeGreaterThan(0);
  });

  // 3. Empty state shows message
  it('shows empty-state message when results is empty', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getByText(/no rituals available/i)).toBeInTheDocument();
  });

  // 4. Clicking Perform opens the dialog
  it('clicking Perform button on a card opens the dialog', async () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [ritual1] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    // Dialog is not yet visible
    expect(screen.queryByTestId('mock-ritual-perform-dialog')).not.toBeInTheDocument();

    const performBtn = screen.getByRole('button', { name: /perform/i });
    await userEvent.click(performBtn);

    await waitFor(() => {
      expect(screen.getByTestId('mock-ritual-perform-dialog')).toBeInTheDocument();
    });
    expect(screen.getByTestId('dialog-ritual-name')).toHaveTextContent('Soul Tether');
  });

  // 5. Dialog receives the correct characterSheetId from auth context
  it('passes characterSheetId from the first available character to the dialog', async () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [ritual1] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    const performBtn = screen.getByRole('button', { name: /perform/i });
    await userEvent.click(performBtn);

    await waitFor(() => {
      expect(screen.getByTestId('dialog-character-sheet-id')).toHaveTextContent('99');
    });
    expect(mockDialogProps.characterSheetId).toBe(99);
  });

  // 6. No character: renders no-character empty state
  it('renders a no-character message when no character is puppeted', () => {
    // Override auth state: character exists but is not puppeted.
    currentAuthState = {
      auth: {
        account: {
          id: 1,
          username: 'testuser',
          available_characters: [
            {
              id: 99,
              name: 'Test Character',
              character_type: 'PC',
              roster_status: 'active',
              personas: [],
              last_location: null,
              portrait_url: null,
              currently_puppeted_in_session: false,
            },
          ],
          pending_applications: [],
        },
      },
    } as typeof defaultAuthState;

    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [ritual1] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getByText(/active character/i)).toBeInTheDocument();
  });
});
