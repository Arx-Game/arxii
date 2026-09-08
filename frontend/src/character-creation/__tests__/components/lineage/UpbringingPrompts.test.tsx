/**
 * UpbringingPrompts Component Tests (#3675 Task 14).
 *
 * A priced pick-list answer prints an `offers X` / `bundles Y` line off its
 * own `AnswerOffer[]` (the retired singular `grants_distinction` is gone).
 * The CHOSEN answer alone, when it carries a CHOICE offer, mounts a
 * `ChapterOffers` block right after the answers list; its bundled offers (if
 * any) render inside that same block as locked stances. The route's whole
 * closed list prints once, as a `ClosedByRoute` note after the last
 * `scope: 'path'` question - never per-answer.
 */

import { screen } from '@testing-library/react';
import { vi } from 'vitest';
import { UpbringingPrompts } from '../../../components/lineage/UpbringingPrompts';
import type { OffersResponse, OriginTemplate, VisibleOffer } from '../../../types';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import { unreachableClasses } from '../offers/classGuard';

const updateDraftMutate = vi.fn();

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useUpdateDraft: () => ({ mutate: updateDraftMutate }),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));

vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: [] }),
  useSyncDistinctions: () => ({ mutate: vi.fn() }),
}));

/** One question, "How you got off the crew" (the demo's Screen 5): two priced
 * answers, one chosen. The chosen answer bundles Impoverished for free and
 * offers Somehow Always Broke as a priced pick; the unchosen answer offers
 * Leal Agent - it must never get its own offered block. */
const template: OriginTemplate = {
  id: 900,
  name: 'Work Crews',
  frame_narrative: '',
  is_active: true,
  sort_order: 1,
  cg_point_cost: 0,
  trust_required: 0,
  allows_claim_family: false,
  allows_name_family: false,
  allows_no_family: true,
  claimable_kind_ids: [],
  family_templates: [],
  slots: [
    {
      id: 500,
      name: 'road_out',
      prompt: 'How you got off the crew',
      example: '',
      sort_order: 1,
      is_required: true,
      applies_to: 'claimed',
      allows_text: false,
      kind: 'pick',
      connection_kind: '',
      life_stage: '',
      anchor_source: '',
      same_anchor_as: null,
      follow_up_to: null,
      shown_for_choice_ids: [],
      groups: [],
      choices: [
        {
          id: 601,
          name: 'A house bought you out',
          description: 'Someone saw a use for you.',
          cg_point_cost: 5,
          cost_per_influence: 0,
          trust_required: 0,
          sort_order: 1,
          offers: [
            {
              offer_id: 11,
              distinction_id: 21,
              name: 'Leal Agent',
              player_line: 'You owe a debt.',
              arrives_as: 'choice',
              cost_per_rank: 10,
              max_rank: 1,
            },
          ],
        },
        {
          id: 602,
          name: 'Ran, with nothing',
          description: 'The road out was a wall.',
          cg_point_cost: -10,
          cost_per_influence: 0,
          trust_required: 0,
          sort_order: 2,
          offers: [
            {
              offer_id: 12,
              distinction_id: 22,
              name: 'Impoverished',
              player_line: 'Nothing but the clothes.',
              arrives_as: 'bundled',
              cost_per_rank: -25,
              max_rank: 1,
            },
            {
              offer_id: 13,
              distinction_id: 23,
              name: 'Somehow Always Broke',
              player_line: 'You learned to spend before someone took it.',
              arrives_as: 'choice',
              cost_per_rank: -50,
              max_rank: 1,
            },
            {
              offer_id: 14,
              distinction_id: 24,
              name: 'Wary of Debts',
              player_line: 'You do not trust a favor that arrives free.',
              arrives_as: 'choice',
              cost_per_rank: 5,
              max_rank: 1,
            },
          ],
        },
      ],
    },
  ],
};

const somehowAlwaysBroke: VisibleOffer = {
  offer_id: 13,
  distinction_id: 23,
  name: 'Somehow Always Broke',
  player_line: 'You learned to spend before someone took it.',
  chapter: 'lineage',
  arrives_as: 'choice',
  opener_label: 'Ran, with nothing',
  cost_per_rank: -50,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
  opener_key: '',
  first_look: false,
  held: false,
  effect_line: '',
};

