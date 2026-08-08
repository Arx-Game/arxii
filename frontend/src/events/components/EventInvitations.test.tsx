/**
 * EventInvitations (#3069) — the invitee-side RSVP surface: a viewer's own
 * pending persona invitation on an event gets Accept/Decline buttons.
 */
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import type { RenderOptions } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';
import { EventInvitations } from './EventInvitations';
import type { EventDetailData, EventInvitation } from '../types';

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function render(ui: ReactElement, options?: RenderOptions) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return rtlRender(ui, { wrapper: Wrapper, ...options });
}

const respondToInvitationMock = vi.fn(
  (): Promise<{ success: boolean; message: string }> =>
    Promise.resolve({ success: true, message: 'ok' })
);
const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();

vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}));

vi.mock('../queries', () => ({
  inviteToEvent: vi.fn(),
  removeInvitation: vi.fn(),
  respondToInvitation: (...args: unknown[]) =>
    respondToInvitationMock(...(args as [number, 'accept' | 'decline'])),
  searchPersonas: vi.fn(() => Promise.resolve([])),
  searchOrganizations: vi.fn(() => Promise.resolve([])),
  searchSocieties: vi.fn(() => Promise.resolve([])),
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'Alice',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 501,
        active_persona_id: null,
      },
    ],
  })),
}));

function invitation(overrides: Partial<EventInvitation>): EventInvitation {
  return {
    id: 1,
    target_type: 'persona',
    target_persona: null,
    target_organization: null,
    target_society: null,
    target_name: 'Bob',
    can_bring_guests: false,
    response: 'pending',
    responded_at: null,
    invited_at: '2026-08-01T00:00:00Z',
    ...overrides,
  };
}

function eventWithInvitations(invitations: EventInvitation[]): EventDetailData {
  return {
    id: 1,
    name: 'Masquerade',
    description: '',
    location: 1,
    location_name: 'Ballroom',
    status: 'scheduled',
    is_public: true,
    scheduled_real_time: '2026-08-10T20:00:00Z',
    scheduled_ic_time: null,
    time_phase: 'night',
    primary_host_name: 'Host',
    started_at: null,
    ended_at: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    hosts: [],
    invitations,
    modification: null,
    is_host: false,
    is_gm: false,
  };
}

describe('EventInvitations RSVP (#3069)', () => {
  beforeEach(() => {
    respondToInvitationMock.mockClear();
    toastSuccessMock.mockClear();
    toastErrorMock.mockClear();
    queryClient.clear();
  });

  it("shows Accept/Decline on the viewer's own pending persona invitation", () => {
    const event = eventWithInvitations([
      invitation({ id: 10, target_persona: 501, target_name: 'Alice' }),
    ]);
    render(<EventInvitations event={event} canManage={false} />);

    expect(screen.getByRole('button', { name: /accept/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /decline/i })).toBeInTheDocument();
  });

  it('does not show RSVP controls for an invitation targeting someone else', () => {
    const event = eventWithInvitations([
      invitation({ id: 11, target_persona: 999, target_name: 'Carol' }),
    ]);
    render(<EventInvitations event={event} canManage={false} />);

    expect(screen.queryByRole('button', { name: /accept/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /decline/i })).not.toBeInTheDocument();
  });

  it('accepting calls respondToInvitation with the accept verb and refetches', async () => {
    const event = eventWithInvitations([
      invitation({ id: 12, target_persona: 501, target_name: 'Alice' }),
    ]);
    render(<EventInvitations event={event} canManage={false} />);

    fireEvent.click(screen.getByRole('button', { name: /accept/i }));

    await waitFor(() => expect(respondToInvitationMock).toHaveBeenCalledWith(12, 'accept'));
    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalled());
  });

  it('declining calls respondToInvitation with the decline verb', async () => {
    const event = eventWithInvitations([
      invitation({ id: 13, target_persona: 501, target_name: 'Alice' }),
    ]);
    render(<EventInvitations event={event} canManage={false} />);

    fireEvent.click(screen.getByRole('button', { name: /decline/i }));

    await waitFor(() => expect(respondToInvitationMock).toHaveBeenCalledWith(13, 'decline'));
    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalled());
  });

  it('shows the resolved response instead of buttons once already responded', () => {
    const event = eventWithInvitations([
      invitation({ id: 14, target_persona: 501, target_name: 'Alice', response: 'accepted' }),
    ]);
    render(<EventInvitations event={event} canManage={false} />);

    expect(screen.getByText(/you accepted/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^accept$/i })).not.toBeInTheDocument();
  });

  it('never shows RSVP controls on a group (organization/society) invitation', () => {
    const event = eventWithInvitations([
      invitation({
        id: 15,
        target_type: 'organization',
        target_organization: 501,
        target_name: 'The Guild',
      }),
    ]);
    render(<EventInvitations event={event} canManage={false} />);

    expect(screen.queryByRole('button', { name: /accept/i })).not.toBeInTheDocument();
  });
});
