import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/companions/queries', () => ({
  useMyCompanions: () => ({
    data: [
      { id: 1, name: 'Ash', archetype: { name: 'Direwolf' }, released_at: null, is_present: true },
      { id: 2, name: 'Ember', archetype: { name: 'Hawk' }, released_at: null, is_present: false },
      {
        id: 3,
        name: 'Gone',
        archetype: { name: 'Hawk' },
        released_at: '2026-01-01',
        is_present: false,
      },
    ],
  }),
}));
vi.mock('../RelationshipWriteupDialog', () => ({
  RelationshipWriteupDialog: () => <div data-testid="writeup-dialog" />,
}));

import { CompanionBondList } from '../CompanionBondList';

describe('CompanionBondList', () => {
  it('offers an impression for unbonded companions and develop for bonded ones, hiding released', () => {
    render(
      <CompanionBondList
        relationships={[{ id: 10, target: null, target_companion: 1, target_name: 'Ash' } as never]}
      />
    );
    expect(screen.getByTestId('companion-bond-1')).toHaveTextContent('Develop');
    expect(screen.getByTestId('companion-bond-2')).toHaveTextContent('Record an impression');
    expect(screen.queryByTestId('companion-bond-3')).not.toBeInTheDocument();
  });
});
