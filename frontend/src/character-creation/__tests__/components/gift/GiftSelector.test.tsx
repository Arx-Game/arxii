/**
 * GiftSelector Component Tests (#2426 Task 10)
 *
 * Ports the selection-writes-draft-keys pattern from the old
 * CantripSelector.test.tsx (now removed with the cantrip UI).
 */

import { codexKeys } from '@/codex/queries';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { GiftSelector } from '../../../components/gift/GiftSelector';
import { characterCreationKeys } from '../../../queries';
import type { CharacterDraft } from '../../../types';
import {
  createMockDraft,
  mockCGGiftOptions,
  mockCodexEntry,
  mockPath,
  mockTradition,
} from '../../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../../testUtils';

const updateDraftMock = vi.fn();

// Mock the API module — updateDraft is the only call the mutation actually fires;
// getCGGifts is never invoked because the query cache is pre-seeded below.
vi.mock('../../../api', () => ({
  getCGGifts: vi.fn(),
  updateDraft: (...args: unknown[]) => updateDraftMock(...args),
}));

function renderSelector(draft: CharacterDraft) {
  const queryClient = createTestQueryClient();
  seedQueryData(queryClient, characterCreationKeys.cgGifts(draft.id), mockCGGiftOptions);
  // The gift options include a codex_entry_id (12) — CodexTerm/CodexModal mount
  // unconditionally and fetch on render, not just on open. Seed it so that
  // fetch never hits the (unmocked, real) codex API in tests.
  seedQueryData(queryClient, codexKeys.entry(12), mockCodexEntry(12));
  return renderWithCharacterCreationProviders(<GiftSelector draft={draft} />, { queryClient });
}

describe('GiftSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateDraftMock.mockResolvedValue({});
  });

  it('renders gift cards from the gift-options query', () => {
    const draft = createMockDraft({
      id: 1,
      selected_tradition: mockTradition,
      selected_path: mockPath,
    });
    renderSelector(draft);

    expect(screen.getByText('Whispers of Shadow')).toBeInTheDocument();
    expect(screen.getByText('Flame Ascendant')).toBeInTheDocument();
  });

  it('shows a prompt instead of gift cards when no tradition is selected', () => {
    const draft = createMockDraft({ id: 1, selected_path: mockPath });
    renderSelector(draft);

    expect(screen.getByText(/select a tradition/i)).toBeInTheDocument();
    expect(screen.queryByText('Whispers of Shadow')).not.toBeInTheDocument();
  });

  it('selecting a gift writes selected_gift_id and clears selected_technique_ids', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      id: 1,
      selected_tradition: mockTradition,
      selected_path: mockPath,
      draft_data: { selected_gift_id: 2, selected_technique_ids: [99] },
    });
    renderSelector(draft);

    // Click the description, not the gift name — the name is wrapped in a
    // CodexTerm button (codex_entry_id 12) that stops click propagation to
    // open the lore modal instead of selecting the card.
    await user.click(screen.getByText('Mastery over shadows and darkness.'));

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          draft_data: expect.objectContaining({
            selected_gift_id: 1,
            selected_technique_ids: [],
          }),
        })
      );
    });
  });
});
