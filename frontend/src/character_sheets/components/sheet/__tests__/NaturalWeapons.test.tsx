/** The natural weapons block on Physical (#4898): what a clawed character reads on their sheet. */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { CharacterSheetNaturalWeapon } from '@/character_sheets/api';
import { NaturalWeapons } from '../NaturalWeapons';

function talons(overrides: Partial<CharacterSheetNaturalWeapon> = {}): CharacterSheetNaturalWeapon {
  return {
    id: 7,
    name: 'Talons',
    gift_name: 'Blood of the Hunt',
    from_species: true,
    damage: 6,
    damage_type: 'Slashing',
    facets: ['Keenness', 'Wolf'],
    facets_used: 2,
    facet_capacity: 3,
    ...overrides,
  };
}

describe('NaturalWeapons', () => {
  it('names a species gift and states damage, facets and that they stay', () => {
    render(<NaturalWeapons weapons={[talons()]} />);

    expect(screen.getByRole('heading', { name: 'Natural weapons' })).toBeInTheDocument();
    expect(screen.getByText('Talons')).toBeInTheDocument();
    expect(screen.getByText('Unarmed')).toBeInTheDocument();
    expect(screen.getByText('From the species gift Blood of the Hunt.')).toBeInTheDocument();
    expect(
      screen.getByText('6 slashing damage · Keenness, Wolf, 2 of 3 · cannot be taken from you')
    ).toBeInTheDocument();
  });

  it('names a gift that came another way, and leaves out facets it has none of', () => {
    render(
      <NaturalWeapons
        weapons={[talons({ from_species: false, damage_type: '', facets: [], facets_used: 0 })]}
      />
    );

    expect(screen.getByText('From the gift Blood of the Hunt.')).toBeInTheDocument();
    expect(screen.getByText('6 damage · cannot be taken from you')).toBeInTheDocument();
  });

  it('renders nothing for a character with no natural weapons', () => {
    const { container } = render(<NaturalWeapons weapons={[]} />);

    expect(container).toBeEmptyDOMElement();
  });
});
