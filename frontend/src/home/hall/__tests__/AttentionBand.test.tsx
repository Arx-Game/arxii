/**
 * AttentionBand tests (#3412 slice 2) — the Hall's "Your Attention" band:
 * route-by-relatedness grouping (OOC group always present, per-character
 * groups only for characters with pending items), and respond flows firing
 * the correct endpoints.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AttentionBand } from '../AttentionBand';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { MyRosterEntry } from '@/roster/types';
import type { EventInvitation } from '@/events/types';
import type { OrganizationMembershipOffer } from '@/societies/types';

const mockUnreadMail = vi.fn(() => 0);
const mockMailQuery = vi.fn();
vi.mock('@/mail/queries', () => ({
  useUnreadMailCount: () => mockUnreadMail(),
  useMailQuery: () => mockMailQuery(),
}));

const mockFetchInvitations = vi.fn();
const mockRespondToInvitation = vi.fn().mockResolvedValue({ success: true, message: 'ok' });
vi.mock('@/events/queries', () => ({
  fetchMyEventInvitations: () => mockFetchInvitations(),
  respondToInvitation: (id: number, response: string) => mockRespondToInvitation(id, response),
}));

const mockOffersQuery = vi.fn();
const mockRespondOfferMutate = vi.fn();
vi.mock('@/societies/queries', () => ({
  usePendingMembershipOffersQuery: () => mockOffersQuery(),
  useRespondToMembershipOffer: () => ({ mutate: mockRespondOfferMutate, isPending: false }),
}));

const aria: MyRosterEntry = {
  id: 1,
  name: 'Aria',
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

const bianca: MyRosterEntry = {
  id: 2,
  name: 'Bianca',
  character_id: 43,
  profile_picture_url: null,
  primary_persona_id: 8,
  active_persona_id: 8,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

const invitation: EventInvitation = {
  id: 100,
  target_type: 'persona',
  target_persona: 7,
  target_organization: null,
  target_society: null,
  target_name: "The Lamplighter's Ball",
  can_bring_guests: false,
  response: 'pending',
  responded_at: null,
  invited_at: '2026-08-01T00:00:00Z',
};

const offer: OrganizationMembershipOffer = {
  id: 200,
  organization: 5,
  organization_name: 'The Compact',
  from_persona: 9,
  from_persona_name: 'Someone',
  to_persona: 8,
  to_persona_name: 'Bianca',
  kind: 'invite',
  status: 'pending',
  created_at: '2026-08-01T00:00:00Z',
  resolved_at: null,
};

function setDefaultMocks() {
  mockUnreadMail.mockReturnValue(0);
  mockMailQuery.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] } });
  mockFetchInvitations.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
  mockOffersQuery.mockReturnValue({ data: { count: 0, next: null, previous: null, results: [] } });
}

describe('AttentionBand', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('always renders the OOC group (Mail row) regardless of pending items', async () => {
    setDefaultMocks();
    renderWithProviders(<AttentionBand characters={[]} />);

    expect(screen.getByRole('link', { name: 'Mail' })).toHaveAttribute('href', '/profile/mail');
  });

  it('renders no boards row (review fix — no boards-index surface exists; a link to /game was a false affordance)', async () => {
    setDefaultMocks();
    renderWithProviders(<AttentionBand characters={[]} />);

    expect(screen.queryByText('The boards')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /boards/i })).not.toBeInTheDocument();
  });

  it('shows the unread-mail CountChip when there is unread mail', async () => {
    setDefaultMocks();
    mockUnreadMail.mockReturnValue(3);
    renderWithProviders(<AttentionBand characters={[]} />);

    expect(screen.getByTitle('3 unread messages')).toBeInTheDocument();
  });

  it('an empty mailbox reads "Empty, alas." and no character groups render', async () => {
    setDefaultMocks();
    renderWithProviders(<AttentionBand characters={[aria, bianca]} />);

    await waitFor(() => {
      expect(screen.getByText('Empty, alas.')).toBeInTheDocument();
    });
    expect(screen.queryByText('Aria')).not.toBeInTheDocument();
    expect(screen.queryByText('Bianca')).not.toBeInTheDocument();
  });

  it('mail with nothing unread reads "Nothing unread." and stays a live link', async () => {
    setDefaultMocks();
    mockMailQuery.mockReturnValue({ data: { count: 4, next: null, previous: null, results: [] } });
    renderWithProviders(<AttentionBand characters={[]} />);

    await waitFor(() => {
      expect(screen.getByText('Nothing unread.')).toBeInTheDocument();
    });
    expect(screen.getByRole('link', { name: 'Mail' })).toHaveAttribute('href', '/profile/mail');
  });

  it('shows neither mail state line while the mail list is still loading', async () => {
    setDefaultMocks();
    mockMailQuery.mockReturnValue({ data: undefined });
    renderWithProviders(<AttentionBand characters={[]} />);

    expect(screen.queryByText('Empty, alas.')).not.toBeInTheDocument();
    expect(screen.queryByText('Nothing unread.')).not.toBeInTheDocument();
  });

  it('groups a pending tidings count under its own character, not others', async () => {
    setDefaultMocks();
    renderWithProviders(
      <AttentionBand characters={[{ ...aria, unread_narrative_count: 2 }, bianca]} />
    );

    await waitFor(() => {
      expect(screen.getByText('Aria')).toBeInTheDocument();
    });
    expect(screen.getByTitle('2 tidings waiting')).toBeInTheDocument();
    expect(screen.queryByText('Bianca')).not.toBeInTheDocument();
  });

  it('groups a pending event invitation under the persona it targets', async () => {
    setDefaultMocks();
    mockFetchInvitations.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [invitation],
    });
    renderWithProviders(<AttentionBand characters={[aria, bianca]} />);

    expect(await screen.findByText('Aria')).toBeInTheDocument();
    expect(screen.getByText(/Lamplighter's Ball/)).toBeInTheDocument();
    expect(screen.queryByText('Bianca')).not.toBeInTheDocument();
  });

  it('accepting an invitation calls respondToInvitation with accept', async () => {
    setDefaultMocks();
    mockFetchInvitations.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [invitation],
    });
    const user = userEvent.setup();
    renderWithProviders(<AttentionBand characters={[aria]} />);

    await screen.findByText(/Lamplighter's Ball/);
    await user.click(screen.getByRole('button', { name: 'Accept' }));

    expect(mockRespondToInvitation).toHaveBeenCalledWith(100, 'accept');
  });

  it('declining an invitation calls respondToInvitation with decline', async () => {
    setDefaultMocks();
    mockFetchInvitations.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [invitation],
    });
    const user = userEvent.setup();
    renderWithProviders(<AttentionBand characters={[aria]} />);

    await screen.findByText(/Lamplighter's Ball/);
    await user.click(screen.getByRole('button', { name: 'Decline' }));

    expect(mockRespondToInvitation).toHaveBeenCalledWith(100, 'decline');
  });

  it('groups a pending org offer under the persona it targets', async () => {
    setDefaultMocks();
    mockOffersQuery.mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [offer] },
    });
    renderWithProviders(<AttentionBand characters={[aria, bianca]} />);

    await waitFor(() => {
      expect(screen.getByText('Bianca')).toBeInTheDocument();
    });
    expect(screen.getByText(/The Compact/)).toBeInTheDocument();
    expect(screen.queryByText('Aria')).not.toBeInTheDocument();
  });

  it('responding to an org offer calls the respond mutation with the offer id and response', async () => {
    setDefaultMocks();
    mockOffersQuery.mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [offer] },
    });
    const user = userEvent.setup();
    renderWithProviders(<AttentionBand characters={[bianca]} />);

    await waitFor(() => screen.getByText(/The Compact/));
    await user.click(screen.getByRole('button', { name: 'Accept' }));

    expect(mockRespondOfferMutate).toHaveBeenCalledWith({ offerId: 200, response: 'accept' });
  });
});
