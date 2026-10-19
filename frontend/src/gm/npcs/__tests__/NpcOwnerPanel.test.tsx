import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { NpcDetail } from '../npcFormApi';
import { NpcOwnerPanel } from '../NpcOwnerPanel';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (url: string, init?: RequestInit) => apiFetch(url, init),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const detail: NpcDetail = {
  id: 9,
  name: 'Captain Vael',
  thumbnail_url: null,
  description: '',
  owner_name: 'Ravenna',
  lend_policy: 'on_request',
  borrow_audience: 'gms',
  can_borrow: false,
  listed_on_npc_roster: true,
  notes_for_player: 'He is right about almost everything.',
  is_template: false,
  open_requests: [{ id: 5, status: 'requested' }],
  preferences: [],
  regard: [],
};

function ok(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <NpcOwnerPanel entryId={9} name="Captain Vael" />
    </QueryClientProvider>
  );
}

function bodyOf(call: unknown[]): unknown {
  return JSON.parse((call[1] as RequestInit).body as string);
}

describe('NpcOwnerPanel', () => {
  beforeEach(() => {
    apiFetch.mockReset().mockImplementation(() => ok(detail));
  });

  it('approves an open borrow request by loan id', async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        '/api/roster/npcs/answer/',
        expect.objectContaining({ method: 'POST' })
      )
    );
    const call = apiFetch.mock.calls.find((c) => c[0] === '/api/roster/npcs/answer/')!;
    expect(bodyOf(call)).toEqual({ loan_id: 5, accept: true });
  });

  it('declines an open borrow request', async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: 'Decline' }));
    await waitFor(() =>
      expect(apiFetch.mock.calls.some((c) => c[0].endsWith('/answer/'))).toBe(true)
    );
    const call = apiFetch.mock.calls.find((c) => c[0] === '/api/roster/npcs/answer/')!;
    expect(bodyOf(call)).toEqual({ loan_id: 5, accept: false });
  });

  it('shows no requests list when none are open', async () => {
    apiFetch.mockImplementation(() => ok({ ...detail, open_requests: [] }));
    renderPanel();
    await screen.findByLabelText('Who may play Captain Vael');
    expect(screen.queryByTestId('npc-borrow-request')).not.toBeInTheDocument();
  });

  it('saves edited settings through PATCH', async () => {
    renderPanel();
    await userEvent.selectOptions(
      await screen.findByLabelText('Who may play Captain Vael'),
      'without_asking'
    );
    await userEvent.selectOptions(screen.getByLabelText('Who may ask to borrow'), 'gms_and_guides');
    await userEvent.click(screen.getByLabelText('List on the NPC roster'));
    const notes = screen.getByLabelText('Notes for whoever plays Captain Vael');
    expect(notes).toHaveAttribute('rows', '8');
    await userEvent.clear(notes);
    await userEvent.type(notes, 'Plays him warm.');
    await userEvent.click(screen.getByRole('button', { name: 'Save settings' }));
    await waitFor(() =>
      expect(apiFetch.mock.calls.some((c) => (c[1] as RequestInit)?.method === 'PATCH')).toBe(true)
    );
    const call = apiFetch.mock.calls.find((c) => (c[1] as RequestInit)?.method === 'PATCH')!;
    expect(call[0]).toBe('/api/roster/npcs/9/');
    expect(bodyOf(call)).toEqual({
      listed_on_npc_roster: false,
      lend_policy: 'without_asking',
      borrow_audience: 'gms_and_guides',
      notes_for_player: 'Plays him warm.',
    });
  });
});
