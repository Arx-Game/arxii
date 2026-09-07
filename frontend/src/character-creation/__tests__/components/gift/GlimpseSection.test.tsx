/**
 * GlimpseSection Component Tests (#2427, offers slot #3675)
 *
 * Mirrors GiftSelector.test.tsx's mock/provider setup: the catalog and draft
 * distinctions queries are pre-seeded, and the API module is mocked so only
 * updateDraft is actually exercised.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { distinctionKeys } from '@/hooks/useDistinctions';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import { GlimpseSection } from '../../../components/gift/GlimpseSection';
import { characterCreationKeys } from '../../../queries';
import type {
  CharacterDraft,
  GlimpseTagOption,
  OffersResponse,
  VisibleOffer,
} from '../../../types';
import { createMockDraft } from '../../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../../testUtils';

const updateDraftMock = vi.fn();
const syncDistinctionsMutate = vi.fn();

// getGlimpseTags/getDraftOffers/getCGExplanations are never invoked because
// the query caches are pre-seeded below.
vi.mock('../../../api', () => ({
  getGlimpseTags: vi.fn(),
  getDraftOffers: vi.fn(),
  getCGExplanations: vi.fn(),
  updateDraft: (...args: unknown[]) => updateDraftMock(...args),
}));

vi.mock('@/hooks/useDistinctions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/useDistinctions')>()),
  useSyncDistinctions: () => ({ mutate: syncDistinctionsMutate }),
}));

const TONE_WONDER: GlimpseTagOption = {
  id: 1,
  axis: 'TONE',
  name: 'Wonder',
  slug: 'wonder',
  description: 'Awe at the impossible.',
  example: 'The light bent around her hand like water.',
  sort_order: 1,
  offers: [],
};

const TONE_DREAD: GlimpseTagOption = {
  id: 2,
  axis: 'TONE',
  name: 'Dread',
  slug: 'dread',
  description: 'Fear at the impossible.',
  example: 'The shadows breathed.',
  sort_order: 2,
  offers: [],
};

const WITNESS_ALONE: GlimpseTagOption = {
  id: 5,
  axis: 'WITNESS',
  name: 'Alone',
  slug: 'alone',
  description: 'No one else saw.',
  example: 'She told no one.',
  sort_order: 1,
  offers: [],
};

const CATALOG: GlimpseTagOption[] = [TONE_WONDER, TONE_DREAD, WITNESS_ALONE];

/** Wonder is the selected tag in the tests below; this offer should render. */
const wonderOffer: VisibleOffer = {
  offer_id: 201,
  distinction_id: 20,
  name: 'Keen Senses',
  player_line: 'You notice things others miss.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: 'Wonder',
  cost_per_rank: 5,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
};

/** Dread is on the same (open) TONE axis but is NOT selected; must not render. */
const dreadOffer: VisibleOffer = {
  offer_id: 202,
  distinction_id: 21,
  name: 'Marked',
  player_line: 'Something about you unsettles people.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: 'Dread',
  cost_per_rank: 5,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
};

/** Alone's axis (WITNESS) has nothing selected at all; must not render. */
const aloneOffer: VisibleOffer = {
  offer_id: 203,
  distinction_id: 22,
  name: 'Solitary',
  player_line: 'You keep your own counsel.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: 'Alone',
  cost_per_rank: 5,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
};

const OFFERS_RESPONSE: OffersResponse = {
  offers: [wonderOffer, dreadOffer, aloneOffer],
  closed: [],
};

const DRAFT_DISTINCTION: DraftDistinctionEntry = {
  distinction_id: 10,
  distinction_name: 'Keen Senses',
  distinction_slug: 'keen-senses',
  category_slug: 'advantages',
  rank: 1,
  cost: 2,
  notes: '',
  offer_ids: [],
  sources: [],
  arrivals: [],
};

function renderSection(draft: CharacterDraft) {
  const queryClient = createTestQueryClient();
  seedQueryData(queryClient, characterCreationKeys.glimpseTags(), CATALOG);
  seedQueryData(queryClient, distinctionKeys.draftDistinctions(draft.id), [DRAFT_DISTINCTION]);
  seedQueryData(
    queryClient,
    characterCreationKeys.draftOffers(draft.id, 'glimpse'),
    OFFERS_RESPONSE
  );
  seedQueryData(queryClient, characterCreationKeys.explanations(), {});
  const glimpseProseField = {
    name: 'glimpse_story' as const,
    onChange: vi.fn(),
    onBlur: vi.fn(),
    ref: vi.fn(),
  };
  const result = renderWithCharacterCreationProviders(
    <GlimpseSection draft={draft} glimpseProseField={glimpseProseField} />,
    { queryClient }
  );
  return { ...result, glimpseProseField };
}

