/**
 * AnimaRitualForm Component Tests
 *
 * Tests for the AnimaRitualForm component which uses Combobox dropdowns
 * with green intensity shading based on draft stat/skill/resonance investments.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { AnimaRitualForm } from '../../components/magic/AnimaRitualForm';
import { mockResonances } from '../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';
import type { ProjectedResonance, Skill, StatDefinition, Stats } from '../../types';

// Polyfill browser APIs for cmdk (used by Combobox)
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));
Element.prototype.scrollIntoView = vi.fn();

// Mock the API module
vi.mock('../../api', () => ({
  getStatDefinitions: vi.fn(),
  getSkillsWithSpecializations: vi.fn(),
  getResonances: vi.fn(),
  getDraftAnimaRitual: vi.fn(),
  createDraftAnimaRitual: vi.fn(),
  updateDraftAnimaRitual: vi.fn(),
}));

// Mock stat definitions
const mockStatDefinitions: StatDefinition[] = [
  { id: 1, name: 'Strength', trait_type: 'stat', category: 'physical', description: 'Raw power' },
  { id: 2, name: 'Agility', trait_type: 'stat', category: 'physical', description: 'Speed' },
  {
    id: 3,
    name: 'Intellect',
    trait_type: 'stat',
    category: 'mental',
    description: 'Mental acuity',
  },
];

// Mock skills
const mockSkills: Skill[] = [
  {
    id: 10,
    name: 'Athletics',
    category: 'physical',
    category_display: 'Physical',
    description: 'Physical feats',
    tooltip: '',
    display_order: 1,
    is_active: true,
    specializations: [
      {
        id: 100,
        name: 'Running',
        description: 'Fast movement',
        tooltip: '',
        display_order: 1,
        is_active: true,
        parent_skill_id: 10,
        parent_skill_name: 'Athletics',
      },
      {
        id: 101,
        name: 'Climbing',
        description: 'Vertical movement',
        tooltip: '',
        display_order: 2,
        is_active: true,
        parent_skill_id: 10,
        parent_skill_name: 'Athletics',
      },
    ],
  },
  {
    id: 11,
    name: 'Occult',
    category: 'knowledge',
    category_display: 'Knowledge',
    description: 'Arcane lore',
    tooltip: '',
    display_order: 2,
    is_active: true,
    specializations: [],
  },
];

describe('AnimaRitualForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function seedAnimaRitualData(queryClient: ReturnType<typeof createTestQueryClient>) {
    seedQueryData(queryClient, characterCreationKeys.statDefinitions(), mockStatDefinitions);
    seedQueryData(queryClient, characterCreationKeys.skills(), mockSkills);
    seedQueryData(queryClient, characterCreationKeys.resonances(), mockResonances);
    seedQueryData(queryClient, characterCreationKeys.draftAnimaRitual(), null);
  }

  describe('Rendering', () => {
    it('displays the anima ritual form card', () => {
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(<AnimaRitualForm />, { queryClient });

      expect(screen.getByText('Anima Recovery Ritual')).toBeInTheDocument();
      expect(screen.getByText('Stat')).toBeInTheDocument();
      expect(screen.getByText('Skill')).toBeInTheDocument();
      expect(screen.getByText('Resonance')).toBeInTheDocument();
    });

    it('shows combobox placeholders when no selection made', () => {
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(<AnimaRitualForm />, { queryClient });

      expect(screen.getByText('Select a stat...')).toBeInTheDocument();
      expect(screen.getByText('Select a skill...')).toBeInTheDocument();
      expect(screen.getByText('Select a resonance...')).toBeInTheDocument();
    });

    it('displays loading skeleton when data is loading', () => {
      const queryClient = createTestQueryClient();
      // Don't seed data - should show loading

      renderWithCharacterCreationProviders(<AnimaRitualForm />, { queryClient });

      expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
    });

    it('displays description textarea', () => {
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(<AnimaRitualForm />, { queryClient });

      expect(screen.getByText('Ritual Description')).toBeInTheDocument();
    });
  });

  describe('Combobox interaction', () => {
    it('opens stat combobox and shows stat options', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(<AnimaRitualForm />, { queryClient });

      const comboboxes = screen.getAllByRole('combobox');
      await user.click(comboboxes[0]);

      await waitFor(() => {
        expect(screen.getByText('Strength')).toBeInTheDocument();
        expect(screen.getByText('Agility')).toBeInTheDocument();
        expect(screen.getByText('Intellect')).toBeInTheDocument();
      });
    });

    it('opens skill combobox and shows skill options grouped by category', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(<AnimaRitualForm />, { queryClient });

      const comboboxes = screen.getAllByRole('combobox');
      await user.click(comboboxes[1]); // skill combobox

      await waitFor(() => {
        expect(screen.getByText('Athletics')).toBeInTheDocument();
        expect(screen.getByText('Occult')).toBeInTheDocument();
      });
    });
  });

  describe('Intensity shading with draft data', () => {
    it('renders stat combobox items with intensity based on draftStats', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      // Strength = 40 → display 4, intensity min(3, 4-2) = 2
      // Agility = 20 → display 2, intensity min(3, 2-2) = 0
      const draftStats: Stats = {
        strength: 40,
        agility: 20,
        stamina: 20,
        intellect: 20,
        perception: 20,
        willpower: 20,
        charm: 20,
        presence: 20,
        wits: 20,
      };

      renderWithCharacterCreationProviders(<AnimaRitualForm draftStats={draftStats} />, {
        queryClient,
      });

      const comboboxes = screen.getAllByRole('combobox');
      await user.click(comboboxes[0]); // stat combobox

      await waitFor(() => {
        expect(screen.getByText('Strength')).toBeInTheDocument();
      });

      // Strength has display value 4 > 2, so secondaryText should show "4"
      expect(screen.getByText('4')).toBeInTheDocument();
    });

    it('renders skill combobox items with intensity based on draftSkills', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      const draftSkills: Record<string, number> = {
        '10': 30, // Athletics = 30 → intensity min(3, floor(30/10)) = 3
        '11': 0, // Occult = 0 → intensity 0
      };

      renderWithCharacterCreationProviders(<AnimaRitualForm draftSkills={draftSkills} />, {
        queryClient,
      });

      const comboboxes = screen.getAllByRole('combobox');
      await user.click(comboboxes[1]); // skill combobox

      await waitFor(() => {
        expect(screen.getByText('Athletics')).toBeInTheDocument();
      });

      // Athletics invested 30, so secondaryText "30" shown
      expect(screen.getByText('30')).toBeInTheDocument();
    });

    it('renders resonance combobox items with intensity from projectedResonances', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      const projectedResonances: ProjectedResonance[] = [
        {
          resonance_id: 1,
          resonance_name: 'Shadow',
          total: 20,
          sources: [{ distinction_name: 'Patient', value: 20 }],
        },
      ];

      renderWithCharacterCreationProviders(
        <AnimaRitualForm projectedResonances={projectedResonances} />,
        { queryClient }
      );

      const comboboxes = screen.getAllByRole('combobox');
      await user.click(comboboxes[2]); // resonance combobox

      await waitFor(() => {
        expect(screen.getByText('Shadow')).toBeInTheDocument();
      });

      // Shadow total=20, secondaryText "+20"
      expect(screen.getByText('+20')).toBeInTheDocument();
    });
  });

  describe('Graceful handling of undefined props', () => {
    it('renders without draftStats', () => {
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(<AnimaRitualForm />, { queryClient });

      expect(screen.getByText('Anima Recovery Ritual')).toBeInTheDocument();
    });

    it('renders without draftSkills', () => {
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(<AnimaRitualForm draftStats={{} as Stats} />, {
        queryClient,
      });

      expect(screen.getByText('Anima Recovery Ritual')).toBeInTheDocument();
    });

    it('renders without projectedResonances', () => {
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(
        <AnimaRitualForm draftStats={{} as Stats} draftSkills={{}} />,
        { queryClient }
      );

      expect(screen.getByText('Anima Recovery Ritual')).toBeInTheDocument();
    });

    it('renders with all props provided', () => {
      const queryClient = createTestQueryClient();
      seedAnimaRitualData(queryClient);

      renderWithCharacterCreationProviders(
        <AnimaRitualForm draftStats={{} as Stats} draftSkills={{}} projectedResonances={[]} />,
        { queryClient }
      );

      expect(screen.getByText('Anima Recovery Ritual')).toBeInTheDocument();
    });
  });
});
