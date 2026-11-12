import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { MissiveList } from '../MissiveList';
import type { Missive } from '../../types';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));
vi.mock('@/missives/api', () => ({
  dispatchMissiveAction: vi.fn(),
  fetchMissives: vi.fn(),
  fetchMissiveUnreadCount: vi.fn(),
}));

import { dispatchMissiveAction } from '@/missives/api';

function row(overrides: Partial<Missive>): Missive {
  return {
    id: 1,
    direction: 'received',
    counterpart_name: 'Ysmay',
    own_persona_id: 1,
    own_persona_name: 'Hobb',
    method_name: 'Messenger',
    body: 'A letter.',
    ic_date: '',
    sent_at: '2026-11-01T00:00:00Z',
    is_read: true,
    in_reply_to: null,
    attachments: [],
    ...overrides,
  };
}

describe('MissiveList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(dispatchMissiveAction).mockResolvedValue({ message: '', data: undefined });
  });

  it('groups by the face written to, puts sent letters last, and reads an unread one', async () => {
    renderWithProviders(
      <MissiveList
        characterId={12}
        onReply={vi.fn()}
        missives={[
          row({ id: 31, counterpart_name: 'Ysmay', is_read: false }),
          row({
            id: 32,
            counterpart_name: 'Orrin',
            own_persona_id: 2,
            own_persona_name: 'the Gray Fox',
          }),
          row({ id: 33, direction: 'sent', counterpart_name: 'Alice' }),
        ]}
      />
    );

    const headings = screen.getAllByRole('heading').map((h) => h.textContent);
    expect(headings).toEqual(['To Hobb', 'To the Gray Fox', 'Sent']);
    const sent = screen.getByRole('heading', { name: 'Sent' }).closest('section') as HTMLElement;
    expect(within(sent).getByText('Alice')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Ysmay' }));
    await waitFor(() =>
      expect(dispatchMissiveAction).toHaveBeenCalledWith(12, 'read_missive', { missive_id: 31 })
    );
  });
});