describe('GlimpseSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateDraftMock.mockResolvedValue({});
  });

  it('selecting a tone card PATCHes draft_data.glimpse_tag_ids', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    await user.click(screen.getByText('Wonder'));

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          draft_data: expect.objectContaining({ glimpse_tag_ids: [1] }),
        })
      );
    });
  });

  it('never PATCHes glimpse_linked_distinction_ids (#3675: offers are chapter-scoped now)', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1] } });
    renderSection(draft);

    // The Wonder-opened offer, Keen Senses, is toggleable; clicking it
    // should write through useSyncDistinctions, never through updateDraft.
    await user.click(screen.getByRole('button', { name: /Keen Senses/ }));

    await waitFor(() => {
      expect(syncDistinctionsMutate).toHaveBeenCalled();
    });
    for (const call of updateDraftMock.mock.calls) {
      const body = call[1] as { draft_data?: Record<string, unknown> };
      expect(body.draft_data ?? {}).not.toHaveProperty('glimpse_linked_distinction_ids');
    }
  });

  it('renders offers under the axis whose tag is selected, and nowhere else', () => {
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1] } });
    renderSection(draft);

    // Wonder (selected, TONE) opens Keen Senses.
    expect(screen.getByText('Keen Senses')).toBeInTheDocument();
    // Dread (unselected, same TONE axis) does not open Marked, even though
    // its axis section is the one open by default.
    expect(screen.queryByText('Marked')).not.toBeInTheDocument();
    // Alone's axis (WITNESS) has no selection at all.
    expect(screen.queryByText('Solitary')).not.toBeInTheDocument();
  });

  it('registers the prose textarea under glimpse_story via the passed-down field', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      id: 1,
      draft_data: { glimpse_story: 'Once, in the dark' },
    });
    const { glimpseProseField } = renderSection(draft);

    const textarea = screen.getByLabelText('Your Story') as HTMLTextAreaElement;
    expect(textarea.value).toBe('Once, in the dark');

    await user.type(textarea, '!');

    expect(glimpseProseField.onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        target: expect.objectContaining({ name: 'glimpse_story' }),
      })
    );
  });

  it('renders GlimpseFlow default heading when no heading prop is passed', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    expect(screen.getByText('The Glimpse')).toBeInTheDocument();
  });

  it('renders the default story hint under the story textarea', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    expect(
      screen.getByText('The detail behind any of the picks above goes here; the picks stay short.')
    ).toBeInTheDocument();
  });

  it('passes a staff-authored heading through to GlimpseFlow', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    const queryClient = createTestQueryClient();
    seedQueryData(queryClient, characterCreationKeys.glimpseTags(), CATALOG);
    seedQueryData(queryClient, distinctionKeys.draftDistinctions(draft.id), [DRAFT_DISTINCTION]);
    seedQueryData(
      queryClient,
      characterCreationKeys.draftOffers(draft.id, 'glimpse'),
      OFFERS_RESPONSE
    );
    seedQueryData(queryClient, characterCreationKeys.explanations(), {});
    const glimpseProseField = {
      name: 'glimpse_story' as const,
      onChange: vi.fn(),
      onBlur: vi.fn(),
      ref: vi.fn(),
    };
    renderWithCharacterCreationProviders(
      <GlimpseSection
        draft={draft}
        glimpseProseField={glimpseProseField}
        heading="A Door You Cannot Unsee"
      />,
      { queryClient }
    );

    expect(screen.getByText('A Door You Cannot Unsee')).toBeInTheDocument();
    expect(screen.queryByText('The Glimpse')).not.toBeInTheDocument();
  });

  it('selects a tag card via the keyboard (Enter)', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    (screen.getByText('Wonder').closest('[role="button"]') as HTMLElement | null)?.focus();
    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(updateDraftMock).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          draft_data: expect.objectContaining({ glimpse_tag_ids: [1] }),
        })
      );
    });
  });
});
