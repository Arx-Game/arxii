import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/roster/useBrowsingIdentity', () => ({
  useBrowsingIdentity: () => ({ entryId: 1, name: 'Warden Osk', entry: { character_id: 7 } }),
}));
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({
    data: [{ id: 31, name: 'Sergeant Rook', roster_type: 'NPC' }],
  }),
}));
const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (url: string, init?: RequestInit) => apiFetch(url, init),
}));

import { NpcForm } from '../NpcForm';

const NEW_ENTRY = 55;

function ok(body: unknown) {
  return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
}

function route(url: string, init?: RequestInit) {
  if (url === '/api/roster/npcs/templates/') {
    return ok({ count: 1, results: [{ id: 12, name: 'Veteran gate officer' }] });
  }
  if (url === '/api/roster/npc-presets/') {
    return ok({ count: 1, results: [{ id: 3, name: 'Guardsman', description: '' }] });
  }
  if (url.endsWith('/dispatch/')) {
    return ok({ success: true, message: 'Vael minted.', data: { roster_entry_id: NEW_ENTRY } });
  }
  if (url === `/api/roster/entries/${NEW_ENTRY}/`) {
    return ok({ id: NEW_ENTRY, character: { id: 90, name: 'Vael' } });
  }
  if (init?.method) return ok({});
  return ok({ count: 0, results: [] });
}

/** Every call that writes: method, url and parsed body. */
function writes() {
  return apiFetch.mock.calls
    .filter(([, init]) => init?.method && init.method !== 'GET')
    .map(([url, init]) => ({
      method: init.method as string,
      url: url as string,
      body: init.body ? JSON.parse(init.body as string) : undefined,
    }));
}

function renderForm(mode: 'quick' | 'detailed') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NpcForm mode={mode} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(route);
});

