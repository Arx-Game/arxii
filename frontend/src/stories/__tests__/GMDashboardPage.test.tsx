/**
 * GMDashboardPage Tests (#2004)
 *
 * Smoke tests: renders without crashing, shows the dashboard sections,
 * and renders the 403 not-a-GM error state.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { GMDashboardPage } from '../pages/GMDashboardPage';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

vi.mock('@/store/hooks', () => ({
  useAccount: vi.fn(() => null),
}));

// Radix Select, for any picker on the page. jsdom can't drive Radix's real
// pointer-capture popover, so this is stubbed as a plain native <select> (the
// established pattern; see boundaries/__tests__/PlayerBoundaryFormDialog.test.tsx).
vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: ReactNode;
  }) => (
    <select value={value} onChange={(e) => onValueChange?.(e.target.value)}>
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

// The "Waiting on you" strip (#4188) reads the attention counts through its
// own hook; mocked directly so it never shifts the ordered apiFetch mocks
// below. `mockAttention` is overridden per test; the default is all zeros.
const ZERO_ATTENTION = {
  story_offers: 0,
  crossover_invites: 0,
  sheet_update_requests: 0,
  claims_to_approve: 0,
  my_claims: 0,
  session_requests: 0,
  total: 0,
};
const mockAttention = vi.fn((_enabled: boolean) => ({ data: ZERO_ATTENTION }));
vi.mock('@/gm/queries', () => ({
  gmKeys: { attention: ['gm-attention'] },
  useGMAttention: (enabled: boolean) => mockAttention(enabled),
}));

// The My NPCs block (#3426) fetches the account's roster entries; mock the
// query directly so it never competes with the order-dependent apiFetch mocks.
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({ data: [] })),
}));

// The new-NPC form (#4418) reads its own templates and dispatches its own mint;
// it is covered by gm/npcs/__tests__/NpcForm.test.tsx, so it is stubbed here and
// never shifts the ordered apiFetch mocks below.
vi.mock('@/gm/npcs/NpcOwnerPanel', () => ({
  NpcOwnerPanel: ({ entryId }: { entryId: number }) => (
    <div data-testid="npc-owner-panel" data-entry={entryId} />
  ),
}));

vi.mock('@/gm/npcs/NpcForm', () => ({
  NpcForm: ({ mode, sceneId }: { mode?: string; sceneId?: number | null }) => (
    <div data-testid="npc-form" data-mode={mode} data-scene={String(sceneId)} />
  ),
}));

// GMPromptFilterCard (#4101) fetches its own settings on mount; mock its
// hooks directly for the same reason — this page's tests assert on an
// ordered sequence of apiFetch calls (dashboard, dispatch) that
// the card's own fetch would otherwise shift. GMPromptFilterCard's own
// behaviour is covered by GMPromptFilterCard.test.tsx.
vi.mock('@/scenes/gmPromptQueries', () => ({
  useGMPromptFilters: vi.fn(() => ({ data: [], isLoading: false, isError: false, error: null })),
  useSetGMPromptFilter: vi.fn(() => ({ mutate: vi.fn(), isError: false, error: null })),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { useAccount } from '@/store/hooks';

function withProviders(children: ReactNode, path = '/gm/dashboard') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const mockDashboard = {
  episodes_ready_to_run: [],
  pending_agm_claims: [],
  assigned_session_requests: [],
  waiting_for_gm: [],
  open_group_requests: [],
  my_tables: [{ id: 1, name: 'Test Table', membership_count: 3 }],
  pending_story_offers: [],
  evidence_summary: {
    level: 'gm',
    stories_running: 2,
    beats_completed_by_risk: {},
    last_active_at: '2026-07-08T00:00:00Z',
  },
  pending_applications: 3,
  open_invites: 2,
};

describe('GMDashboardPage', () => {
  beforeEach(() => {
    mockAttention.mockReset();
    mockAttention.mockReturnValue({ data: ZERO_ATTENTION });
  });

  it('renders dashboard sections on success', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDashboard),
    } as Response);

    render(withProviders(<GMDashboardPage />));

    await waitFor(() => {
      expect(screen.getByText('GM Dashboard')).toBeInTheDocument();
    });
    expect(screen.getByText('Test Table')).toBeInTheDocument();
    expect(screen.getByText('gm')).toBeInTheDocument();
  });

  it('renders the pending applications and open invites tiles, linking to /tables (#3268)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDashboard),
    } as Response);

    render(withProviders(<GMDashboardPage />));

    await waitFor(() => {
      expect(screen.getByText('GM Dashboard')).toBeInTheDocument();
    });

    const applicationsTile = screen.getByTestId('pending-applications-tile');
    expect(applicationsTile).toHaveTextContent('3');
    expect(applicationsTile).toHaveAttribute('href', '/tables');

    const invitesTile = screen.getByTestId('open-invites-tile');
    expect(invitesTile).toHaveTextContent('2');
    expect(invitesTile).toHaveAttribute('href', '/tables');
  });

  it('opens on a "Waiting on you" strip whose non-zero rows link to their pages (#4188)', async () => {
    mockAttention.mockReturnValue({
      data: {
        story_offers: 2,
        crossover_invites: 1,
        sheet_update_requests: 3,
        claims_to_approve: 1,
        my_claims: 0,
        session_requests: 4,
        total: 11,
      },
    });
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDashboard),
    } as Response);

    render(withProviders(<GMDashboardPage />));

    const strip = await screen.findByTestId('waiting-on-you');
    expect(strip).toHaveTextContent('Waiting on you');
    // Only asked once the dashboard answered, the proof the viewer is a GM.
    expect(mockAttention).toHaveBeenLastCalledWith(true);

    const row = (key: string) => screen.getByTestId(`waiting-${key}`);
    expect(row('story_offers')).toHaveAttribute('href', '/stories/my-offers');
    expect(row('story_offers')).toHaveTextContent('2');
    expect(row('crossover_invites')).toHaveAttribute('href', '/crossover/inbox');
    expect(row('sheet_update_requests')).toHaveAttribute('href', '/gm/update-requests');
    expect(row('claims_to_approve')).toHaveAttribute('href', '/stories/gm-queue');
    expect(row('session_requests')).toHaveAttribute('href', '/stories/gm-queue');
    expect(row('session_requests')).toHaveTextContent('4');
    // A zero row is muted and unlinked.
    expect(row('my_claims')).not.toHaveAttribute('href');
    expect(row('my_claims')).toHaveTextContent('0');

    // The strip replaced the offers section and the claims/sessions tiles.
    expect(screen.queryByText(/Pending Story Offers/)).not.toBeInTheDocument();
    expect(screen.queryByText('Pending AGM claims')).not.toBeInTheDocument();
    expect(screen.queryByText('Assigned sessions')).not.toBeInTheDocument();
    expect(screen.getByText('Episodes ready to run')).toBeInTheDocument();
  });

  it('renders a strip of zeros with no links when nothing is waiting (#4188)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDashboard),
    } as Response);

    render(withProviders(<GMDashboardPage />));

    const strip = await screen.findByTestId('waiting-on-you');
    expect(strip.querySelectorAll('a')).toHaveLength(0);
    expect(screen.getByTestId('waiting-my_claims')).toHaveTextContent('My claims');
  });

  it('renders not-a-GM message on 403', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: false,
      status: 403,
    } as Response);

    render(withProviders(<GMDashboardPage />));

    await waitFor(() => {
      expect(screen.getByText(/You must be a GM/i)).toBeInTheDocument();
    });
  });

  it('renders the open group requests section (#2119)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          ...mockDashboard,
          open_group_requests: [
            {
              request_id: 1,
              covenant_id: 5,
              covenant_name: 'The Open Circle',
              message: 'Seeking a GM!',
              created_at: '2026-07-08T00:00:00Z',
            },
          ],
        }),
    } as Response);

    render(withProviders(<GMDashboardPage />));

    await waitFor(() => {
      expect(screen.getByText('Open Group Requests (1)')).toBeInTheDocument();
    });
    expect(screen.getByText('The Open Circle')).toBeInTheDocument();
    expect(screen.getByTestId('claim-group-request-button')).toBeInTheDocument();
  });
});

/**
 * Claim rejection (#3155) — `DispatchActionView` resolves HTTP 200 even for a
 * business-rule rejection (e.g. someone else already claimed the request).
 * Before the fix, `claimGroupStoryRequest` only checked `res.ok`, so a
 * rejected claim read as a resolved Promise: `onSuccess` fired, the dashboard
 * was refetched, and the server's rejection reason was never shown.
 */
