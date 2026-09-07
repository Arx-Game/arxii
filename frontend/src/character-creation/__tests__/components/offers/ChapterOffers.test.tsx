/**
 * ChapterOffers Component Tests (#3675).
 *
 * The reusable offers block every CG chapter mounts in place of the retired
 * Distinctions stage: renders a chapter's visible offers as folio stances,
 * writes selection through `useSyncDistinctions` immediately, and prints the
 * closed list with its reason.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ChapterOffers } from '../../../components/offers/ChapterOffers';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import type { OffersResponse, VisibleOffer } from '../../../types';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import { unreachableClasses } from './classGuard';

const mutate = vi.fn();

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));

vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate }),
}));

const silverTongue: VisibleOffer = {
  offer_id: 101,
  distinction_id: 1,
  name: 'Silver Tongue',
  player_line: 'You always know the right thing to say.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: 'Mark',
  cost_per_rank: -25,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
};

const magicalScar: VisibleOffer = {
  offer_id: 102,
  distinction_id: 2,
  name: 'Magical Scar',
  player_line: 'A scar that answers magic. Deeper answers more.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: 5,
  max_rank: 3,
  is_locked: false,
  lock_reason: '',
};

const highborn: VisibleOffer = {
  offer_id: 103,
  distinction_id: 3,
  name: 'Highborn',
  player_line: 'Blood runs true.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: 'Public',
  cost_per_rank: 20,
  max_rank: 1,
  is_locked: true,
  lock_reason: 'The Cradle raised this character; the route closed it.',
};

/** A CHOICE entry from a different chapter's offer, to prove a toggle never drops it. */
const otherChapterEntry: DraftDistinctionEntry = {
  distinction_id: 50,
  distinction_name: 'Leal Agent',
  distinction_slug: 'leal-agent',
  category_slug: 'social',
  rank: 2,
  cost: 10,
  notes: '',
  offer_ids: [999],
  sources: ['A house bought you out'],
  arrivals: ['choice'],
};

let offersResponse: OffersResponse;
let draftDistinctions: DraftDistinctionEntry[];

beforeEach(() => {
  mutate.mockClear();
  offersResponse = {
    offers: [silverTongue, magicalScar, highborn],
    closed: [
      {
        distinction_id: 9,
        name: 'Generational Talent',
        reason: 'The route closed it.',
        opener_labels: [],
      },
    ],
  };
  draftDistinctions = [otherChapterEntry];
});