describe('NpcForm', () => {
  it('quick mode asks only for a name, a Copy from and a description', async () => {
    renderForm('quick');
    const textboxes = screen.getAllByRole('textbox');
    expect(textboxes.map((box) => box.getAttribute('id'))).toEqual(['npc-name', 'npc-description']);
    expect(screen.getByLabelText('Name')).toBe(textboxes[0]);
    expect(screen.getByLabelText('Description')).toBe(textboxes[1]);
    const pickers = screen.getAllByRole('combobox');
    expect(pickers).toHaveLength(1);
    expect(screen.getByLabelText('Copy from')).toBe(pickers[0]);
    expect(screen.getByRole('button', { name: 'Create and add to scene' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Create NPC' })).not.toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole('option', { name: 'Veteran gate officer (template)' })).toBeTruthy()
    );
  });

  it('a detailed NPC with only a name is minted and nothing else is written', async () => {
    const user = userEvent.setup();
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    await waitFor(() => expect(screen.getByRole('region', { name: 'Vael' })).toBeInTheDocument());
    expect(writes()).toEqual([
      {
        method: 'POST',
        url: '/api/actions/characters/7/dispatch/',
        body: {
          ref: { backend: 'registry', registry_key: 'mint_story_npc' },
          kwargs: { name: 'Vael' },
        },
      },
    ]);
  });

  it("Description's Copy from copies that section onto the new NPC", async () => {
    const user = userEvent.setup();
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    const copy = screen.getByLabelText('Copy Description from');
    await waitFor(() =>
      expect(
        screen.getAllByRole('option', { name: 'Veteran gate officer (template)' }).length
      ).toBeGreaterThan(0)
    );
    await user.selectOptions(copy, '12');
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[1]).toEqual({
      method: 'POST',
      url: `/api/roster/npcs/${NEW_ENTRY}/copy-section/`,
      body: { source_entry: 12, section: 'description' },
    });
  });

  it('sends the chosen stat block as the mint preset', async () => {
    const user = userEvent.setup();
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await waitFor(() => expect(screen.getByRole('option', { name: 'Guardsman' })).toBeTruthy());
    await user.selectOptions(screen.getByLabelText('Stat block'), 'Guardsman');
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0].body.kwargs).toEqual({ name: 'Vael', preset: 'Guardsman' });
  });

  it('writes only the identity and lending fields the GM filled in', async () => {
    const user = userEvent.setup();
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.type(screen.getByLabelText('Vocation'), 'Soldier');
    await user.click(screen.getByLabelText('List on the NPC roster'));
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    await waitFor(() => expect(writes()).toHaveLength(3));
    expect(writes().slice(1)).toEqual([
      {
        method: 'PATCH',
        url: '/api/character-sheets/90/staff-edit/',
        body: { vocation: 'Soldier' },
      },
      {
        method: 'PATCH',
        url: `/api/roster/npcs/${NEW_ENTRY}/`,
        body: { listed_on_npc_roster: true },
      },
    ]);
  });

  it('Save as template creates the NPC, then copies it as a template', async () => {
    const user = userEvent.setup();
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.click(screen.getByRole('button', { name: 'Save as template' }));
    const templateName = screen.getByLabelText('Template name');
    await user.clear(templateName);
    await user.type(templateName, 'Gate captain');
    await user.click(screen.getByRole('button', { name: 'Save template' }));

    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[1]).toEqual({
      method: 'POST',
      url: `/api/roster/npcs/${NEW_ENTRY}/copy-as-new/`,
      body: { name: 'Gate captain', as_template: true },
    });
  });

  it('names each identity picker by its label', () => {
    renderForm('detailed');
    for (const label of ['Gender', 'Pronouns', 'Species', 'Build', 'Family']) {
      expect(screen.getByRole('combobox', { name: label })).toBeInTheDocument();
    }
  });

  it('shows the acting GM character as the owner', () => {
    renderForm('detailed');
    expect(screen.getByText('Warden Osk (you, the creator)')).toBeInTheDocument();
  });

  it('carries the name and description from Quick into Detailed', async () => {
    const user = userEvent.setup();
    renderForm('quick');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.type(screen.getByRole('textbox', { name: 'Description' }), 'Tall and spare.');
    await user.click(screen.getByRole('button', { name: 'Detailed' }));
    expect(screen.getByLabelText('Name')).toHaveValue('Vael');
    expect(screen.getByRole('textbox', { name: 'Description' })).toHaveValue('Tall and spare.');
  });

  it('Quick sends only what Quick shows, even after filling Detailed', async () => {
    const user = userEvent.setup();
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.type(screen.getByLabelText('Vocation'), 'Soldier');
    await user.click(screen.getByLabelText('List on the NPC roster'));
    await user.click(screen.getByRole('button', { name: 'Quick' }));
    await user.click(screen.getByRole('button', { name: 'Create and add to scene' }));

    await waitFor(() => expect(screen.getByRole('region', { name: 'Vael' })).toBeInTheDocument());
    expect(writes()).toHaveLength(1);
    expect(writes()[0].body.kwargs).toEqual({ name: 'Vael' });
  });

  it('a Quick chip opens its section inline, and Quick then sends it', async () => {
    const user = userEvent.setup();
    renderForm('quick');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.click(screen.getByRole('button', { name: '+ Who they are' }));
    expect(screen.getByRole('button', { name: 'Create and add to scene' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '+ Who they are' })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText('Vocation'), 'Soldier');
    await user.click(screen.getByRole('button', { name: 'Create and add to scene' }));

    await waitFor(() => expect(writes()).toHaveLength(2));
    expect(writes()[1]).toEqual({
      method: 'PATCH',
      url: '/api/character-sheets/90/staff-edit/',
      body: { vocation: 'Soldier' },
    });
  });

  it('writes a typed description on top of a copied one', async () => {
    const user = userEvent.setup();
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.type(screen.getByRole('textbox', { name: 'Description' }), 'Tall and spare.');
    await waitFor(() =>
      expect(
        screen.getAllByRole('option', { name: 'Veteran gate officer (template)' }).length
      ).toBeGreaterThan(0)
    );
    await user.selectOptions(screen.getByLabelText('Copy Description from'), '12');
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    await waitFor(() => expect(writes()).toHaveLength(3));
    expect(writes()[0].body.kwargs).toEqual({ name: 'Vael' });
    expect(writes().slice(1)).toEqual([
      {
        method: 'POST',
        url: `/api/roster/npcs/${NEW_ENTRY}/copy-section/`,
        body: { source_entry: 12, section: 'description' },
      },
      {
        method: 'PATCH',
        url: '/api/character-sheets/90/staff-edit/',
        body: { description: 'Tall and spare.' },
      },
    ]);
  });

  it('after a failed step, says the NPC exists and retries without minting again', async () => {
    const user = userEvent.setup();
    let copyFails = true;
    apiFetch.mockImplementation((url: string, init?: RequestInit) => {
      if (url.endsWith('/copy-section/') && copyFails) {
        copyFails = false;
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ detail: 'Server error.' }),
        });
      }
      return route(url, init);
    });
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await waitFor(() =>
      expect(
        screen.getAllByRole('option', { name: 'Veteran gate officer (template)' }).length
      ).toBeGreaterThan(0)
    );
    await user.selectOptions(screen.getByLabelText('Copy Description from'), '12');
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Vael was created; copying Description failed. Try again.'
    );
    await user.click(screen.getByRole('button', { name: 'Create NPC' }));

    await waitFor(() => expect(screen.getByRole('region', { name: 'Vael' })).toBeInTheDocument());
    const dispatches = writes().filter((call) => call.url.endsWith('/dispatch/'));
    const copies = writes().filter((call) => call.url.endsWith('/copy-section/'));
    expect(dispatches).toHaveLength(1);
    expect(copies).toHaveLength(2);
  });

  it('Enter in a sub-editor or a number box never submits the form', async () => {
    const user = userEvent.setup();
    renderForm('detailed');
    await user.type(screen.getByLabelText('Name'), 'Vael');
    await user.type(screen.getByLabelText('Born (IC year)'), '980{Enter}');
    await user.type(screen.getByLabelText('Reason'), 'Sold the grain{Enter}');
    await user.type(screen.getByLabelText('Name'), '{Enter}');
    expect(writes()).toEqual([]);
    expect(screen.getByRole('form', { name: 'New NPC' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save as template' }));
    await user.type(screen.getByLabelText('Template name'), '{Enter}');

    await waitFor(() => expect(writes().length).toBeGreaterThan(0));
    // The only write is the one the template name's Enter asked for: its mint.
    expect(writes().filter((call) => call.url.endsWith('/dispatch/'))).toHaveLength(1);
  });
});