describe('GMDashboardPage claim rejection (#3155)', () => {
  const dashboardWithOneRequest = {
    episodes_ready_to_run: [],
    pending_agm_claims: [],
    assigned_session_requests: [],
    waiting_for_gm: [],
    open_group_requests: [
      {
        request_id: 1,
        covenant_id: 5,
        covenant_name: 'The Open Circle',
        message: 'Seeking a GM!',
        created_at: '2026-07-08T00:00:00Z',
      },
    ],
    my_tables: [],
    pending_story_offers: [],
    evidence_summary: {
      level: 'gm',
      stories_running: 0,
      beats_completed_by_risk: {},
      last_active_at: null,
    },
  };

  beforeEach(() => {
    vi.mocked(useAccount).mockReturnValue({
      available_characters: [{ id: 42, currently_puppeted_in_session: true }],
    } as unknown as ReturnType<typeof useAccount>);
  });

  it('surfaces the server rejection reason instead of treating the claim as done', async () => {
    const user = userEvent.setup();
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(dashboardWithOneRequest),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            backend: 'registry',
            deferred: false,
            success: false,
            message: 'Someone else already claimed this request.',
            data: null,
          }),
      } as Response);

    render(withProviders(<GMDashboardPage />));

    const claimButton = await screen.findByTestId('claim-group-request-button');
    await user.click(claimButton);

    expect(
      await screen.findByText('Someone else already claimed this request.')
    ).toBeInTheDocument();
    // The refused claim must not have been treated as a resolved success —
    // the button returns to its normal (non-"Claiming…") label once the
    // mutation settles into its error state rather than a success refetch.
    expect(screen.getByTestId('claim-group-request-button')).toHaveTextContent('Claim');
  });
});

