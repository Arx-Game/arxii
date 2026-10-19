/**
 * AnimaCheckStep tests (#4450).
 *
 * Magical rolls add magic-category skills as terms, so the Anima Check skill
 * row never offers one: picking it would count the skill twice.
 */

import { screen } from '@testing-library/react';
import { useForm } from 'react-hook-form';
import { vi } from 'vitest';
import { AnimaCheckStep } from '../../../components/gift/AnimaCheckStep';
import type { GiftFormValues } from '../../../components/GiftStage';
import type { Skill } from '../../../types';
import { createMockDraft, mockCGExplanations, mockPath } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';

function skill(id: number, name: string, category: string): Skill {
  return {
    id,
    name,
    category,
    category_display: category,
    description: '',
    tooltip: '',
    display_order: id,
    is_active: true,
    specializations: [],
  };
}

let skills: Skill[] = [];

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
  useSkills: () => ({ data: skills }),
  useStatDefinitions: () => ({ data: [] }),
  usePathSkillSuggestions: () => ({ data: [] }),
}));

function Harness() {
  const { register } = useForm<GiftFormValues>();
  return (
    <AnimaCheckStep draft={createMockDraft({ selected_path: mockPath })} register={register} />
  );
}

describe('AnimaCheckStep', () => {
  it('lists non-magic skills as options', () => {
    skills = [skill(1, 'Melee', 'combat'), skill(2, 'Persuasion', 'social')];
    renderWithCharacterCreationProviders(<Harness />);
    const group = screen.getByRole('group', { name: 'Skill' });
    expect(group).toHaveTextContent('Melee');
    expect(group).toHaveTextContent('Persuasion');
  });

  it('does not offer a magic-category skill', () => {
    skills = [skill(1, 'Melee', 'combat'), skill(3, 'Occult Lore', 'magic')];
    renderWithCharacterCreationProviders(<Harness />);
    const group = screen.getByRole('group', { name: 'Skill' });
    expect(group).toHaveTextContent('Melee');
    expect(screen.queryByRole('button', { name: 'Occult Lore' })).not.toBeInTheDocument();
  });
});
