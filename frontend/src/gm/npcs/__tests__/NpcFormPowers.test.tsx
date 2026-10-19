import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/roster/useBrowsingIdentity', () => ({
  useBrowsingIdentity: () => ({ entryId: 1, name: 'Warden Osk', entry: { character_id: 7 } }),
}));
vi.mock('@/roster/queries', () => ({ useMyRosterEntriesQuery: () => ({ data: [] }) }));
const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (url: string, init?: RequestInit) => apiFetch(url, init),
}));

import { NpcForm } from '../NpcForm';

const NEW_ENTRY = 55;
const SHEET = 90;

// The shape of NPCPowerOptions (generated), with the lists the pickers show.
const OPTIONS = {
  paths: [{ id: 3, name: 'Wayfarer' }],
  traditions: [{ id: 4, name: 'Hedge' }],
  gifts: [{ id: 5, name: 'Embers' }],
  techniques: [
    { id: 6, name: 'Spark' },
    { id: 7, name: 'Kindle' },
  ],
  resonances: [{ id: 8, name: 'Warmth' }],
  stats: [{ id: 11, name: 'Presence' }],
  skills: [{ id: 12, name: 'Persuasion' }],
  technique_limit: 1,
  all_stats: [
    { id: 11, name: 'Presence' },
    { id: 13, name: 'Strength' },
  ],
  all_skills: [{ id: 12, name: 'Persuasion' }],
};

let hasGift = false;
let failOn: string | null = null;

function ok(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function route(url: string, init?: RequestInit) {
  if (url.startsWith('/api/roster/npcs/power-options/')) return ok(OPTIONS);
  if (url.endsWith('/dispatch/')) {
    return ok({ success: true, message: 'Minted.', data: { roster_entry_id: NEW_ENTRY } });
  }
  if (url === `/api/roster/entries/${NEW_ENTRY}/`) {
    return ok({ id: NEW_ENTRY, character: { id: SHEET, name: 'Vael' } });
  }
  if (url === `/api/character-sheets/${SHEET}/` && !init?.method) {
    return ok({ staff_edit: { rows: { has_gift: hasGift } } });
  }
  if (init?.method && failOn && url.endsWith(`/${failOn}/`)) {
    return Promise.resolve({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ detail: 'refused' }),
    });
  }
  if (init?.method) return ok({});
  return ok({ count: 0, next: null, results: [] });
}

function writes() {
  return apiFetch.mock.calls
    .filter(([, init]) => init?.method && init.method !== 'GET')
    .map(([url, init]) => ({
      method: init.method as string,
      url: url as string,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    }));
}

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NpcForm mode="detailed" sceneId={null} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function fillPowers(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Name'), 'Vael');
  await user.selectOptions(await screen.findByLabelText('Path'), '3');
  await user.type(screen.getByLabelText('Path level'), '2');
  await user.selectOptions(screen.getByLabelText('Tradition'), '4');
  await user.selectOptions(await screen.findByLabelText('Gift'), '5');
  await user.selectOptions(await screen.findByLabelText('Resonance'), '8');
  await user.click(await screen.findByLabelText('Spark'));
  await user.selectOptions(screen.getByLabelText('Anima stat'), '11');
  await user.selectOptions(screen.getByLabelText('Anima skill'), '12');
  await user.type(screen.getByLabelText('Stats: Strength'), '4');
  await user.type(screen.getByLabelText('Skills: Persuasion'), '60');
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(route);
  hasGift = false;
  failOn = null;
});

describe('NpcForm Powers', () => {
  it('shows the path, magic and override pickers, not an empty section', async () => {
    renderForm();
    expect(await screen.findByLabelText('Path')).toBeInTheDocument();
    expect(screen.getByLabelText('Tradition')).toBeInTheDocument();
    expect(screen.getByLabelText('Stats: Strength')).toBeInTheDocument();
    expect(screen.getByLabelText('Skills: Persuasion')).toBeInTheDocument();
  });

  it('names what magic still needs until every pick is made', async () => {
    const user = userEvent.setup();
    renderForm();
    await user.selectOptions(await screen.findByLabelText('Tradition'), '4');
    expect(screen.getByTestId('powers-magic-incomplete')).toHaveTextContent(
      'gift, a technique, resonance, anima stat, anima skill'
    );
  });

  it('applies the typed powers after the mint: path, magic, stats, skills', async () => {
    const user = userEvent.setup();
    renderForm();
    await fillPowers(user);
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    await waitFor(() => expect(writes().length).toBeGreaterThanOrEqual(6));
    expect(writes().slice(1)).toEqual([
      { method: 'PATCH', url: `/api/character-sheets/${SHEET}/staff-path/`, body: { path: 3 } },
      { method: 'PATCH', url: `/api/character-sheets/${SHEET}/staff-path/`, body: { level: 2 } },
      {
        method: 'POST',
        url: `/api/character-sheets/${SHEET}/staff-magic/`,
        body: {
          tradition: 4,
          gift: 5,
          techniques: [6],
          resonance: 8,
          anima_stat: 11,
          anima_skill: 12,
        },
      },
      {
        method: 'PATCH',
        url: `/api/character-sheets/${SHEET}/staff-stats/`,
        body: { stats: { 13: 4 } },
      },
      {
        method: 'PATCH',
        url: `/api/character-sheets/${SHEET}/staff-skills/`,
        body: { skills: { 12: 60 } },
      },
    ]);
  });

  it('names the failed part and retries without minting again', async () => {
    const user = userEvent.setup();
    failOn = 'staff-stats';
    renderForm();
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.type(await screen.findByLabelText('Stats: Strength'), '4');
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));
    expect(await screen.findByText(/saving the stats|refused/i)).toBeInTheDocument();

    failOn = null;
    await user.click(screen.getByRole('button', { name: /Create NPC|Retry/ }));
    await waitFor(() =>
      expect(writes().filter((w) => w.url.endsWith('/dispatch/'))).toHaveLength(1)
    );
    await waitFor(() =>
      expect(writes().filter((w) => w.url.endsWith('/staff-stats/'))).toHaveLength(2)
    );
  });

  it('does not grant magic twice when a retry finds the gift already held', async () => {
    const user = userEvent.setup();
    hasGift = true;
    renderForm();
    await fillPowers(user);
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    await waitFor(() => expect(writes().some((w) => w.url.endsWith('/staff-skills/'))).toBe(true));
    expect(writes().some((w) => w.url.endsWith('/staff-magic/'))).toBe(false);
  });
});