/** Its `offer_id` (14) is in the chosen choice's own `offers`, but its
 * `opener_label` names the OTHER, unchosen answer - proof the mount matches
 * by id, never by label/name (#3676). */
const waryOfDebts: VisibleOffer = {
  offer_id: 14,
  distinction_id: 24,
  name: 'Wary of Debts',
  player_line: 'You do not trust a favor that arrives free.',
  chapter: 'lineage',
  arrives_as: 'choice',
  opener_label: 'A house bought you out',
  cost_per_rank: 5,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
  opener_key: '',
  first_look: false,
  held: false,
  effect_line: '',
};

/** Its `opener_label` matches the chosen choice's own name, but its
 * `offer_id` (99) is not among the chosen choice's `offers` - it must not
 * render under the chosen answer's block (#3676: id match, never label). */
const decoyMatchingLabel: VisibleOffer = {
  offer_id: 99,
  distinction_id: 99,
  name: 'Should Not Render',
  player_line: 'Matches the label but not the id.',
  chapter: 'lineage',
  arrives_as: 'choice',
  opener_label: 'Ran, with nothing',
  cost_per_rank: 5,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
  opener_key: '',
  first_look: false,
  held: false,
  effect_line: '',
};

let offersResponse: OffersResponse;

beforeEach(() => {
  updateDraftMutate.mockClear();
  offersResponse = {
    offers: [somehowAlwaysBroke, waryOfDebts, decoyMatchingLabel],
    closed: [
      {
        distinction_id: 90,
        name: 'Highborn',
        reason: 'The yards do not make those.',
        opener_labels: [],
        opener_ids: [],
      },
      {
        distinction_id: 91,
        name: 'Generational Talent',
        reason: '',
        opener_labels: [],
        opener_ids: [],
      },
      { distinction_id: 92, name: 'Spoiled', reason: '', opener_labels: [], opener_ids: [] },
    ],
  };
});

function draftWithChoice() {
  return createMockDraft({
    draft_data: { origin_choices: { '500': 602 } },
  });
}

