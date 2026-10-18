/**
 * StandoffProfilePanel tests (#4441): the owner reads their profile, flips consent and picks
 * a cause and a drive; a locked profile disables every control and says why.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StandoffProfilePanel, type StandoffProfile } from './StandoffProfilePanel';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

function profile(overrides: Partial<StandoffProfile> = {}): StandoffProfile {
  return {
    opted_in: false,
    cause: 'none',
    cause_label: 'None',
    drives: [{ property_id: 7, name: 'Greedy', strength: 2, strength_label: 'Major' }],
    locked: false,
    locked_reason: '',
    causes: [
      { value: 'none', label: 'None' },
      { value: 'orders', label: 'Orders' },
    ],
    properties: [
      { value: '7', label: 'Greedy' },
      { value: '8', label: 'Loyal' },
    ],
    strengths: [
      { value: '1', label: 'Minor' },
      { value: '2', label: 'Major' },
    ],
    ...overrides,
  };
}

function reply(body: unknown, ok = true) {
  return Promise.resolve({ ok, json: () => Promise.resolve(body) });
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StandoffProfilePanel sheetId={42} />
    </QueryClientProvider>
  );
}

describe('StandoffProfilePanel', () => {
  beforeEach(() => apiFetch.mockReset());

  it('shows the profile and opts the character in', async () => {
    apiFetch.mockImplementation((_url: string, init?: { method?: string }) =>
      init?.method === 'POST' ? reply(profile({ opted_in: true })) : reply(profile())
    );
    renderPanel();
    const toggle = await screen.findByRole('switch', { name: 'Open to being read and pressed' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText('Greedy')).toBeInTheDocument();

    fireEvent.click(toggle);
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        '/api/character-sheets/42/standoff-profile/',
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ change: 'opt_in' }) })
      )
    );
    await waitFor(() => expect(toggle).toHaveAttribute('aria-checked', 'true'));
  });

  it('drops a drive', async () => {
    apiFetch.mockImplementation((_url: string, init?: { method?: string }) =>
      init?.method === 'POST' ? reply(profile({ drives: [] })) : reply(profile())
    );
    renderPanel();
    fireEvent.click(await screen.findByRole('button', { name: 'Drop' }));
    await waitFor(() => expect(screen.getByText('You have no drives.')).toBeInTheDocument());
  });

  it('disables every control while the profile is locked and says why', async () => {
    apiFetch.mockImplementation(() =>
      reply(profile({ locked: true, locked_reason: 'Your profile cannot change.' }))
    );
    renderPanel();
    expect(await screen.findByText('Your profile cannot change.')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Drop' })).toBeDisabled();
  });

  it('shows the refusal the server gives', async () => {
    apiFetch.mockImplementation((_url: string, init?: { method?: string }) =>
      init?.method === 'POST' ? reply({ detail: 'Not now.' }, false) : reply(profile())
    );
    renderPanel();
    fireEvent.click(await screen.findByRole('switch'));
    expect(await screen.findByText('Not now.')).toBeInTheDocument();
  });
});
