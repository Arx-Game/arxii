/**
 * TechniqueSelector Component Tests (#2426 Task 10)
 *
 * Covers the technique-pick budget cap ("n of m chosen"), the signature-row
 * badge, and that selection writes `selected_technique_ids` — porting the
 * old CantripSelector.test.tsx selection-writes-draft-keys pattern.
 */

import { codexKeys } from '@/codex/queries';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { TechniqueSelector } from '../../../components/gift/TechniqueSelector';
import { characterCreationKeys } from '../../../queries';
import type { CharacterDraft } from '../../../types';
import {
  createMockDraft,
  mockCGTechniqueOptions,
  mockCodexEntry,
  mockTradition,
} from '../../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../../testUtils';

const updateDraftMock = vi.fn();

vi.mock('../../../api', () => ({
  getCGTechniqueOptions: vi.fn(),
  updateDraft: (...args: unknown[]) => updateDraftMock(...args),
}));

const GIFT_ID = 1;

function renderSelector(draft: CharacterDraft) {
  const queryClient = createTestQueryClient();
  seedQueryData(
    queryClient,
    characterCreationKeys.cgTechniqueOptions(draft.id, GIFT_ID),
    mockCGTechniqueOptions
  );
  // "Veil of Whispers" carries codex_entry_id 20 — CodexTerm/CodexModal mount
  // unconditionally and fetch on render, not just on open. Seed it so that
  // fetch never hits the (unmocked, real) codex API in tests.
  seedQueryData(queryClient, codexKeys.entry(20), mockCodexEntry(20));
  return renderWithCharacterCreationProviders(
    <TechniqueSelector draft={draft} giftId={GIFT_ID} />,
    { queryClient }
  );
}

describe('TechniqueSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateDraftMock.mockResolvedValue({});
  });

  it('groups techniques by category using the archetype labels', () => {
    const draft = createMockDraft({ id: 1, selected_tradition: mockTradition });
    renderSelector(draft);

    expect(screen.getByText('Offense')).toBeInTheDocument();
    expect(screen.getByText('Defense')).toBeInTheDocument();
    expect(screen.getByText('Utility')).toBeInTheDocument();
  });

  it('badges signature rows with the tradition name', () => {
    const draft = createMockDraft({ id: 1, selected_tradition: mockTradition });
    renderSelector(draft);

    expect(screen.getByText('The Whispering Path signature')).toBeInTheDocument();
  });

  it('shows the "n of m chosen" budget banner', () => {
    const draft = createMockDraft({
      id: 1,
      selected_tradition: mockTradition,
      starting_technique_picks: 2,
      draft_data: { selected_technique_ids: [10] },
    });
    renderSelector(draft);

    expect(screen.getByText('1 of 2 chosen')).toBeInTheDocument();
  });

  it('selecting a technique writes selected_technique_ids', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      id: 1,
      selected_tradition: mockTradition,
      starting_technique_picks: 2,
      draft_data: { selected_technique_ids: [] },
    });
    renderSelector(draft);

    await user.click(screen.getByText('Shadow Strike'));

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          draft_data: expect.objectContaining({ selected_technique_ids: [10] }),
        })
      );
    });
  });

  it('deselecting an already-picked technique is always allowed, even at budget', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      id: 1,
      selected_tradition: mockTradition,
      starting_technique_picks: 1,
      draft_data: { selected_technique_ids: [10] },
    });
    renderSelector(draft);

    await user.click(screen.getByText('Shadow Strike'));

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          draft_data: expect.objectContaining({ selected_technique_ids: [] }),
        })
      );
    });
  });

  it('caps additional picks at the budget — clicking an unselected card is a no-op', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      id: 1,
      selected_tradition: mockTradition,
      starting_technique_picks: 1,
      draft_data: { selected_technique_ids: [10] },
    });
    renderSelector(draft);

    // Already at budget (1 of 1) — clicking a different, unselected technique
    // must not add it.
    await user.click(screen.getByText('Umbral Wall'));

    expect(updateDraftMock).not.toHaveBeenCalled();
  });
});
