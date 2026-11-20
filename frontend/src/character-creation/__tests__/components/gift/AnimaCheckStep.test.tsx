/**
 * AnimaCheckStep tests (#4450).
 *
 * Magical rolls add magic-category skills as terms, so the Anima Check skill
 * row never offers one: picking it would count the skill twice.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
let stats: {
  id: number;
  name: string;
  trait_type: string;
  category: string;
  description: string;
}[] = [];
let suggestions: { skill_id: number; suggested_value: number }[] = [];
const mutate = vi.fn();

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate, mutateAsync: vi.fn() }),
  useSkills: () => ({ data: skills }),
  useStatDefinitions: () => ({ data: stats }),
  usePathSkillSuggestions: () => ({ data: suggestions }),
}));

function stat(id: number, name: string, category: string) {
  return { id, name, trait_type: 'stat', category, description: '' };
}

function Harness({ data = {} }: { data?: Record<string, unknown> }) {
  const { register } = useForm<GiftFormValues>();
  return (
    <AnimaCheckStep
      draft={createMockDraft({ selected_path: mockPath, draft_data: data })}
      register={register}
    />
  );
}

function optionNames(select: HTMLElement): string[] {
  return within(select)
    .getAllByRole('option')
    .map((option) => option.textContent ?? '');
}

describe('AnimaCheckStep', () => {
  beforeEach(() => {
    skills = [];
    stats = [];
    suggestions = [];
    mutate.mockReset();
  });

  it('lists non-magic skills as options', () => {
    skills = [skill(1, 'Melee', 'combat'), skill(2, 'Persuasion', 'social')];
    renderWithCharacterCreationProviders(<Harness />);

    expect(optionNames(screen.getByRole('combobox', { name: 'Skill' }))).toEqual([
      'Select',
      'Melee',
      'Persuasion',
    ]);
  });

  it('does not offer a magic-category skill', () => {
    skills = [skill(1, 'Melee', 'combat'), skill(3, 'Occult Lore', 'magic')];
    renderWithCharacterCreationProviders(<Harness />);

    expect(optionNames(screen.getByRole('combobox', { name: 'Skill' }))).toEqual([
      'Select',
      'Melee',
    ]);
    expect(screen.queryByText('Occult Lore')).not.toBeInTheDocument();
  });

  // #5220, owner ruling 2026-11-20: the picks were a button per statistic and per skill,
  // 28 boxes of uneven width. Each is now one dropdown.
  it('draws each pick as one dropdown and no button per option', () => {
    stats = [stat(1, 'strength', 'physical'), stat(2, 'willpower', 'meta')];
    skills = [skill(1, 'Melee', 'combat')];
    renderWithCharacterCreationProviders(<Harness />);

    expect(screen.getByRole('combobox', { name: 'Statistic' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Skill' })).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('puts the suggested statistic and skill first and the rest under their categories', () => {
    stats = [
      stat(1, 'strength', 'physical'),
      stat(2, 'agility', 'physical'),
      stat(3, 'charm', 'social'),
      stat(4, 'willpower', 'meta'),
    ];
    skills = [
      skill(1, 'Melee', 'Combat'),
      skill(2, 'Persuasion', 'Social'),
      skill(3, 'Rites', 'Social'),
    ];
    suggestions = [
      { skill_id: 1, suggested_value: 10 },
      { skill_id: 3, suggested_value: 30 },
    ];
    renderWithCharacterCreationProviders(<Harness />);

    const statSelect = screen.getByRole('combobox', { name: 'Statistic' });
    expect(optionNames(statSelect)).toEqual([
      'Select',
      'Willpower (suggested)',
      'Strength',
      'Agility',
      'Charm',
    ]);
    // Willpower was the only Meta statistic, so its category has nothing left to list.
    expect(
      within(statSelect)
        .getAllByRole('group')
        .map((group) => group.getAttribute('label'))
    ).toEqual(['Physical', 'Social']);

    const skillSelect = screen.getByRole('combobox', { name: 'Skill' });
    expect(optionNames(skillSelect)).toEqual([
      'Select',
      'Rites (suggested)',
      'Melee',
      'Persuasion',
    ]);
    expect(
      within(skillSelect)
        .getAllByRole('group')
        .map((group) => group.getAttribute('label'))
    ).toEqual(['Combat', 'Social']);
  });

  it('saves the statistic and the skill chosen, each to its own draft field', async () => {
    const user = userEvent.setup();
    stats = [stat(1, 'strength', 'physical'), stat(4, 'willpower', 'meta')];
    skills = [skill(1, 'Melee', 'Combat'), skill(2, 'Persuasion', 'Social')];
    renderWithCharacterCreationProviders(<Harness />);

    await user.selectOptions(screen.getByRole('combobox', { name: 'Statistic' }), 'Strength');
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ data: { draft_data: { anima_check_stat_id: 1 } } })
    );

    await user.selectOptions(screen.getByRole('combobox', { name: 'Skill' }), 'Persuasion');
    expect(mutate).toHaveBeenLastCalledWith(
      expect.objectContaining({ data: { draft_data: { anima_check_skill_id: 2 } } })
    );
  });

  it('shows the saved pick and drops the empty first option once something is chosen', () => {
    stats = [stat(1, 'strength', 'physical'), stat(4, 'willpower', 'meta')];
    skills = [skill(1, 'Melee', 'Combat'), skill(2, 'Persuasion', 'Social')];
    renderWithCharacterCreationProviders(
      <Harness data={{ anima_check_stat_id: 1, anima_check_skill_id: 2 }} />
    );

    const statSelect = screen.getByRole('combobox', { name: 'Statistic' });
    expect(statSelect).toHaveValue('1');
    expect(optionNames(statSelect)).toEqual(['Willpower (suggested)', 'Strength']);
    expect(screen.getByRole('combobox', { name: 'Skill' })).toHaveValue('2');
  });
});
