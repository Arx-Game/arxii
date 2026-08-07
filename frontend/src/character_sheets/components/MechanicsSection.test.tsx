/**
 * MechanicsSection tests (#3042).
 *
 * Covers: attribute grid rendering + display capitalization, empty-state lines for both
 * stats and skills, skill rows with value/specializations/at_boundary badge.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MechanicsSection } from './MechanicsSection';
import type { CharacterSheetSkill } from '@/character_sheets/api';

function makeSkill(overrides: Partial<CharacterSheetSkill> = {}): CharacterSheetSkill {
  return {
    skill: { id: 1, name: 'melee', category: 'combat' },
    value: 25,
    at_boundary: false,
    specializations: [],
    ...overrides,
  };
}

describe('MechanicsSection', () => {
  it('renders stat entries with capitalized names and display values', () => {
    render(<MechanicsSection stats={{ strength: 3, agility: 4 }} skills={[]} />);
    expect(screen.getByText('Strength')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Agility')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
  });

  it('shows the empty state when there are no stats', () => {
    render(<MechanicsSection stats={{}} skills={[]} />);
    expect(screen.getByTestId('stats-empty-state')).toBeInTheDocument();
  });

  it('renders a skill row with its value and specializations', () => {
    render(
      <MechanicsSection
        stats={{}}
        skills={[
          makeSkill({
            skill: { id: 2, name: 'sewing', category: 'crafting' },
            value: 40,
            specializations: [{ id: 9, name: 'Embroidery', value: 5 }],
          }),
        ]}
      />
    );
    expect(screen.getByText('Sewing')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('Embroidery (5)')).toBeInTheDocument();
  });

  it('shows the at-boundary badge when a skill is parked at an XP boundary', () => {
    render(<MechanicsSection stats={{}} skills={[makeSkill({ at_boundary: true })]} />);
    expect(screen.getByTestId('skill-at-boundary')).toBeInTheDocument();
  });

  it('shows the empty state when there are no skills', () => {
    render(<MechanicsSection stats={{}} skills={[]} />);
    expect(screen.getByTestId('skills-empty-state')).toBeInTheDocument();
  });
});