describe('ChapterOffers', () => {
  it('renders offers with their price, opener label and refund/per-rank formats', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByText('Silver Tongue')).toBeInTheDocument();
    expect(screen.getByText('You always know the right thing to say.')).toBeInTheDocument();
    expect(screen.getByText('From Mark.')).toBeInTheDocument();
    expect(screen.getByText('Refunds 25')).toBeInTheDocument();
    expect(screen.getByText('Magical Scar')).toBeInTheDocument();
    expect(screen.getByText('5 per rank')).toBeInTheDocument();
  });

  it('toggling an offer syncs every CHOICE entry, including the new offer_id', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    await user.click(screen.getByRole('button', { name: /Silver Tongue/ }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 50, rank: 2, offer_id: 999 },
      { id: 1, rank: 1, offer_id: 101 },
    ]);
  });

  it('a locked row is aria-disabled, shows its reason, and cannot be toggled', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    const row = screen.getByRole('button', { name: /Highborn/ });
    expect(row).toHaveAttribute('aria-disabled', 'true');
    expect(row).toBeDisabled();
    expect(
      screen.getByText('The Cradle raised this character; the route closed it.')
    ).toBeInTheDocument();
    await user.click(row);
    expect(mutate).not.toHaveBeenCalled();
  });

  it("a ranked offer's control raises its rank and syncs the new entry", async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    await user.click(screen.getByRole('button', { name: 'Raise Magical Scar' }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 50, rank: 2, offer_id: 999 },
      { id: 2, rank: 1, offer_id: 102 },
    ]);
  });

  it('renders the closed hint with the name and its own reason', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(
      screen.getByText('Closed on this road: Generational Talent: The route closed it.')
    ).toBeInTheDocument();
  });

  it('lists every closed item with its own reason, joined, when more than one is closed', () => {
    offersResponse = {
      ...offersResponse,
      closed: [
        {
          distinction_id: 9,
          name: 'Generational Talent',
          reason: 'The route closed it.',
          opener_labels: [],
        },
        {
          distinction_id: 8,
          name: 'Highborn',
          reason: 'The Cradle raised this character.',
          opener_labels: ['Public'],
        },
      ],
    };
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(
      screen.getByText(
        'Closed on this road: Generational Talent: The route closed it.; Highborn: The Cradle raised this character.'
      )
    ).toBeInTheDocument();
  });

  it('the closedLead prop overrides the default lead-in phrase', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" closedLead="No longer offered" />
    );
    expect(
      screen.getByText('No longer offered: Generational Talent: The route closed it.')
    ).toBeInTheDocument();
  });

  it("a selected ranked offer's price line adds a second 'N spent' total", () => {
    draftDistinctions = [
      otherChapterEntry,
      {
        distinction_id: 2,
        distinction_name: 'Magical Scar',
        distinction_slug: 'magical-scar',
        category_slug: 'magic',
        rank: 2,
        cost: 10,
        notes: '',
        offer_ids: [102],
        sources: ['The Glimpse'],
        arrivals: ['choice'],
      },
    ];
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByText('5 per rank')).toBeInTheDocument();
    expect(screen.getByText('10 spent')).toBeInTheDocument();
  });

  it('no spent line prints for a ranked offer at rank 0', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.queryByText(/spent$/)).not.toBeInTheDocument();
  });

  it('a selected ranked offer with a per-rank refund gets the refund class on its spent line', () => {
    const refundRanked: VisibleOffer = {
      offer_id: 104,
      distinction_id: 4,
      name: 'Fading Mark',
      player_line: 'It softens with every year you carry it.',
      chapter: 'glimpse',
      arrives_as: 'choice',
      opener_label: 'Mark',
      cost_per_rank: -5,
      max_rank: 3,
      is_locked: false,
      lock_reason: '',
    };
    offersResponse = { ...offersResponse, offers: [...offersResponse.offers, refundRanked] };
    draftDistinctions = [
      otherChapterEntry,
      {
        distinction_id: 4,
        distinction_name: 'Fading Mark',
        distinction_slug: 'fading-mark',
        category_slug: 'magic',
        rank: 2,
        cost: -10,
        notes: '',
        offer_ids: [104],
        sources: ['The Glimpse'],
        arrivals: ['choice'],
      },
    ];
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    const spentLine = screen.getByText('-10 spent');
    expect(spentLine).toHaveClass('refund');
  });

  it('showOpener={false} omits the "From X." attribution line', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" showOpener={false} />
    );
    expect(screen.getByText('Silver Tongue')).toBeInTheDocument();
    expect(screen.queryByText('From Mark.')).not.toBeInTheDocument();
  });

  it('showOpener defaults to true (the attribution line prints without the prop)', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByText('From Mark.')).toBeInTheDocument();
  });

  it('headingTag prints a .tag.soft chip right after the heading', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        heading="What it left in you"
        headingTag="optional"
      />
    );
    const chip = screen.getByText('optional');
    expect(chip).toHaveClass('tag', 'soft');
    expect(chip.closest('.tags')).toBeInTheDocument();
  });

  it('headingTag renders nothing when heading itself is omitted', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" headingTag="optional" />
    );
    expect(screen.queryByText('optional')).not.toBeInTheDocument();
  });

  it('closedFilter scopes the closed hint to matching items only', () => {
    offersResponse = {
      ...offersResponse,
      closed: [
        {
          distinction_id: 9,
          name: 'Generational Talent',
          reason: 'The route closed it.',
          opener_labels: ['Mark'],
        },
        {
          distinction_id: 8,
          name: 'Highborn',
          reason: 'The Cradle raised this character.',
          opener_labels: ['Public'],
        },
      ],
    };
    renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        closedFilter={(c) => c.opener_labels.includes('Public')}
      />
    );
    expect(
      screen.getByText('Closed on this road: Highborn: The Cradle raised this character.')
    ).toBeInTheDocument();
    expect(screen.queryByText(/Generational Talent/)).not.toBeInTheDocument();
  });

  it('closedFilter defaults to showing every closed item', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(
      screen.getByText('Closed on this road: Generational Talent: The route closed it.')
    ).toBeInTheDocument();
  });

  it('showClosed={false} hides the closed hint even when the chapter has closed items', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" showClosed={false} />
    );
    expect(screen.getByText('Silver Tongue')).toBeInTheDocument();
    expect(screen.queryByText(/Closed on this road/)).not.toBeInTheDocument();
  });

  it('showClosed defaults to true (the closed hint prints without the prop)', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByText(/Closed on this road/)).toBeInTheDocument();
  });

  it('a bundled row renders locked, ahead of the offered rows, with its refund', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        bundled={[
          {
            name: 'Impoverished',
            player_line: 'Nothing but the clothes.',
            cost_per_rank: -25,
            max_rank: 1,
          },
        ]}
      />
    );
    const impoverished = screen.getByText('Impoverished');
    const stance = impoverished.closest('.stance');
    expect(stance).not.toBeNull();
    expect(stance).toHaveAttribute('aria-pressed', 'true');
    expect(stance).toHaveAttribute('aria-disabled', 'true');
    expect(stance?.querySelector('.locked')).toHaveTextContent('bundled');
    expect(stance?.querySelector('.refund')).toHaveTextContent('Refunds 25');
    expect(screen.getByText('Nothing but the clothes.')).toBeInTheDocument();
    // The bundled row prints before the offered ones.
    const stances = Array.from(document.querySelectorAll('.stances > li'));
    expect(stances[0].textContent).toContain('Impoverished');
    expect(stances[1].textContent).toContain('Silver Tongue');
  });

  it('a bundled row with no player_line renders no description span', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        bundled={[{ name: 'Impoverished', cost_per_rank: -25, max_rank: 1 }]}
      />
    );
    const stance = screen.getByText('Impoverished').closest('.stance');
    expect(stance?.querySelector('.g')).toBeNull();
  });

  it('bundled rows alone (no offers, no closed) still render the block', () => {
    offersResponse = { offers: [], closed: [] };
    renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        bundled={[{ name: 'Impoverished', cost_per_rank: -25, max_rank: 1 }]}
      />
    );
    expect(screen.getByText('Impoverished')).toBeInTheDocument();
  });

  it('emits no class hook that cg.css has no rule reaching it (#3667 shape)', () => {
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <ChapterOffers
          draft={createMockDraft()}
          chapter="glimpse"
          heading="What it left in you"
          headingTag="optional"
          hint="staff copy"
        />
      </div>
    );
    const styledElsewhere = new Set(['chosen', 'closed']);
    expect(unreachableClasses(container, styledElsewhere)).toEqual([]);
  });
});
