/**
 * The journal composer's "Reflecting on" row (#5124): a private or public entry posts the
 * picked deed or resonance and Embrace or Disown with the entry, and posts none when nothing
 * is picked.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

vi.mock('../queries', () => ({ useCreateJournalEntry: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: () => ({ results: [], isFetching: false }),
}));
vi.mock('@/gm-adjudication/useActiveCharacterId', () => ({ useActiveCharacterId: () => 7 }));
vi.mock('@/magic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/magic/api')>()),
  getReflectionOptions: vi.fn(),
}));

import * as magicApi from '@/magic/api';
import { JournalComposerDialog } from '../components/JournalComposerDialog';
import * as queries from '../queries';

const mutate = vi.fn();

describe('JournalComposerDialog reflection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(queries.useCreateJournalEntry).mockReturnValue({
      mutate,
      isPending: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof queries.useCreateJournalEntry>);
    vi.mocked(magicApi.getReflectionOptions).mockResolvedValue([
      {
        kind: 'resonance',
        id: 21,
        label: 'Your Domination · unsettling you',
        replaces_waiting: false,
      },
    ]);
  });

  it('posts the resonance the writer disowns with the black journal entry', async () => {
    const user = userEvent.setup();
    renderWithProviders(<JournalComposerDialog open onClose={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Black journal · Private' }));
    await user.type(screen.getByLabelText('Title'), 'The collar');
    await user.type(screen.getByLabelText('Entry'), 'I am putting it down.');
    await user.click(await screen.findByTestId('reflect-option-resonance-21'));
    await user.click(screen.getByTestId('reflect-choice-DISOWN'));
    await user.click(screen.getByRole('button', { name: /post entry/i }));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'The collar',
        is_public: false,
        reflect_choice: 'DISOWN',
        reflect_resonance_id: 21,
      }),
      expect.anything()
    );
  });

  it('posts no reflection fields when nothing is picked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<JournalComposerDialog open onClose={vi.fn()} />);

    await user.type(screen.getByLabelText('Title'), 'A quiet evening');
    await user.type(screen.getByLabelText('Entry'), 'Rain.');
    await screen.findByTestId('reflecting-on-row');
    await user.click(screen.getByRole('button', { name: /post entry/i }));

    const payload = mutate.mock.calls[0][0] as Record<string, unknown>;
    expect(payload).not.toHaveProperty('reflect_choice');
    expect(payload).not.toHaveProperty('reflect_resonance_id');
    expect(payload).not.toHaveProperty('reflect_grant_id');
  });
});
