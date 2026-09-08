/**
 * ChapterOffers Component Tests (#3675).
 *
 * The reusable offers block every CG chapter mounts in place of the retired
 * Distinctions stage: renders a chapter's visible offers as folio stances,
 * writes selection through `useSyncDistinctions` immediately, and prints the
 * closed list with its reason.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ChapterOffers } from '../../../components/offers/ChapterOffers';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import type { OffersResponse, VisibleOffer } from '../../../types';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import { unreachableClasses } from './classGuard';

const mutate = vi.fn();
// Mutable so a test can flip isPending/isError before rendering (F2, #3675
// final fix): a real useMutation() exposes both while a PUT is in flight or
// after it fails.
let syncState = { isPending: false, isError: false };

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));

vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate, ...syncState }),
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
  opener_key: '',
  first_look: false,
  held: false,
  effect_line: '',
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
  opener_key: '',
  first_look: false,
  held: false,
  effect_line: '',
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
  opener_key: '',
  first_look: false,
  held: false,
  effect_line: '',
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
  syncState = { isPending: false, isError: false };
  offersResponse = {
    offers: [silverTongue, magicalScar, highborn],
    closed: [
      {
        distinction_id: 9,
        name: 'Generational Talent',
        reason: 'The route closed it.',
        opener_labels: [],
        opener_ids: [],
      },
    ],
  };
  draftDistinctions = [otherChapterEntry];
});

describe('ChapterOffers', () => {
  it('renders offers with their price, opener label and award/per-rank formats', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByText('Silver Tongue')).toBeInTheDocument();
    expect(screen.getByText('You always know the right thing to say.')).toBeInTheDocument();
    expect(screen.getByText('From Mark.')).toBeInTheDocument();
    expect(screen.getByText('Awards 25')).toBeInTheDocument();
    expect(screen.getByText('Magical Scar')).toBeInTheDocument();
    expect(screen.getByText('5 per rank')).toBeInTheDocument();
  });

  it('the price-grammar words route through their own props (#3675 final fix F5)', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        wordPerRank="par la marque"
        wordAwards="Rembourse"
      />
    );
    expect(screen.getByText('Rembourse 25')).toBeInTheDocument();
    expect(screen.getByText('5 par la marque')).toBeInTheDocument();
    expect(screen.queryByText('Awards 25')).not.toBeInTheDocument();
    expect(screen.queryByText('5 per rank')).not.toBeInTheDocument();
  });

  it('a bundled row prints its own wordBundled override', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        wordBundled="groupé"
        bundled={[{ offer_id: 700, name: 'A Bundled Grant', cost_per_rank: 0, max_rank: 1 }]}
      />
    );
    expect(screen.getByText('groupé')).toBeInTheDocument();
    expect(screen.queryByText('bundled')).not.toBeInTheDocument();
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

  it('toggling an offer sends a sync body without a bundled-only entry (#3675 final fix F1)', async () => {
    const bundledOnly: DraftDistinctionEntry = {
      distinction_id: 60,
      distinction_name: 'Household Retainer',
      distinction_slug: 'household-retainer',
      category_slug: 'social',
      rank: 1,
      cost: 0,
      notes: '',
      offer_ids: [888],
      sources: ['A group question'],
      arrivals: ['bundled'],
    };
    draftDistinctions = [otherChapterEntry, bundledOnly];
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    await user.click(screen.getByRole('button', { name: /Silver Tongue/ }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 50, rank: 2, offer_id: 999 },
      { id: 1, rank: 1, offer_id: 101 },
    ]);
    const [syncBody] = mutate.mock.calls[0];
    expect(syncBody.some((row: { id: number }) => row.id === 60)).toBe(false);
  });

  it('disables the toggle and rank controls while the sync mutation is pending (#3675 final fix F2)', () => {
    syncState = { isPending: true, isError: false };
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByRole('button', { name: /Silver Tongue/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Raise Magical Scar' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Lower Magical Scar' })).toBeDisabled();
  });

  it('prints the sync error hint when the mutation fails', () => {
    syncState = { isPending: false, isError: true };
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByText('That pick did not save. Try again.')).toBeInTheDocument();
  });

  it('the syncErrorHint prop overrides the default error copy', () => {
    syncState = { isPending: false, isError: true };
    renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        syncErrorHint="Staff-authored fallback"
      />
    );
    expect(screen.getByText('Staff-authored fallback')).toBeInTheDocument();
    expect(screen.queryByText('That pick did not save. Try again.')).not.toBeInTheDocument();
  });

  it('prints no error hint while the mutation has not failed', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.queryByText('That pick did not save. Try again.')).not.toBeInTheDocument();
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

  it("a ranked offer's row is a group labeled by its name, never aria-pressed (#3675 final fix F6)", () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    const group = screen.getByRole('group', { name: 'Magical Scar' });
    expect(group).toHaveClass('stance');
    expect(group).not.toHaveAttribute('aria-pressed');
    expect(group).not.toHaveAttribute('aria-disabled');
    // Only the row's own interactive controls (the rank stepper) carry a
    // button role; aria-pressed appears only on those, never on the group.
    for (const button of within(group).getAllByRole('button')) {
      expect(button).not.toHaveAttribute('aria-pressed');
    }
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
          opener_ids: [],
        },
        {
          distinction_id: 8,
          name: 'Highborn',
          reason: 'The Cradle raised this character.',
          opener_labels: ['Public'],
          opener_ids: [103],
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

  it('a selected ranked offer with a per-rank award gets the award class on its spent line', () => {
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
      opener_key: '',
      first_look: false,
      held: false,
      effect_line: '',
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
    expect(spentLine).toHaveClass('award');
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
          opener_ids: [101],
        },
        {
          distinction_id: 8,
          name: 'Highborn',
          reason: 'The Cradle raised this character.',
          opener_labels: ['Public'],
          opener_ids: [103],
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
            offer_id: 201,
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
    expect(stance?.querySelector('.award')).toHaveTextContent('Awards 25');
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
        bundled={[{ offer_id: 202, name: 'Impoverished', cost_per_rank: -25, max_rank: 1 }]}
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
        bundled={[{ offer_id: 202, name: 'Impoverished', cost_per_rank: -25, max_rank: 1 }]}
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
    expect(unreachableClasses(container)).toEqual([]);
  });
});

describe('ChapterOffers fold, held state and effect line (#3709)', () => {
  const many = (count: number, pinned: number[] = []): VisibleOffer[] =>
    Array.from({ length: count }, (_, i) => ({
      ...silverTongue,
      offer_id: 200 + i,
      distinction_id: 20 + i,
      name: `Trait ${i}`,
      cost_per_rank: 5,
      first_look: pinned.includes(200 + i),
    }));

  it('a block of five or more shows the pinned lines at rest and folds the rest', () => {
    offersResponse = { offers: many(6, [203, 205]), closed: [] };
    const { container } = renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    const atRest = container.querySelector<HTMLElement>('ul.stances')!;
    expect(within(atRest).getByText('Trait 3')).toBeInTheDocument();
    expect(within(atRest).getByText('Trait 5')).toBeInTheDocument();
    expect(within(atRest).queryByText('Trait 0')).not.toBeInTheDocument();
    const fold = container.querySelector<HTMLElement>('details.more')!;
    expect(fold).not.toBeNull();
    expect(within(fold).getByText('See 4 more')).toBeInTheDocument();
    expect(within(fold).getByText('Trait 0')).toBeInTheDocument();
  });

  it('with nothing pinned the first three stand in for the first look', () => {
    offersResponse = { offers: many(7), closed: [] };
    const { container } = renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" wordSeeMore="{count} further" />
    );
    const atRest = container.querySelector<HTMLElement>('ul.stances')!;
    expect(within(atRest).getByText('Trait 2')).toBeInTheDocument();
    expect(within(atRest).queryByText('Trait 3')).not.toBeInTheDocument();
    expect(screen.getByText('4 further')).toBeInTheDocument();
  });

  it('a block under five never folds', () => {
    offersResponse = { offers: many(4), closed: [] };
    const { container } = renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(container.querySelector('details.more')).toBeNull();
    expect(screen.getByText('Trait 3')).toBeInTheDocument();
  });

  it('firstLook={false} shows everything at rest', () => {
    offersResponse = { offers: many(6, [200]), closed: [] };
    const { container } = renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" firstLook={false} />
    );
    expect(container.querySelector('details.more')).toBeNull();
    expect(screen.getByText('Trait 5')).toBeInTheDocument();
  });

  it('a held line renders pressed and disabled with the held word and no toggle', async () => {
    const user = userEvent.setup();
    offersResponse = {
      offers: [{ ...magicalScar, held: true }, silverTongue],
      closed: [],
    };
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" wordHeld="yours already" />
    );
    const stance = screen.getByText('Magical Scar').closest('.stance')!;
    expect(stance).toHaveAttribute('aria-pressed', 'true');
    expect(stance).toHaveAttribute('aria-disabled', 'true');
    expect(stance.querySelector('.locked')).toHaveTextContent('yours already');
    expect(stance.querySelector('.rank')).toBeNull();
    await user.click(stance as HTMLElement);
    expect(mutate).not.toHaveBeenCalled();
  });

  it('prints the effect line in its own fx span under the player line', () => {
    offersResponse = {
      offers: [{ ...silverTongue, effect_line: '+Deception; -Willpower' }],
      closed: [],
    };
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
      </div>
    );
    const fx = screen.getByText('+Deception; -Willpower');
    expect(fx).toHaveClass('fx');
    expect(unreachableClasses(container)).toEqual([]);
  });

  it('a plain cost carries the cost class and an award the award class', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByText('Awards 25')).toHaveClass('award');
    expect(screen.getByText('20')).toHaveClass('cost');
  });
});
