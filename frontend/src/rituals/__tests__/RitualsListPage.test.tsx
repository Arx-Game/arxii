/**
 * RitualsListPage tests
 *
 * Covers: renders all rituals, loading state, empty state, section split
 * (authored vs known), clicking Perform/Manage opens the correct UI, and
 * the dialog receives the correct characterSheetId.
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
// The personal anima ritual's Perform button posts through this mutation (#4451).
const mockPerformMutate = vi.fn();
const mockPerformState: {
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  data?: { message?: string };
  error?: Error;
} = { isPending: false, isSuccess: false, isError: false };
vi.mock('@/rituals/queries', () => ({
  useRituals: () => mockUseRituals(),
  usePerformRitual: () => ({ mutate: mockPerformMutate, ...mockPerformState }),
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

// Mock RitualSceneActionDetailPanel to prevent rendering AnimaRitualEditDialog deps
vi.mock('../components/RitualSceneActionDetailPanel', () => ({
  RitualSceneActionDetailPanel: (props: { ritual: RitualWithSchema }) => (
    <div data-testid="mock-scene-action-detail-panel">
      <span data-testid="detail-panel-ritual-name">{props.ritual.name}</span>
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock Redux auth — provide a character for characterSheetId
// ---------------------------------------------------------------------------

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

const knownRitual: RitualWithSchema = {
  id: 1,
  name: 'Soul Tether',
  description: 'Binds a soul to this plane.',
  narrative_prose: 'The sineater reaches across the veil.',
  execution_kind: 'SERVICE',
  input_schema: null,
  client_hosted: false,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

const authoredRitual: RitualWithSchema = {
  id: 2,
  name: 'My Anima Ritual',
  description: 'A personal recovery rite.',
  narrative_prose: 'Breath in, breath out.',
  execution_kind: 'SCENE_ACTION',
  input_schema: null,
  client_hosted: false,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

const knownRitual2: RitualWithSchema = {
  id: 3,
  name: 'Blood Rite',
  description: 'A dangerous ritual.',
  narrative_prose: null,
  execution_kind: 'FLOW',
  input_schema: null,
  client_hosted: false,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

const clientHostedRitual: RitualWithSchema = {
  id: 4,
  name: 'Imbuing',
  description: 'Hosted by Thread Detail page.',
  narrative_prose: 'Weave threads into resonance.',
  execution_kind: 'FLOW',
  input_schema: null,
  client_hosted: true,
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
    currentAuthState = defaultAuthState;
    mockPerformState.isPending = false;
    mockPerformState.isSuccess = false;
    mockPerformState.isError = false;
    mockPerformState.data = undefined;
    mockPerformState.error = undefined;
  });

  // 1. Renders all rituals from useRituals()
  it('renders all rituals returned by useRituals()', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [knownRitual, knownRitual2] },
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

  // 4. Clicking Perform opens the dialog (non-SCENE_ACTION)
  it('clicking Perform button on a known ritual card opens the dialog', async () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [knownRitual] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.queryByTestId('mock-ritual-perform-dialog')).not.toBeInTheDocument();

    const performBtn = screen.getByRole('button', { name: /perform/i });
    await userEvent.click(performBtn);

    await waitFor(() => {
      expect(screen.getByTestId('mock-ritual-perform-dialog')).toBeInTheDocument();
    });
    expect(screen.getByTestId('dialog-ritual-name')).toHaveTextContent('Soul Tether');
  });

  // 5. Dialog receives the correct characterSheetId from auth context
  it('passes characterSheetId from the puppeted character to the dialog', async () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [knownRitual] },
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
      data: { results: [knownRitual] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getByText(/active character/i)).toBeInTheDocument();
  });

  // 7. SCENE_ACTION ritual shows both Perform and Manage (#4451)
  it('renders Perform and Manage buttons for SCENE_ACTION rituals', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [authoredRitual] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getByRole('button', { name: /manage/i })).toBeInTheDocument();
    expect(screen.getByTestId('ritual-perform-button')).toBeInTheDocument();
  });

  // 7b. Perform on the anima ritual posts it for the active character and opens no dialog
  it('performs the anima ritual straight from its card', async () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [authoredRitual] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    await userEvent.click(screen.getByTestId('ritual-perform-button'));

    expect(mockPerformMutate).toHaveBeenCalledWith({
      ritual_id: authoredRitual.id,
      character_sheet_id: expect.any(Number),
      kwargs: {},
    });
    expect(screen.queryByTestId('mock-ritual-perform-dialog')).not.toBeInTheDocument();
  });

  // 7c. The card tells the player what the roll did, or why it was refused
  it('shows the outcome line after the anima ritual is performed', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [authoredRitual] },
    });
    mockPerformState.isSuccess = true;
    mockPerformState.data = {
      message: 'You perform My Anima Ritual: Success. You recover 4 anima.',
    };

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getByTestId('ritual-perform-result')).toHaveTextContent(
      'You perform My Anima Ritual: Success. You recover 4 anima.'
    );
  });

  it('shows the refusal when the anima ritual cannot be performed', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [authoredRitual] },
    });
    mockPerformState.isError = true;
    mockPerformState.error = new Error("You've already performed your ritual in this scene.");

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getByRole('alert')).toHaveTextContent(
      "You've already performed your ritual in this scene."
    );
  });

  // 8. Mixed list: both sections render with headers
  it('renders two sections with headers when both authored and known rituals exist', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [authoredRitual, knownRitual] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.getByTestId('authored-rituals-section')).toBeInTheDocument();
    expect(screen.getByTestId('known-rituals-section')).toBeInTheDocument();
    expect(screen.getByText('Authored by you')).toBeInTheDocument();
    expect(screen.getByText('Known rituals')).toBeInTheDocument();
  });

  // 9. Only authored section: no section header rendered
  it('renders no section headers when only authored rituals exist', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [authoredRitual] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.queryByText('Authored by you')).not.toBeInTheDocument();
    expect(screen.queryByText('Known rituals')).not.toBeInTheDocument();
  });

  // 10. Clicking Manage on a SCENE_ACTION card expands the detail panel
  it('clicking Manage expands the scene action detail panel', async () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [authoredRitual] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    expect(screen.queryByTestId('mock-scene-action-detail-panel')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /manage/i }));

    await waitFor(() => {
      expect(screen.getByTestId('mock-scene-action-detail-panel')).toBeInTheDocument();
    });
    expect(screen.getByTestId('detail-panel-ritual-name')).toHaveTextContent('My Anima Ritual');
  });

  // 11. client_hosted rituals are filtered out from both sections
  it('filters out client_hosted rituals from display', () => {
    mockUseRituals.mockReturnValue({
      isLoading: false,
      data: { results: [knownRitual, clientHostedRitual, authoredRitual] },
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualsListPage />
      </Wrapper>
    );

    // Non-client_hosted rituals should appear
    expect(screen.getByText('Soul Tether')).toBeInTheDocument();
    expect(screen.getByText('My Anima Ritual')).toBeInTheDocument();

    // client_hosted ritual should NOT appear
    expect(screen.queryByText('Imbuing')).not.toBeInTheDocument();
  });
});
