/**
 * GlimpseSection Component Tests (#2427, offers slot #3675, folio-grammar
 * fix round 1).
 *
 * Mirrors GiftSelector.test.tsx's mock/provider setup: the catalog and draft
 * distinctions queries are pre-seeded, and the API module is mocked so only
 * updateDraft is actually exercised.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { distinctionKeys } from '@/hooks/useDistinctions';
import type { TagOffer } from '@/magic/components/glimpse/glimpseTypes';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import { unreachableClasses } from '../offers/classGuard';
import { GlimpseSection } from '../../../components/gift/GlimpseSection';
import { characterCreationKeys } from '../../../queries';
import type {
  CGExplanations,
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

function tagOffer(overrides: Partial<TagOffer> & Pick<TagOffer, 'offer_id' | 'name'>): TagOffer {
  return {
    distinction_id: overrides.offer_id,
    player_line: `Player line for ${overrides.name}.`,
    cost_per_rank: 5,
    max_rank: 1,
    ...overrides,
  };
}

const TONE_WONDER: GlimpseTagOption = {
  id: 1,
  axis: 'TONE',
  name: 'Wonder',
  slug: 'wonder',
  description: 'Awe at the impossible.',
  example: 'The light bent around her hand like water.',
  sort_order: 1,
  offers: [tagOffer({ offer_id: 201, name: 'Keen Senses', cost_per_rank: 5 })],
};

const TONE_DREAD: GlimpseTagOption = {
  id: 2,
  axis: 'TONE',
  name: 'Dread',
  slug: 'dread',
  description: 'Fear at the impossible.',
  example: 'The shadows breathed.',
  sort_order: 2,
  offers: [tagOffer({ offer_id: 202, name: 'Marked', cost_per_rank: 5 })],
};

const CONSEQUENCE_A: GlimpseTagOption = {
  id: 3,
  axis: 'CONSEQUENCE',
  name: 'A Debt Incurred',
  slug: 'debt-incurred',
  description: 'Something was owed after.',
  example: 'The price came due at midnight.',
  sort_order: 1,
  offers: [tagOffer({ offer_id: 301, name: 'Wrathful', cost_per_rank: -5 })],
};

const CONSEQUENCE_B: GlimpseTagOption = {
  id: 4,
  axis: 'CONSEQUENCE',
  name: 'A Door Opened',
  slug: 'door-opened',
  description: 'Something new became possible.',
  example: 'A door that was not there before, now was.',
  sort_order: 2,
  offers: [tagOffer({ offer_id: 302, name: 'Impoverished', cost_per_rank: -25 })],
};

const WITNESS_ALONE: GlimpseTagOption = {
  id: 5,
  axis: 'WITNESS',
  name: 'Alone',
  slug: 'alone',
  description: 'No one else saw.',
  example: 'She told no one.',
  sort_order: 1,
  offers: [tagOffer({ offer_id: 501, name: 'Solitary', cost_per_rank: -10 })],
};

const CATALOG: GlimpseTagOption[] = [
  TONE_WONDER,
  TONE_DREAD,
  CONSEQUENCE_A,
  CONSEQUENCE_B,
  WITNESS_ALONE,
];

function visibleOffer(tag: GlimpseTagOption, overrides: Partial<VisibleOffer> = {}): VisibleOffer {
  const catalogOffer = tag.offers[0];
  return {
    offer_id: catalogOffer.offer_id,
    distinction_id: catalogOffer.distinction_id,
    name: catalogOffer.name,
    player_line: catalogOffer.player_line,
    chapter: 'glimpse',
    arrives_as: 'choice',
    opener_label: tag.name,
    cost_per_rank: catalogOffer.cost_per_rank,
    max_rank: catalogOffer.max_rank,
    is_locked: false,
    lock_reason: '',
    opener_key: '',
    first_look: false,
    held: false,
    effect_line: '',
    ...overrides,
  };
}

const OFFERS_RESPONSE: OffersResponse = {
  offers: [
    visibleOffer(TONE_WONDER),
    visibleOffer(TONE_DREAD),
    visibleOffer(CONSEQUENCE_A),
    visibleOffer(CONSEQUENCE_B),
    visibleOffer(WITNESS_ALONE),
  ],
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

function renderSection(draft: CharacterDraft, copy: CGExplanations = {}) {
  const queryClient = createTestQueryClient();
  seedQueryData(queryClient, characterCreationKeys.glimpseTags(), CATALOG);
  seedQueryData(queryClient, distinctionKeys.draftDistinctions(draft.id), [DRAFT_DISTINCTION]);
  seedQueryData(
    queryClient,
    characterCreationKeys.draftOffers(draft.id, 'glimpse'),
    OFFERS_RESPONSE
  );
  seedQueryData(queryClient, characterCreationKeys.explanations(), copy);
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

  it('renders every axis as its own field, with a pick button per tag, all visible at once', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    // TONE (single-select) and CONSEQUENCE/WITNESS (multi) are all present
    // simultaneously; no accordion collapsing any of them away.
    expect(screen.getByText('How it felt')).toBeInTheDocument();
    expect(screen.getByText('What it left behind')).toBeInTheDocument();
    expect(screen.getByText('Who saw')).toBeInTheDocument();

    const wonderPick = screen.getByRole('button', { name: /Wonder/ });
    expect(wonderPick).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('Awe at the impossible.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Dread/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /A Debt Incurred/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /A Door Opened/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Alone/ })).toBeInTheDocument();
  });

  it('tags an axis field with its display name and arity (choose one vs choose any)', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    expect(screen.getByText('Tone')).toBeInTheDocument();
    expect(screen.getByText('choose one')).toBeInTheDocument();
    expect(screen.getByText('Consequence')).toBeInTheDocument();
    expect(screen.getAllByText('choose any').length).toBeGreaterThanOrEqual(1);
  });

  it('selecting a tone card PATCHes draft_data.glimpse_tag_ids', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    await user.click(screen.getByRole('button', { name: /Wonder/ }));

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

  it("a chosen tag's offers render in their own sub-block under that axis, and nowhere else", () => {
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1] } });
    renderSection(draft);

    // Wonder (selected, TONE) opens Keen Senses.
    expect(screen.getByText('Keen Senses')).toBeInTheDocument();
    // Dread (unselected, same TONE axis) does not open Marked.
    expect(screen.queryByText('Marked')).not.toBeInTheDocument();
    // Consequence and Witness have no selection at all.
    expect(screen.queryByText('Wrathful')).not.toBeInTheDocument();
    expect(screen.queryByText('Impoverished')).not.toBeInTheDocument();
    expect(screen.queryByText('Solitary')).not.toBeInTheDocument();
  });

  it('two chosen tags on the same (multi-select) axis each get their own offers sub-block and heading', () => {
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [3, 4] } });
    renderSection(draft, {
      'glimpse_offers_heading_debt-incurred': 'What the debt was',
      'glimpse_offers_heading_door-opened': 'What the door led to',
    });

    expect(screen.getByText('Wrathful')).toBeInTheDocument();
    expect(screen.getByText('Impoverished')).toBeInTheDocument();
    // Distinct per-tag headings, not one merged heading for the whole axis
    // (the gap Task 13's per-axis renderOffers slot could not close).
    expect(screen.getByText('What the debt was')).toBeInTheDocument();
    expect(screen.getByText('What the door led to')).toBeInTheDocument();
  });

  it('falls back to the shared offers heading, per axis, when no per-tag copy is authored', () => {
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [3, 4] } });
    renderSection(draft);

    // Both sub-blocks fall all the way back to the same generic heading,
    // still two separate blocks, each with its own offer underneath.
    expect(screen.getAllByText('What it left in you')).toHaveLength(2);
    expect(screen.getByText('Wrathful')).toBeInTheDocument();
    expect(screen.getByText('Impoverished')).toBeInTheDocument();
  });

  it('registers the prose textarea under glimpse_story via the passed-down field', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      id: 1,
      draft_data: { glimpse_story: 'Once, in the dark' },
    });
    const { glimpseProseField } = renderSection(draft);

    const textarea = screen.getByLabelText('Your story') as HTMLTextAreaElement;
    expect(textarea.value).toBe('Once, in the dark');

    await user.type(textarea, '!');

    expect(glimpseProseField.onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        target: expect.objectContaining({ name: 'glimpse_story' }),
      })
    );
  });

  it('renders the default story hint under the story textarea', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    expect(
      screen.getByText('The detail behind any of the picks above goes here; the picks stay short.')
    ).toBeInTheDocument();
  });

  it("a route-closed distinction's hint prints exactly once, under the tag that would have opened it (#3675 fix round 2)", () => {
    // The demo's "Highborn under Public" case: Highborn is closed by the
    // route, so it never appears in `offers`, only in `closed` with
    // `opener_ids: [601]` matching the Public tag's own offer id (#3675 final
    // fix F4: matched by offer id, never `opener_labels`/tag name).
    const publicTag: GlimpseTagOption = {
      id: 6,
      axis: 'WITNESS',
      name: 'Public',
      slug: 'public',
      description: 'Everyone; there is no taking it back.',
      example: 'The whole street saw.',
      sort_order: 2,
      offers: [tagOffer({ offer_id: 601, name: 'Highborn', cost_per_rank: 20 })],
    };
    const closedOffersResponse: OffersResponse = {
      offers: [
        visibleOffer(TONE_WONDER),
        visibleOffer(TONE_DREAD),
        visibleOffer(CONSEQUENCE_A),
        visibleOffer(CONSEQUENCE_B),
        visibleOffer(WITNESS_ALONE),
      ],
      closed: [
        {
          distinction_id: 601,
          name: 'Highborn',
          reason: 'The Cradle raised this character; the route closed it.',
          opener_labels: ['Public'],
          opener_ids: [601],
        },
      ],
    };
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [6] } });
    const queryClient = createTestQueryClient();
    seedQueryData(queryClient, characterCreationKeys.glimpseTags(), [...CATALOG, publicTag]);
    seedQueryData(queryClient, distinctionKeys.draftDistinctions(draft.id), [DRAFT_DISTINCTION]);
    seedQueryData(
      queryClient,
      characterCreationKeys.draftOffers(draft.id, 'glimpse'),
      closedOffersResponse
    );
    seedQueryData(queryClient, characterCreationKeys.explanations(), {});
    const glimpseProseField = {
      name: 'glimpse_story' as const,
      onChange: vi.fn(),
      onBlur: vi.fn(),
      ref: vi.fn(),
    };
    renderWithCharacterCreationProviders(
      <GlimpseSection draft={draft} glimpseProseField={glimpseProseField} />,
      { queryClient }
    );

    expect(screen.getAllByText(/Closed on this road/)).toHaveLength(1);
    expect(
      screen.getByText(/Highborn: The Cradle raised this character; the route closed it\./)
    ).toBeInTheDocument();
  });

  it('matches a closed row by opener_ids, not by opener_labels/tag name (#3675 final fix F4)', () => {
    // opener_labels deliberately does NOT name this tag (a stale/mismatched
    // label would have failed a name match), but opener_ids does carry the
    // tag's own offer id -- the hint must still print under Public.
    const publicTag: GlimpseTagOption = {
      id: 6,
      axis: 'WITNESS',
      name: 'Public',
      slug: 'public',
      description: 'Everyone; there is no taking it back.',
      example: 'The whole street saw.',
      sort_order: 2,
      offers: [tagOffer({ offer_id: 601, name: 'Highborn', cost_per_rank: 20 })],
    };
    const closedOffersResponse: OffersResponse = {
      offers: [
        visibleOffer(TONE_WONDER),
        visibleOffer(TONE_DREAD),
        visibleOffer(CONSEQUENCE_A),
        visibleOffer(CONSEQUENCE_B),
        visibleOffer(WITNESS_ALONE),
      ],
      closed: [
        {
          distinction_id: 601,
          name: 'Highborn',
          reason: 'The Cradle raised this character; the route closed it.',
          opener_labels: ['Some Other Tag'],
          opener_ids: [601],
        },
      ],
    };
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [6] } });
    const queryClient = createTestQueryClient();
    seedQueryData(queryClient, characterCreationKeys.glimpseTags(), [...CATALOG, publicTag]);
    seedQueryData(queryClient, distinctionKeys.draftDistinctions(draft.id), [DRAFT_DISTINCTION]);
    seedQueryData(
      queryClient,
      characterCreationKeys.draftOffers(draft.id, 'glimpse'),
      closedOffersResponse
    );
    seedQueryData(queryClient, characterCreationKeys.explanations(), {});
    const glimpseProseField = {
      name: 'glimpse_story' as const,
      onChange: vi.fn(),
      onBlur: vi.fn(),
      ref: vi.fn(),
    };
    renderWithCharacterCreationProviders(
      <GlimpseSection draft={draft} glimpseProseField={glimpseProseField} />,
      { queryClient }
    );

    expect(
      screen.getByText(/Highborn: The Cradle raised this character; the route closed it\./)
    ).toBeInTheDocument();
  });

  it('a route-closed distinction prints nowhere when the tag that would have opened it is not chosen', () => {
    const publicTag: GlimpseTagOption = {
      id: 6,
      axis: 'WITNESS',
      name: 'Public',
      slug: 'public',
      description: 'Everyone; there is no taking it back.',
      example: 'The whole street saw.',
      sort_order: 2,
      offers: [tagOffer({ offer_id: 601, name: 'Highborn', cost_per_rank: 20 })],
    };
    const closedOffersResponse: OffersResponse = {
      offers: [
        visibleOffer(TONE_WONDER),
        visibleOffer(TONE_DREAD),
        visibleOffer(CONSEQUENCE_A),
        visibleOffer(CONSEQUENCE_B),
        visibleOffer(WITNESS_ALONE),
      ],
      closed: [
        {
          distinction_id: 601,
          name: 'Highborn',
          reason: 'The Cradle raised this character; the route closed it.',
          opener_labels: ['Public'],
          opener_ids: [601],
        },
      ],
    };
    // Public is never chosen here.
    const draft = createMockDraft({ id: 1, draft_data: {} });
    const queryClient = createTestQueryClient();
    seedQueryData(queryClient, characterCreationKeys.glimpseTags(), [...CATALOG, publicTag]);
    seedQueryData(queryClient, distinctionKeys.draftDistinctions(draft.id), [DRAFT_DISTINCTION]);
    seedQueryData(
      queryClient,
      characterCreationKeys.draftOffers(draft.id, 'glimpse'),
      closedOffersResponse
    );
    seedQueryData(queryClient, characterCreationKeys.explanations(), {});
    const glimpseProseField = {
      name: 'glimpse_story' as const,
      onChange: vi.fn(),
      onBlur: vi.fn(),
      ref: vi.fn(),
    };
    renderWithCharacterCreationProviders(
      <GlimpseSection draft={draft} glimpseProseField={glimpseProseField} />,
      { queryClient }
    );

    expect(screen.queryByText(/Closed on this road/)).not.toBeInTheDocument();
  });

  it('renders no heading of its own: the h2 above this mount is GiftStage’s job', () => {
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    expect(screen.queryByText('The Glimpse')).not.toBeInTheDocument();
  });

  it('selects a tag card via the keyboard (Enter, native button semantics)', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 1, draft_data: {} });
    renderSection(draft);

    screen.getByRole('button', { name: /Wonder/ }).focus();
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

  it('emits no class hook that cg.css has no rule reaching it (#3667 shape)', () => {
    const draft = createMockDraft({ id: 1, draft_data: { glimpse_tag_ids: [1, 3, 4] } });
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
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <GlimpseSection draft={draft} glimpseProseField={glimpseProseField} />
      </div>,
      { queryClient }
    );
    expect(unreachableClasses(container)).toEqual([]);
  });
});
