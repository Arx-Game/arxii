import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

vi.mock('@/gm-adjudication/useActiveCharacterId', () => ({ useActiveCharacterId: () => 7 }));
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
];

function respond(url: string) {
  const results = url.includes('cast-list') ? cast : [{ account_id: 21, display_name: 'Ilsa' }];
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ results }) });
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return render(<CastListPanel sceneId={3} />, { wrapper: Wrapper });
}

describe('CastListPanel', () => {
  beforeEach(() => {
    dispatch.mockReset().mockResolvedValue({ message: 'Done.', success: true });
    apiFetch.mockReset().mockImplementation(respond);
  });

  it('shows who plays each row', async () => {
    renderPanel();
    expect(await screen.findByText('Captain Vael · Ilsa (Guide)')).toBeInTheDocument();
    expect(screen.getByText('Besieger skirmishers · swarm · 30 bodies')).toBeInTheDocument();
  });

  it('takes back a lent NPC by loan id', async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: 'Take back' }));
    await waitFor(() => expect(dispatch).toHaveBeenCalledWith(7, 'take_back_npc', { loan_id: 33 }));
  });

  it('offers an NPC to a Guide', async () => {
    renderPanel();
    await screen.findByText('Magistrate Orr · Tehom');
    await screen.findByRole('option', { name: 'Offer to Ilsa' });
    await userEvent.selectOptions(screen.getByLabelText('Play Magistrate Orr'), '21');
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith(7, 'offer_npc', {
        roster_entry_id: 6,
        guide_account_id: 21,
      })
    );
  });

  it('gives an unvoiced crowd a voice', async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: 'Add crowd voice' }));
    await userEvent.type(screen.getByLabelText('Crowd voice name'), 'The Besiegers');
    await userEvent.click(screen.getByRole('button', { name: 'Give voice' }));
    await waitFor(() =>
      expect(dispatch).toHaveBeenCalledWith(7, 'voice_crowd', {
        opponent_ids: [4, 5],
        name: 'The Besiegers',
      })
    );
  });
});
