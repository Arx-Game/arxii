/**
 * #2049 — Invite flow component tests (InvitePicker + PendingInvitesSection).
 *
 * Verifies the invite picker renders for contract holders, the pending invites
 * section shows accept/decline, and the mutations are called with the right args.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import type { EntitySearchResult } from '@/components/EntitySearchField';

import type { PendingMissionInvite } from '../types';

const inviteMock = vi.fn();
const respondMock = vi.fn();

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useInviteToMission: () => ({
      mutate: inviteMock,
      isPending: false,
      error: null,
      isSuccess: false,
    }),
    useRespondToMissionInvite: () => ({ mutate: respondMock, isPending: false, error: null }),
  };
});

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    searchRoomCharacters: vi.fn(async (query: string): Promise<EntitySearchResult[]> => {
      if (!query) return [];
      return [
        { id: 42, name: 'Sidekick', hint: undefined },
        { id: 99, name: 'Wanderer', hint: undefined },
      ].filter((r) => r.name.toLowerCase().includes(query.toLowerCase()));
    }),
  };
});

import { InvitePicker } from '../components/InvitePicker';
import { PendingInvitesSection } from '../components/PendingInvitesSection';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

const INVITES: PendingMissionInvite[] = [
  { invite_id: 10, instance_id: 7, template_name: 'The Merchant Debt' },
  { invite_id: 11, instance_id: 9, template_name: 'Old Business' },
];

describe('InvitePicker', () => {
  beforeEach(() => {
    inviteMock.mockClear();
  });

  it('renders the search field and submit button', () => {
    render(withProviders(<InvitePicker instanceId={7} />));
    expect(screen.getByPlaceholderText(/Search characters/)).toBeInTheDocument();
    expect(screen.getByTestId('invite-submit')).toBeDisabled();
  });

  it('enables submit and sends the invite when a character is picked', async () => {
    const user = userEvent.setup();
    render(withProviders(<InvitePicker instanceId={7} />));
    const input = screen.getByPlaceholderText(/Search characters/);
    await user.type(input, 'side');
    // Click the search result
    const option = await screen.findByText('Sidekick');
    await user.click(option);
    // Submit button should now be enabled
    const submit = screen.getByTestId('invite-submit');
    expect(submit).not.toBeDisabled();
    await user.click(submit);
    expect(inviteMock).toHaveBeenCalledWith(
      { instanceId: 7, invitee_character_id: 42 },
      expect.anything()
    );
  });
});

describe('PendingInvitesSection', () => {
  beforeEach(() => {
    respondMock.mockClear();
  });

  it('renders nothing when there are no invites', () => {
    const { container } = render(withProviders(<PendingInvitesSection invites={[]} />));
    expect(container).toBeEmptyDOMElement();
  });

  it('renders one row per invite with accept/decline buttons', () => {
    render(withProviders(<PendingInvitesSection invites={INVITES} />));
    expect(screen.getByTestId('invite-10')).toHaveTextContent('The Merchant Debt');
    expect(screen.getByTestId('invite-11')).toHaveTextContent('Old Business');
    expect(screen.getByTestId('invite-accept-10')).toBeInTheDocument();
    expect(screen.getByTestId('invite-decline-10')).toBeInTheDocument();
  });

  it('dispatches accept with the right invite_id', async () => {
    const user = userEvent.setup();
    render(withProviders(<PendingInvitesSection invites={INVITES} />));
    await user.click(screen.getByTestId('invite-accept-11'));
    expect(respondMock).toHaveBeenCalledWith({ invite_id: 11, response: 'accept' });
  });

  it('dispatches decline with the right invite_id', async () => {
    const user = userEvent.setup();
    render(withProviders(<PendingInvitesSection invites={INVITES} />));
    await user.click(screen.getByTestId('invite-decline-10'));
    expect(respondMock).toHaveBeenCalledWith({ invite_id: 10, response: 'decline' });
  });
});
