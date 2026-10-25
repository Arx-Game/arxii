/**
 * GiftStage Resonance step against the real fetch (#4665).
 *
 * The Resonance and Affinity pickers once called /api/mechanics/types/, which no URL
 * registers, and every test mocked useResonances, so the 404 never showed. Here
 * useResonances runs for real and only apiFetch is stubbed, by URL.
 */

import { screen, within } from '@testing-library/react';
import { vi } from 'vitest';
import { apiFetch } from '@/evennia_replacements/api';
import { GiftStage } from '../../components/GiftStage';
import { createMockDraft, mockCGExplanations, mockPath, mockTradition } from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';

vi.mock('@/evennia_replacements/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/evennia_replacements/api')>()),
  apiFetch: vi.fn(),
}));

vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
  useTraditions: () => ({ data: [mockTradition], isLoading: false }),
  useSelectTradition: () => ({ mutate: vi.fn(), isPending: false }),
  useTraditionPerspectives: () => ({ data: [] }),
  useCGGifts: () => ({ data: [], isLoading: false }),
  useCGTechniqueOptions: () => ({ data: [], isLoading: false }),
  useGlimpseTags: () => ({ data: [], isLoading: false }),
  useDraftOffers: () => ({ data: { offers: [], closed: [] }, isLoading: false }),
  useSkills: () => ({ data: [] }),
  useStatDefinitions: () => ({ data: [] }),
  usePathSkillSuggestions: () => ({ data: [] }),
  useCGPointBudget: () => ({ data: { starting_points: 100 } }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: [] }),
  useSyncDistinctions: () => ({ mutate: vi.fn() }),
}));

const served = [
  {
    id: 41,
    name: 'Tidecall',
    affinity: 2,
    affinity_name: 'Primal',
    description: 'The pull of deep water.',
    codex_entry_id: null,
  },
];

beforeEach(() => {
  vi.mocked(apiFetch).mockImplementation(async (url: string) =>
    url === '/api/magic/resonances/'
      ? ({ ok: true, json: () => Promise.resolve(served) } as Response)
      : ({ ok: false, status: 404, json: () => Promise.resolve({}) } as Response)
  );
});

describe('GiftStage Resonance step (#4665)', () => {
  it('lists the resonances served at /api/magic/resonances/ with their affinity', async () => {
    const draft = createMockDraft({
      selected_path: mockPath,
      selected_tradition: mockTradition,
      draft_data: { selected_gift_id: 1, selected_technique_ids: [1] },
    });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const list = await screen.findByRole('list', { name: 'Resonances' });
    expect(await within(list).findByText('Tidecall')).toBeInTheDocument();
    expect(within(list).getByText('Primal')).toBeInTheDocument();
    expect(within(list).getByText('The pull of deep water.')).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith('/api/magic/resonances/');
  });
});
