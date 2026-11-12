import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { MissiveComposeDialog } from '../MissiveComposeDialog';
import type { Missive } from '../../types';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));
vi.mock('@/missives/api', () => ({
  dispatchMissiveAction: vi.fn(),
  fetchMissives: vi.fn(),
  fetchMissiveUnreadCount: vi.fn(),
}));
vi.mock('@/game/personaQueries', () => ({
  useCharacterPersonasQuery: vi.fn(),
}));
vi.mock('@/inventory/api', () => ({
  listInventory: vi.fn(),
}));
vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: vi.fn(() => ({ results: [], isFetching: false })),
}));

import { dispatchMissiveAction } from '@/missives/api';
import { useCharacterPersonasQuery } from '@/game/personaQueries';
import { listInventory } from '@/inventory/api';

const mockDispatch = vi.mocked(dispatchMissiveAction);

const PERSONAS = [
  { id: 1, name: 'Hobb', persona_type: 'primary' },
  { id: 2, name: 'the Gray Fox', persona_type: 'established' },
];

const LETTER: Missive = {
  id: 30,
  direction: 'received',
  counterpart_name: 'Ysmay',
  own_persona_id: 2,
  own_persona_name: 'the Gray Fox',
  method_name: 'Messenger',
  body: 'Meet me at the docks.',
  ic_date: '',
  sent_at: '2026-11-01T00:00:00Z',
  is_read: true,
  in_reply_to: null,
  attachments: [],
};

describe('MissiveComposeDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDispatch.mockResolvedValue({ message: 'Your missive is on its way.', data: undefined });
    vi.mocked(useCharacterPersonasQuery).mockReturnValue({
      data: PERSONAS,
    } as unknown as ReturnType<typeof useCharacterPersonasQuery>);
    vi.mocked(listInventory).mockResolvedValue([
      { id: 5, display_name: 'Moth Brooch' },
    ] as unknown as Awaited<ReturnType<typeof listInventory>>);
  });

  it('sends to the card persona from the worn face, with coin and an item', async () => {
    const onClose = vi.fn();
    renderWithProviders(
      <MissiveComposeDialog
        open
        onClose={onClose}
        characterId={12}
        activePersonaId={1}
        recipient={{ id: 9, name: 'Alice' }}
      />
    );
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'Hello there.' } });
    fireEvent.change(screen.getByLabelText('Coin'), { target: { value: '5s' } });
    fireEvent.click(await screen.findByLabelText('Moth Brooch'));
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mockDispatch).toHaveBeenCalledWith(12, 'send_missive', {
      body: 'Hello there.',
      sender_persona_id: 1,
      coin_amount: 50,
      item_ids: [5],
      recipient_persona_id: 9,
    });
  });

  it('replies from the face the letter was addressed to', async () => {
    const onClose = vi.fn();
    renderWithProviders(
      <MissiveComposeDialog
        open
        onClose={onClose}
        characterId={12}
        activePersonaId={1}
        replyTo={LETTER}
      />
    );
    expect(screen.getByLabelText('From')).toHaveValue('2');
    expect(screen.queryByLabelText('To')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Message'), { target: { value: 'At dusk.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(mockDispatch).toHaveBeenCalledWith(12, 'reply_missive', {
      body: 'At dusk.',
      sender_persona_id: 2,
      missive_id: 30,
    });
  });
});
