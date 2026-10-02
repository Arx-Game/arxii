/**
 * PersonalizationPanel race-safety test (#4099 fix round 1).
 *
 * Two panels for two different techniques each build their own
 * `technique_personalizations` patch. If each one reads the OTHER's starting
 * point from its own stale render-time `draft` prop instead of the live query
 * cache, the second write can clobber the first's pick. This test uses the
 * REAL `useUpdateDraft` (and its optimistic `onMutate` cache merge in
 * queries.ts) rather than mocking it out, so the cache round-trip actually
 * runs; only the network call (`api.updateDraft`) is stubbed.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { PersonalizationPanel } from '../../../components/gift/PersonalizationPanel';
import { characterCreationKeys } from '../../../queries';
import type { CharacterDraft, TechniquePersonalizationOptions } from '../../../types';
import { createMockDraft, mockCGExplanations, mockPersonalizationOptions } from '../../fixtures';
import { createTestQueryClient, renderWithCharacterCreationProviders } from '../../testUtils';

const updateDraftMock = vi.fn();

vi.mock('../../../api', () => ({
  updateDraft: (...args: unknown[]) => updateDraftMock(...args),
}));

describe('PersonalizationPanel race safety', () => {
  beforeEach(() => {
    updateDraftMock.mockReset();
    // Echo back whatever was PATCHed, as the real endpoint would.
    updateDraftMock.mockImplementation((draftId: number, data: Record<string, unknown>) =>
      Promise.resolve({ id: draftId, ...data })
    );
  });

  it('two panels editing back to back from the same initial render both survive', async () => {
    const user = userEvent.setup();
    const techniqueA = mockPersonalizationOptions.technique_id;
    const techniqueB = 777;
    const optionsB: TechniquePersonalizationOptions = {
      ...mockPersonalizationOptions,
      technique_id: techniqueB,
      technique_name: 'Other Technique',
    };

    const draft = createMockDraft({
      id: 1,
      draft_data: {
        selected_technique_ids: [techniqueA, techniqueB],
      },
    });

    const queryClient = createTestQueryClient();
    // No component in this test subscribes to the draft query via `useQuery`
    // (only `PersonalizationPanel`'s direct `getQueryData`/mutation calls
    // touch it), so with the default test `gcTime: 0` it would otherwise be
    // garbage-collected the instant it has zero observers.
    queryClient.setQueryDefaults(characterCreationKeys.draft(), {
      gcTime: Infinity,
      staleTime: Infinity,
    });
    queryClient.setQueryData(characterCreationKeys.draft(), draft);

    renderWithCharacterCreationProviders(
      <>
        <PersonalizationPanel
          draft={draft}
          options={mockPersonalizationOptions}
          copy={mockCGExplanations}
        />
        <PersonalizationPanel draft={draft} options={optionsB} copy={mockCGExplanations} />
      </>,
      { queryClient }
    );

    // Each panel's price section starts collapsed (demo-fidelity fix round) —
    // open both before the stance buttons underneath exist in the DOM.
    for (const summaryButton of screen.getAllByTestId('personalize-summary-price')) {
      await user.click(summaryButton);
    }

    const priceButtons = screen.getAllByRole('button', { name: /Frost on the skin/ });
    expect(priceButtons).toHaveLength(2);

    // Neither panel ever re-renders with an updated `draft` prop in this
    // test (no parent re-passes it) — the only way the second click's write
    // can see the first click's pick is by reading the query cache fresh at
    // mutation time, not the stale render-time prop. Waiting for the first
    // mutation's optimistic cache write to land before the second click
    // keeps the assertion deterministic while still exercising exactly that
    // path: the old (pre-fix) code built its patch purely from the
    // component's own closed-over `draft` prop and would lose technique A's
    // pick here regardless of timing.
    await user.click(priceButtons[0]);
    await waitFor(() => {
      const afterFirst = queryClient.getQueryData<CharacterDraft>(characterCreationKeys.draft());
      expect(
        afterFirst?.draft_data.technique_personalizations?.[String(techniqueA)]?.price_id
      ).toBe(mockPersonalizationOptions.prices[0].id);
    });
    await user.click(priceButtons[1]);

    const cached = queryClient.getQueryData<CharacterDraft>(characterCreationKeys.draft());
    const picks = cached?.draft_data.technique_personalizations ?? {};
    expect(picks[String(techniqueA)]?.price_id).toBe(mockPersonalizationOptions.prices[0].id);
    expect(picks[String(techniqueB)]?.price_id).toBe(optionsB.prices[0].id);
  });
});