/** The My NPCs block (#4418): the new-NPC form in quick mode, and the NPC roster's door. */
describe('GMDashboardPage new NPC form (#4418)', () => {
  it('mounts the NPC form in quick mode and links to the NPC roster', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDashboard),
    } as Response);

    render(withProviders(<GMDashboardPage />));

    const form = await screen.findByTestId('npc-form');
    expect(form).toHaveAttribute('data-mode', 'quick');
    expect(form).toHaveAttribute('data-scene', 'null');
    expect(screen.getByRole('link', { name: 'NPC roster' })).toHaveAttribute('href', '/gm/npcs');
    expect(screen.queryByRole('button', { name: 'Mint Story NPC' })).not.toBeInTheDocument();
  });

  it("passes the cast panel's scene to the form", async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDashboard),
    } as Response);

    render(withProviders(<GMDashboardPage />, '/gm/dashboard?scene=4'));

    expect(await screen.findByTestId('npc-form')).toHaveAttribute('data-scene', '4');
  });
});

/** The owner's panel (#4418): only an NPC the viewer owns can be managed, not a borrowed one. */
describe('GMDashboardPage owner panel (#4418)', () => {
  it('offers Manage on an owned NPC and not on a borrowed one', async () => {
    const { useMyRosterEntriesQuery } = await import('@/roster/queries');
    vi.mocked(useMyRosterEntriesQuery).mockReturnValue({
      data: [
        { id: 9, name: 'Captain Vael', roster_type: 'NPC', loan: null },
        { id: 10, name: 'Sergeant Mira', roster_type: 'NPC', loan: { id: 4 } },
      ],
    } as unknown as ReturnType<typeof useMyRosterEntriesQuery>);
    vi.mocked(apiFetch).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockDashboard),
    } as Response);

    render(withProviders(<GMDashboardPage />));

    await userEvent.click(await screen.findByRole('button', { name: 'Manage Captain Vael' }));
    expect(screen.getByTestId('npc-owner-panel')).toHaveAttribute('data-entry', '9');
    expect(screen.queryByRole('button', { name: 'Manage Sergeant Mira' })).not.toBeInTheDocument();
  });
});
