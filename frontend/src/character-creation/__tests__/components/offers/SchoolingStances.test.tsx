/**
 * SchoolingStances Component Tests (#3675).
 *
 * The standard schooling set under a `living_masters` tradition: three
 * stances at rank 0, 1 and 2, syncing a Tradition Training entry at the
 * picked rank (rank 0 clears the pick).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { SchoolingStances } from '../../../components/offers/SchoolingStances';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import type { SchoolingLineRow, Tradition } from '../../../types';
import { createMockDraft, mockTradition } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import { unreachableClasses } from './classGuard';

const mutate = vi.fn();
let draftDistinctions: DraftDistinctionEntry[];

vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate }),
}));

const newlyTakenIn: SchoolingLineRow = {
  schooling_line_id: 1,
  rank: 0,
  name: 'Newly taken in',
  player_line: 'Taken in after the Glimpse.',
  price: 0,
  techniques: 1,
  grants_distinction_id: null,
  offer_id: null,
};

const trainedForYears: SchoolingLineRow = {
  schooling_line_id: 2,
  rank: 1,
  name: 'Trained for years',
  player_line: 'Trained since youth.',
  price: 1,
  techniques: 2,
  grants_distinction_id: 77,
  offer_id: 201,
};

const raisedWithinIt: SchoolingLineRow = {
  schooling_line_id: 3,
  rank: 2,
  name: 'Raised within it',
  player_line: 'Born to it.',
  price: 2,
  techniques: 3,
  grants_distinction_id: 77,
  offer_id: 202,
};

const tradition: Tradition = {
  ...mockTradition,
  state: 'living_masters',
  schooling: [newlyTakenIn, trainedForYears, raisedWithinIt],
};

beforeEach(() => {
  mutate.mockClear();
  draftDistinctions = [];
});

describe('SchoolingStances', () => {
  it('renders three stances with their prices and technique counts', () => {
    renderWithCharacterCreationProviders(
      <SchoolingStances draft={createMockDraft()} tradition={tradition} />
    );
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByText('1 technique')).toBeInTheDocument();
    expect(screen.getByText('2 techniques')).toBeInTheDocument();
    expect(screen.getByText('3 techniques')).toBeInTheDocument();
  });

  it('picking rank 2 syncs Tradition Training at rank 2 with its offer id', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <SchoolingStances draft={createMockDraft()} tradition={tradition} />
    );
    await user.click(screen.getByRole('button', { name: /Raised within it/ }));
    expect(mutate).toHaveBeenCalledWith([{ id: 77, rank: 2, offer_id: 202 }]);
  });

  it('picking rank 0 removes the existing schooling pick', async () => {
    draftDistinctions = [
      {
        distinction_id: 77,
        distinction_name: 'Tradition Training',
        distinction_slug: 'tradition-training',
        category_slug: 'magic',
        rank: 1,
        cost: 1,
        notes: '',
        offer_ids: [201],
        sources: ['Trained for years'],
        arrivals: ['choice'],
      },
    ];
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <SchoolingStances draft={createMockDraft()} tradition={tradition} />
    );
    await user.click(screen.getByRole('button', { name: /Newly taken in/ }));
    expect(mutate).toHaveBeenCalledWith([]);
  });

  it('emits no class hook that cg.css has no rule reaching it (#3667 shape)', () => {
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <div className="field">
          <label>How you came to it</label>
          <SchoolingStances draft={createMockDraft()} tradition={tradition} />
        </div>
      </div>
    );
    expect(unreachableClasses(container)).toEqual([]);
  });
});
