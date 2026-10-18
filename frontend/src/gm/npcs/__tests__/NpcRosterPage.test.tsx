import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { toast } from 'sonner';
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (u: string, o?: RequestInit) => apiFetch(u, o),
}));

import { NpcRosterPage } from '../NpcRosterPage';

const row = {
  thumbnail_url: null,
  description: 'First paragraph.\n\nSecond paragraph.',
  owner_name: 'Warden Osk',
  borrow_audience: 'gms_and_guides',
};
const rows = [
  { ...row, id: 1, name: 'Captain Vael', lend_policy: 'on_request', can_borrow: true },
  { ...row, id: 2, name: 'The Masked Envoy', lend_policy: 'not_lent', can_borrow: false },
];

function ok(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NpcRosterPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('NpcRosterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiFetch.mockImplementation((url: string, opts?: RequestInit) =>
      opts?.method === 'POST' ? ok({}) : ok({ count: 2, results: rows })
    );
  });

  it('offers Ask to borrow only on a borrowable NPC, with the owner by name', async () => {
    renderPage();
    expect(await screen.findByText('Captain Vael')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Ask to borrow' })).toHaveLength(1);
    expect(screen.getAllByText(/Owner Warden Osk/)).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: 'Copy as a new NPC' })).toHaveLength(2);
  });

  it('posts the borrow request for the NPC', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Ask to borrow' }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('/api/roster/npcs/1/borrow/', { method: 'POST' })
    );
  });

  it('shows a refusal detail in a toast', async () => {
    apiFetch.mockImplementation((url: string, opts?: RequestInit) =>
      opts?.method === 'POST'
        ? Promise.resolve({
            ok: false,
            status: 400,
            json: () => Promise.resolve({ detail: 'Warden Osk does not lend that NPC.' }),
          })
        : ok({ count: 2, results: rows })
    );
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Ask to borrow' }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Warden Osk does not lend that NPC.')
    );
  });

  it('filters to lendable NPCs and posts the copy with the chosen name', async () => {
    renderPage();
    await screen.findByText('Captain Vael');
    await userEvent.click(screen.getByRole('button', { name: 'Lendable to me' }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('/api/roster/npcs/?lendable_to_me=true', undefined)
    );
    await userEvent.click(screen.getAllByRole('button', { name: 'Copy as a new NPC' })[0]);
    const input = screen.getByLabelText(/Name for the copy/);
    await userEvent.clear(input);
    await userEvent.type(input, 'Captain Vale');
    await userEvent.click(screen.getByRole('button', { name: 'Create copy' }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('/api/roster/npcs/1/copy-as-new/', {
        method: 'POST',
        body: JSON.stringify({ name: 'Captain Vale', as_template: false }),
      })
    );
  });

  it('shows only a message to an account that is not a GM or Guide', async () => {
    apiFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 403, json: () => Promise.resolve({ detail: 'no' }) })
    );
    renderPage();
    expect(
      await screen.findByText('You must be a GM or Guide to view this page.')
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Lendable to me' })).not.toBeInTheDocument();
  });

  it('loads the next page of the roster', async () => {
    apiFetch.mockImplementation((url: string) =>
      ok(
        url.includes('page=2')
          ? { count: 2, next: null, results: [rows[1]] }
          : { count: 2, next: 'http://x/?page=2', results: [rows[0]] }
      )
    );
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }));
    expect(await screen.findByText('The Masked Envoy')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument();
  });
});
