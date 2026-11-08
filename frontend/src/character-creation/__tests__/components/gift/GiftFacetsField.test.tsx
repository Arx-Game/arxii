/**
 * GiftFacetsField (#5021): the optional facet pick for the gift resonance in creation.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GiftFacetsField } from '../../../components/gift/GiftFacetsField';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';

const mutate = vi.fn();
const FACETS = [
  { id: 1, name: 'Wolf', description: '' },
  { id: 2, name: 'Silk', description: '' },
  { id: 3, name: 'Red', description: '' },
  { id: 4, name: 'Moon', description: '' },
  { id: 5, name: 'Ash', description: '' },
];

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useFacets: () => ({ data: FACETS }),
  useNearFacets: () => ({ data: [], isPending: false }),
  useUpdateDraft: () => ({ mutate, isPending: false }),
}));

function renderField(picked: number[]) {
  const draft = createMockDraft();
  draft.draft_data = { ...draft.draft_data, selected_gift_facet_ids: picked };
  renderWithCharacterCreationProviders(<GiftFacetsField draft={draft} resonanceName="Frost" />);
  return draft;
}

describe('GiftFacetsField', () => {
  beforeEach(() => mutate.mockReset());

  it('names the resonance and shows the picked facets', () => {
    renderField([1]);
    expect(screen.getByText('Facets of Frost')).toBeInTheDocument();
    expect(screen.getByText('Wolf')).toBeInTheDocument();
    expect(screen.getByText('1 of 5')).toBeInTheDocument();
  });

  it('adds a picked facet to the draft', async () => {
    const draft = renderField([1]);
    await userEvent.click(screen.getByRole('button', { name: '+ Add facet' }));
    await userEvent.click(await screen.findByText('Silk'));
    expect(mutate).toHaveBeenCalledWith({
      draftId: draft.id,
      data: { draft_data: { selected_gift_facet_ids: [1, 2] } },
    });
  });

  it('removes a facet from the draft', async () => {
    const draft = renderField([1, 2]);
    await userEvent.click(screen.getByRole('button', { name: 'Remove Wolf' }));
    expect(mutate).toHaveBeenCalledWith({
      draftId: draft.id,
      data: { draft_data: { selected_gift_facet_ids: [2] } },
    });
  });

  it('offers no picker once five are picked', () => {
    renderField([1, 2, 3, 4, 5]);
    expect(screen.queryByRole('button', { name: '+ Add facet' })).not.toBeInTheDocument();
  });
});
