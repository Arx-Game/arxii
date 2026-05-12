/**
 * Smoke tests for:
 *   - RitualSessionInboxPage
 *   - RitualSessionDetailPage
 *   - RitualSessionDraftDialog
 *   - RitualSessionResponseDialog
 *
 * Verifies each component mounts without crashing given mocked react-query responses.
 * Deep integration through react-query internals is avoided — just mount and assert
 * basic content.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { RitualSessionInboxPage } from '../pages/RitualSessionInboxPage';
import { RitualSessionDetailPage } from '../pages/RitualSessionDetailPage';
import { RitualSessionDraftDialog } from '../components/RitualSessionDraftDialog';
import { RitualSessionResponseDialog } from '../components/RitualSessionResponseDialog';
import type { RitualWithSchema } from '../types';
import type { RitualSessionList, RitualSessionDetail } from '../api';

// ---------------------------------------------------------------------------
// Mock react-query hooks (rituals)
// ---------------------------------------------------------------------------

const mockUseRitualSessionInbox = vi.fn();
const mockUseRitualSessionDetail = vi.fn();
const mockUseDraftRitualSession = vi.fn();
const mockUseAcceptRitualSession = vi.fn();
const mockUseDeclineRitualSession = vi.fn();
const mockUseFireRitualSession = vi.fn();
const mockUseCancelRitualSession = vi.fn();

vi.mock('@/rituals/queries', () => ({
  useRitualSessionInbox: () => mockUseRitualSessionInbox(),
  useRitualSessionDetail: () => mockUseRitualSessionDetail(),
  useDraftRitualSession: () => mockUseDraftRitualSession(),
  useAcceptRitualSession: () => mockUseAcceptRitualSession(),
  useDeclineRitualSession: () => mockUseDeclineRitualSession(),
  useFireRitualSession: () => mockUseFireRitualSession(),
  useCancelRitualSession: () => mockUseCancelRitualSession(),
}));

// Mock auth
const mockAuthState = {
  auth: {
    account: {
      id: 1,
      username: 'testuser',
      available_characters: [
        {
          id: 42,
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

vi.mock('react-redux', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-redux')>();
  return {
    ...actual,
    useSelector: vi.fn((selector: (state: unknown) => unknown) => selector(mockAuthState)),
  };
});

// Mock searchPersonas (used by InviteePicker in DraftDialog)
vi.mock('@/events/queries', () => ({
  searchPersonas: vi.fn(() => Promise.resolve([])),
}));

// ---------------------------------------------------------------------------
// Sample data
// ---------------------------------------------------------------------------

const sampleSessionList: RitualSessionList = {
  id: 1,
  ritual_name: 'Formation of the Pact',
  participation_rule: 'FORMATION',
  initiator_name: 'Aldric the Bold',
  proposed_terms: 'A sacred bond between warriors.',
  expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  created_at: new Date().toISOString(),
  participant_count: { INVITED: 1 },
  my_role: 'INVITEE',
};

const sampleSessionDetail: RitualSessionDetail = {
  id: 1,
  ritual_name: 'Formation of the Pact',
  participation_rule: 'FORMATION',
  initiator_id: 99,
  initiator_name: 'Aldric the Bold',
  proposed_terms: 'A sacred bond between warriors.',
  session_kwargs: {},
  expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  created_at: new Date().toISOString(),
  participants: [
    {
      character_sheet_id: 99,
      character_name: 'Aldric the Bold',
      state: 'ACCEPTED',
      responded_at: new Date().toISOString(),
    },
    {
      character_sheet_id: 42,
      character_name: 'Test Character',
      state: 'INVITED',
      responded_at: null,
    },
  ],
  session_references: '',
};

const sampleRitual: RitualWithSchema = {
  id: 10,
  name: 'Covenant Formation',
  description: 'Forms a covenant.',
  narrative_prose: 'The pact is sealed.',
  execution_kind: 'SESSION',
  input_schema: { fields: [] },
  client_hosted: false,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

// ---------------------------------------------------------------------------
// Wrapper helpers
// ---------------------------------------------------------------------------

function createWrapper(initialRoute = '/') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialRoute]}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function createDetailWrapper(sessionId: number) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/rituals/sessions/${sessionId}`]}>
          <Routes>
            <Route path="/rituals/sessions/:id" element={children} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Default mutation mock
// ---------------------------------------------------------------------------

const idleMutation = {
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  error: null,
  reset: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests: RitualSessionInboxPage
// ---------------------------------------------------------------------------

describe('RitualSessionInboxPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading skeletons while fetching', () => {
    mockUseRitualSessionInbox.mockReturnValue({ data: undefined, isLoading: true });

    const Wrapper = createWrapper('/rituals/sessions/inbox');
    render(
      <Wrapper>
        <RitualSessionInboxPage />
      </Wrapper>
    );

    expect(screen.getAllByTestId('inbox-row-skeleton').length).toBeGreaterThan(0);
  });

  it('renders empty state when inbox is empty', () => {
    mockUseRitualSessionInbox.mockReturnValue({ data: [], isLoading: false });

    const Wrapper = createWrapper('/rituals/sessions/inbox');
    render(
      <Wrapper>
        <RitualSessionInboxPage />
      </Wrapper>
    );

    expect(screen.getByTestId('inbox-empty')).toBeInTheDocument();
    expect(screen.getByText(/no pending invitations/i)).toBeInTheDocument();
  });

  it('renders invitation rows when inbox has sessions', () => {
    mockUseRitualSessionInbox.mockReturnValue({
      data: [sampleSessionList],
      isLoading: false,
    });

    const Wrapper = createWrapper('/rituals/sessions/inbox');
    render(
      <Wrapper>
        <RitualSessionInboxPage />
      </Wrapper>
    );

    expect(screen.getByTestId('inbox-list')).toBeInTheDocument();
    expect(screen.getByText('Formation of the Pact')).toBeInTheDocument();
    expect(screen.getByText(/Aldric the Bold/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /respond/i })).toBeInTheDocument();
  });

  it('renders the page heading', () => {
    mockUseRitualSessionInbox.mockReturnValue({ data: [], isLoading: false });

    const Wrapper = createWrapper('/rituals/sessions/inbox');
    render(
      <Wrapper>
        <RitualSessionInboxPage />
      </Wrapper>
    );

    expect(screen.getByRole('heading', { name: /ritual invitations/i })).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: RitualSessionDetailPage
// ---------------------------------------------------------------------------

describe('RitualSessionDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseFireRitualSession.mockReturnValue(idleMutation);
    mockUseCancelRitualSession.mockReturnValue(idleMutation);
    mockUseAcceptRitualSession.mockReturnValue(idleMutation);
    mockUseDeclineRitualSession.mockReturnValue(idleMutation);
  });

  it('renders loading skeleton while fetching', () => {
    mockUseRitualSessionDetail.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });

    const Wrapper = createDetailWrapper(1);
    render(
      <Wrapper>
        <RitualSessionDetailPage />
      </Wrapper>
    );

    expect(screen.getByTestId('detail-skeleton')).toBeInTheDocument();
  });

  it('renders error state on fetch failure', () => {
    mockUseRitualSessionDetail.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    });

    const Wrapper = createDetailWrapper(1);
    render(
      <Wrapper>
        <RitualSessionDetailPage />
      </Wrapper>
    );

    expect(screen.getByTestId('detail-error')).toBeInTheDocument();
  });

  it('renders session detail with participants', () => {
    mockUseRitualSessionDetail.mockReturnValue({
      data: sampleSessionDetail,
      isLoading: false,
      isError: false,
    });

    const Wrapper = createDetailWrapper(1);
    render(
      <Wrapper>
        <RitualSessionDetailPage />
      </Wrapper>
    );

    expect(screen.getByTestId('session-ritual-name')).toHaveTextContent('Formation of the Pact');
    expect(screen.getByTestId('participants-list')).toBeInTheDocument();
    // Aldric appears in both the header and the participants list — verify at least one exists
    expect(screen.getAllByText(/Aldric the Bold/).length).toBeGreaterThan(0);
  });

  it('shows Respond button for invited non-initiator participant', () => {
    mockUseRitualSessionDetail.mockReturnValue({
      data: sampleSessionDetail,
      isLoading: false,
      isError: false,
    });

    // Auth user's character sheet id is 42 (invited participant, not initiator 99)
    const Wrapper = createDetailWrapper(1);
    render(
      <Wrapper>
        <RitualSessionDetailPage />
      </Wrapper>
    );

    expect(screen.getByTestId('respond-button')).toBeInTheDocument();
  });

  it('shows Fire/Cancel buttons for initiator', () => {
    // Change session so auth user's sheet (42) is the initiator
    const initiatorSession: RitualSessionDetail = {
      ...sampleSessionDetail,
      initiator_id: 42,
      participants: [
        {
          character_sheet_id: 42,
          character_name: 'Test Character',
          state: 'ACCEPTED',
          responded_at: new Date().toISOString(),
        },
        {
          character_sheet_id: 99,
          character_name: 'Aldric',
          state: 'ACCEPTED',
          responded_at: new Date().toISOString(),
        },
      ],
    };

    mockUseRitualSessionDetail.mockReturnValue({
      data: initiatorSession,
      isLoading: false,
      isError: false,
    });

    const Wrapper = createDetailWrapper(1);
    render(
      <Wrapper>
        <RitualSessionDetailPage />
      </Wrapper>
    );

    expect(screen.getByTestId('fire-button')).toBeInTheDocument();
    expect(screen.getByTestId('cancel-button')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: RitualSessionDraftDialog
// ---------------------------------------------------------------------------

describe('RitualSessionDraftDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseDraftRitualSession.mockReturnValue(idleMutation);
  });

  it('renders without crashing when open', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RitualSessionDraftDialog
            ritual={sampleRitual}
            characterSheetId={42}
            open={true}
            onOpenChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText('Covenant Formation')).toBeInTheDocument();
    expect(screen.getByTestId('proposed-terms-input')).toBeInTheDocument();
    expect(screen.getByTestId('invitee-search-input')).toBeInTheDocument();
  });

  it('does not render dialog content when closed', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RitualSessionDraftDialog
            ritual={sampleRitual}
            characterSheetId={42}
            open={false}
            onOpenChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.queryByTestId('proposed-terms-input')).not.toBeInTheDocument();
  });

  it('submit button is disabled when no invitees are selected', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RitualSessionDraftDialog
            ritual={sampleRitual}
            characterSheetId={42}
            open={true}
            onOpenChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByTestId('draft-submit-button')).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Tests: RitualSessionResponseDialog
// ---------------------------------------------------------------------------

describe('RitualSessionResponseDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAcceptRitualSession.mockReturnValue(idleMutation);
    mockUseDeclineRitualSession.mockReturnValue(idleMutation);
  });

  it('renders Accept and Decline buttons when open', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RitualSessionResponseDialog
            session={sampleSessionDetail}
            participantId={42}
            open={true}
            onOpenChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByTestId('accept-button')).toBeInTheDocument();
    expect(screen.getByTestId('decline-button')).toBeInTheDocument();
  });

  it('shows ritual name and initiator in dialog header', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RitualSessionResponseDialog
            session={sampleSessionDetail}
            participantId={42}
            open={true}
            onOpenChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.getByText(/Formation of the Pact/)).toBeInTheDocument();
    expect(screen.getByText(/Aldric the Bold/)).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RitualSessionResponseDialog
            session={sampleSessionDetail}
            participantId={42}
            open={false}
            onOpenChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(screen.queryByTestId('accept-button')).not.toBeInTheDocument();
  });

  it('calls decline mutation on Decline click', async () => {
    const mockDecline = { ...idleMutation, mutate: vi.fn() };
    mockUseDeclineRitualSession.mockReturnValue(mockDecline);

    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <RitualSessionResponseDialog
            session={sampleSessionDetail}
            participantId={42}
            open={true}
            onOpenChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await userEvent.click(screen.getByTestId('decline-button'));

    await waitFor(() => {
      expect(mockDecline.mutate).toHaveBeenCalledWith(
        sampleSessionDetail.id,
        expect.objectContaining({ onSuccess: expect.any(Function) })
      );
    });
  });
});
