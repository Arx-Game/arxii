import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

const actor = vi.fn((): number | null => 7);
vi.mock('@/gm-adjudication/useActiveCharacterId', () => ({ useActiveCharacterId: () => actor() }));
import { toast } from 'sonner';
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const dispatch = vi.fn();
vi.mock('@/map-canvas/dispatch', () => ({
  dispatchCanvasAction: (...args: unknown[]) => dispatch(...args),
}));
const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({ apiFetch: (u: string) => apiFetch(u) }));

import { CastListPanel } from '../CastListPanel';

const base = {
  roster_entry_id: null,
  persona_id: null,
  thumbnail_url: '',
  played_by: '',
  loan_id: null,
  loan_status: null,
  tier: null,
  count: null,
  description: '',
  opponent_ids: [] as number[],
};
const cast = [
  {
    ...base,
    kind: 'npc',
    name: 'Captain Vael',
    roster_entry_id: 5,
    persona_id: 9,
    played_by: 'Ilsa',
    loan_id: 33,
    loan_status: 'active',
  },
  {
    ...base,
    kind: 'npc',
    name: 'Magistrate Orr',
    roster_entry_id: 6,
    persona_id: 10,
    played_by: 'Tehom',
  },
  {
    ...base,
    kind: 'crowd',
    name: 'Besieger skirmishers',
    tier: 'swarm',
    count: 30,
    description: 'First paragraph.\n\nSecond paragraph.',
    opponent_ids: [4, 5],
  },
  {
    ...base,
    kind: 'crowd',
    name: 'Gate guard',
    tier: 'mook',
    count: 8,
    opponent_ids: [8],
    roster_entry_id: 12,
    persona_id: 40,
    played_by: 'Ilsa',
    loan_id: 50,
    loan_status: 'active',
  },
  {
    ...base,
    kind: 'npc',
    name: 'Envoy Pell',
    roster_entry_id: 13,
    persona_id: 41,
    played_by: 'Ilsa',
    loan_id: 51,
    loan_status: 'offered',
  },
];

function respond(url: string) {
  const results = url.includes('cast-list') ? cast : [{ account_id: 21, display_name: 'Ilsa' }];
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ results }) });
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
  return render(<CastListPanel sceneId={3} sceneName="The Siege" />, { wrapper: Wrapper });
}

describe('CastListPanel', () => {
  beforeEach(() => {
    actor.mockReturnValue(7);
    dispatch.mockReset().mockResolvedValue({ message: 'Done.', success: true });
    apiFetch.mockReset().mockImplementation(respond);
  });

  it('shows who plays each row', async () => {
    renderPanel();
    expect(await screen.findByText('Captain Vael · Ilsa (Guide)')).toBeInTheDocument();
    expect(screen.getByText('Besieger skirmishers')).toBeInTheDocument();
    expect(screen.getByText('swarm · 30 bodies')).toBeInTheDocument();
    expect(screen.getByText('8 · mooks')).toBeInTheDocument();
    expect(screen.getByText('Cast · The Siege')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '+ Add NPC' })).toHaveAttribute(
      'href',
      '/gm/dashboard?scene=3'
    );
  });

  it('takes back a lent NPC by loan id', async () => {
    renderPanel();
    const [first] = await screen.findAllByRole('button', { name: 'Take back' });
    await userEvent.click(first);
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith(7, 'take_back_npc', { loan_id: 33, scene_id: 3 })
    );
  });

  it('offers an NPC to a Guide', async () => {
    renderPanel();
    await screen.findByText('Magistrate Orr · Tehom');
    await screen.findAllByRole('option', { name: 'Offer to Ilsa' });
    await userEvent.selectOptions(screen.getByLabelText('Play Magistrate Orr'), '21');
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith(7, 'offer_npc', {
        roster_entry_id: 6,
        guide_account_id: 21,
        scene_id: 3,
      })
    );
  });

  it('gives an unvoiced crowd a voice', async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: 'Add crowd voice' }));
    const input = screen.getByLabelText('Crowd voice name');
    await userEvent.clear(input);
    await userEvent.type(input, 'The Besiegers');
    await userEvent.click(screen.getByRole('button', { name: 'Give voice' }));
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith(7, 'voice_crowd', {
        opponent_ids: [4, 5],
        name: 'The Besiegers',
        scene_id: 3,
      })
    );
  });

  it('lets a voiced lent crowd be taken back like an NPC', async () => {
    renderPanel();
    await screen.findByText('Gate guard');
    expect(screen.queryByRole('button', { name: 'Add crowd voice' })).toBeInTheDocument();
    const buttons = await screen.findAllByRole('button', { name: 'Take back' });
    await userEvent.click(buttons[1]);
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith(7, 'take_back_npc', { loan_id: 50, scene_id: 3 })
    );
  });

  it('offered row has no Take back and Me withdraws the offer', async () => {
    renderPanel();
    expect(await screen.findByText('Envoy Pell \u00b7 Offered to Ilsa')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Take back' })).toHaveLength(2);
    await userEvent.selectOptions(screen.getByLabelText('Play Envoy Pell'), 'me');
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith(7, 'take_back_npc', { loan_id: 51, scene_id: 3 })
    );
  });

  it('renames and describes a crowd', async () => {
    renderPanel();
    const [btn] = await screen.findAllByRole('button', { name: 'Rename or describe' });
    await userEvent.click(btn);
    const area = screen.getByLabelText('Crowd description');
    await userEvent.clear(area);
    await userEvent.type(area, 'A new look');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith(7, 'describe_crowd', {
        opponent_ids: [4, 5],
        name: 'Besieger skirmishers',
        description: 'A new look',
        scene_id: 3,
      })
    );
  });

  it('opening a crowd form starts from the crowd as it is', async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: 'Add crowd voice' }));
    const voice = screen.getByLabelText('Crowd voice name');
    await userEvent.clear(voice);
    await userEvent.type(voice, 'Abandoned edit');
    const [btn] = screen.getAllByRole('button', { name: 'Rename or describe' });
    await userEvent.click(btn);
    expect(screen.getByLabelText('Crowd name')).toHaveValue('Besieger skirmishers');
  });

  it('toasts a refused action', async () => {
    dispatch.mockResolvedValue({ message: 'Not allowed.', success: false });
    renderPanel();
    const [btn] = await screen.findAllByRole('button', { name: 'Take back' });
    await userEvent.click(btn);
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Not allowed.'));
  });

  it('disables actions without an acting character', async () => {
    actor.mockReturnValue(null);
    renderPanel();
    const [btn] = await screen.findAllByRole('button', { name: 'Take back' });
    expect(btn).toBeDisabled();
  });

  it('shows an error when the cast fails to load', async () => {
    apiFetch.mockResolvedValue({ ok: false });
    renderPanel();
    expect(await screen.findAllByRole('alert')).not.toHaveLength(0);
  });
});
