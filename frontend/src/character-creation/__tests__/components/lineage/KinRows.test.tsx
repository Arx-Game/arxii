/**
 * The people seated beside the parents (#4395): a twin, a spouse, children, each row a
 * name, a gender and a fate, the whole list saved on every change.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { KinRows } from '../../../components/lineage/KinRows';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';

const mutate = vi.fn();

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useUpdateDraft: () => ({ mutate, mutateAsync: vi.fn() }),
  useGenders: () => ({
    data: [
      { id: 1, key: 'female', display_name: 'Female' },
      { id: 2, key: 'male', display_name: 'Male' },
    ],
  }),
}));

describe('KinRows', () => {
  beforeEach(() => mutate.mockClear());

  it('adds a spouse with a living fate and saves the whole list', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      draft_data: { kin_rows: [{ kind: 'twin', name: 'Wen', gender_id: 1, fate: '' }] },
    });
    renderWithCharacterCreationProviders(<KinRows draft={draft} copy={{}} />);
    // One twin at most: the twin door is gone once one is seated.
    const add = screen.getByRole('group', { name: 'Add' });
    expect(within(add).queryByRole('button', { name: 'A twin' })).toBeNull();
    await user.click(within(add).getByRole('button', { name: 'A spouse' }));
    expect(mutate).toHaveBeenCalledWith({
      draftId: draft.id,
      data: {
        draft_data: {
          kin_rows: [
            { kind: 'twin', name: 'Wen', gender_id: 1, fate: '' },
            { kind: 'spouse', name: '', gender_id: null, fate: 'alive' },
          ],
        },
      },
    });
  });

  it('a fate, a name and a gender each save their row; remove drops it', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      draft_data: {
        kin_rows: [
          { kind: 'spouse', name: 'Aldo', gender_id: null, fate: 'alive' },
          { kind: 'child', name: 'Pip', gender_id: null, fate: 'raised' },
        ],
      },
    });
    renderWithCharacterCreationProviders(<KinRows draft={draft} copy={{}} />);
    const spouse = screen.getByRole('listitem', { name: 'A spouse' });
    await user.click(within(spouse).getByRole('button', { name: 'Dead' }));
    expect(mutate).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: {
        draft_data: {
          kin_rows: [
            { kind: 'spouse', name: 'Aldo', gender_id: null, fate: 'dead' },
            { kind: 'child', name: 'Pip', gender_id: null, fate: 'raised' },
          ],
        },
      },
    });
    const child = screen.getByRole('listitem', { name: 'A child' });
    await user.click(within(child).getByRole('button', { name: 'Fostered away' }));
    expect(mutate.mock.lastCall?.[0].data.draft_data.kin_rows[1].fate).toBe('fostered_away');
    await user.click(within(child).getByRole('button', { name: 'Male' }));
    expect(mutate.mock.lastCall?.[0].data.draft_data.kin_rows[1].gender_id).toBe(2);
    await user.clear(within(child).getByLabelText('Name'));
    await user.type(within(child).getByLabelText('Name'), 'Tam');
    await user.tab();
    expect(mutate.mock.lastCall?.[0].data.draft_data.kin_rows[1].name).toBe('Tam');
    await user.click(within(spouse).getByRole('button', { name: 'Remove: A spouse' }));
    expect(mutate.mock.lastCall?.[0].data.draft_data.kin_rows).toEqual([
      { kind: 'child', name: 'Pip', gender_id: null, fate: 'raised' },
    ]);
  });
});