describe('UpbringingPrompts', () => {
  it('prints an offers/bundles line on each priced answer off its own AnswerOffer[]', () => {
    renderWithCharacterCreationProviders(
      <UpbringingPrompts
        draft={draftWithChoice()}
        template={template}
        path="claimed"
        influence={0}
        copy={undefined}
        scope="path"
      />
    );
    expect(screen.getByText(/offers Leal Agent/)).toBeInTheDocument();
    expect(screen.getByText(/bundles Impoverished/)).toBeInTheDocument();
  });

  it('the offered block renders only under the chosen answer', () => {
    renderWithCharacterCreationProviders(
      <UpbringingPrompts
        draft={draftWithChoice()}
        template={template}
        path="claimed"
        influence={0}
        copy={undefined}
        scope="path"
      />
    );
    // The chosen answer ("Ran, with nothing") gets its own offered block.
    expect(screen.getByText('What it left you with')).toBeInTheDocument();
    expect(screen.getByText('offered by your answer')).toBeInTheDocument();
    expect(screen.getByText('Somehow Always Broke')).toBeInTheDocument();
    // The unchosen answer ("A house bought you out") offers Leal Agent on its
    // own answer line only - never its own offered block or heading.
    expect(screen.queryAllByText('What it left you with')).toHaveLength(1);
  });

  it('matches offers by offer_id, never by opener_label/name (#3676)', () => {
    renderWithCharacterCreationProviders(
      <UpbringingPrompts
        draft={draftWithChoice()}
        template={template}
        path="claimed"
        influence={0}
        copy={undefined}
        scope="path"
      />
    );
    // Wary of Debts' offer_id (14) is among the chosen choice's own offers,
    // even though its opener_label names the OTHER, unchosen answer - it
    // still renders.
    expect(screen.getByText('Wary of Debts')).toBeInTheDocument();
    // The decoy's opener_label matches the chosen choice's own name, but its
    // offer_id (99) is not among the chosen choice's offers - it never
    // renders under the chosen answer's block.
    expect(screen.queryByText('Should Not Render')).not.toBeInTheDocument();
  });

  it('a bundled offer prints "bundles X" on the answer line and a locked "bundled" stance in the block', () => {
    const { container } = renderWithCharacterCreationProviders(
      <UpbringingPrompts
        draft={draftWithChoice()}
        template={template}
        path="claimed"
        influence={0}
        copy={undefined}
        scope="path"
      />
    );
    expect(screen.getByText(/bundles Impoverished/)).toBeInTheDocument();
    const impoverished = screen.getByText('Impoverished');
    const stance = impoverished.closest('.stance');
    expect(stance).not.toBeNull();
    expect(stance).toHaveAttribute('aria-pressed', 'true');
    expect(stance).toHaveAttribute('aria-disabled', 'true');
    expect(stance?.querySelector('.locked')).toHaveTextContent('bundled');
    expect(stance?.querySelector('.award')).toHaveTextContent('Awards 25');
    // Impoverished stays under the chosen answer's own `.conditional` block.
    expect(container.querySelector('.conditional')?.contains(impoverished)).toBe(true);
  });

  it('the closed note renders once at the end with the reason and not inside any answer block', () => {
    const { container } = renderWithCharacterCreationProviders(
      <UpbringingPrompts
        draft={draftWithChoice()}
        template={template}
        path="claimed"
        influence={0}
        copy={undefined}
        scope="path"
      />
    );
    const note = screen.getByText(
      'Closed by this route: Highborn, Generational Talent, Spoiled. The yards do not make those.'
    );
    expect(note).toBeInTheDocument();
    const conditional = container.querySelector('.conditional');
    expect(conditional?.contains(note)).toBe(false);
  });

  it('emits no class hook that cg.css has no rule reaching it (#3667 shape)', () => {
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <UpbringingPrompts
          draft={draftWithChoice()}
          template={template}
          path="claimed"
          influence={0}
          copy={undefined}
          scope="path"
        />
      </div>
    );
    // Lineage's answer list still carries the pre-Folio shadcn/Tailwind markup
    // (docs/architecture note, Plan C #3630 pending); only the NEW folio-grammar
    // classes this task adds (field/tags/tag/soft/stances/stance/dot/sq/g/price/
    // locked/refund/hint/conditional) are cg.css's business here. Every entry
    // below is a shadcn/Tailwind utility class with NO cg.css rule at all
    // (verified against this render's actual emitted class set, #3675 fix
    // round 1 - not swept in defensively): `space-y-*`/`grid`/`gap-2`/
    // `sm:grid-cols-2` (the answer-list wrapper), the pick-button classes
    // (`rounded-md`/`border`/`p-2`/`text-left`/`text-sm`/`transition-colors`/
    // `border-primary`/`bg-primary/10`/`hover:bg-muted/50`), the `Label`
    // component (`text-sm`/`font-medium`/`leading-none`/`peer-disabled:*`),
    // the required-question asterisk (`ml-1`/`text-destructive`), the
    // description/offer-summary lines (`block`/`text-xs`/
    // `text-muted-foreground`), and the shadcn `Badge` variant on the "N pts"
    // chip (`inline-flex`/`items-center`/`justify-between`/`rounded-full`/
    // `px-2.5`/`py-0.5`/`font-semibold`/`transition-colors`/
    // `focus:outline-none`/`focus:ring-2`/`focus:ring-ring`/
    // `focus:ring-offset-2`/`text-foreground`/`flex`).
    const styledElsewhere = new Set([
      'space-y-6',
      'space-y-2',
      'grid',
      'gap-2',
      'sm:grid-cols-2',
      'rounded-md',
      'border',
      'p-2',
      'text-left',
      'text-sm',
      'transition-colors',
      'border-primary',
      'bg-primary/10',
      'hover:bg-muted/50',
      'flex',
      'items-center',
      'justify-between',
      'font-medium',
      'leading-none',
      'peer-disabled:cursor-not-allowed',
      'peer-disabled:opacity-70',
      'ml-1',
      'text-destructive',
      'block',
      'text-xs',
      'text-muted-foreground',
      // Badge (shadcn) variant classes on the "N pts" chip.
      'inline-flex',
      'rounded-full',
      'px-2.5',
      'py-0.5',
      'font-semibold',
      'focus:outline-none',
      'focus:ring-2',
      'focus:ring-ring',
      'focus:ring-offset-2',
      'text-foreground',
    ]);
    expect(unreachableClasses(container, styledElsewhere)).toEqual([]);
  });
});
