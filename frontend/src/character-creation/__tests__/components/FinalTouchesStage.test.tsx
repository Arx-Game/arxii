/**
 * FinalTouchesStage Component Tests: the Actor's Sheet (#3621).
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { FinalTouchesStage } from '../../components/FinalTouchesStage';
import { createMockDraft, mockCGExplanations } from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';
import type { EnemyOffer, OffersResponse, VisibleOffer } from '../../types';
import { unreachableClasses } from './offers/classGuard';

vi.mock('../../goals', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../goals')>()),
  useGoalDomains: () => ({
    data: [
      {
        id: 1,
        name: 'Ambition',
        description: 'What you reach for.',
        display_order: 1,
        is_optional: false,
      },
      { id: 2, name: 'Bonds', description: 'Who you keep.', display_order: 2, is_optional: false },
    ],
    isLoading: false,
    error: null,
  }),
}));
const mutateAsync = vi.fn().mockResolvedValue({});

const EMPTY_FACE_FOR_TEST = {
  face_name: '',
  concept: '',
  quote: '',
  never_do: '',
  protect: '',
  fear: '',
  background: '',
};
let offersResponse: OffersResponse;
// The card-unlocked chapter's own response (#4846); empty unless a test fills it.
let finalTouchesOffers: OffersResponse = { offers: [], closed: [] };
vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync }),
  useDraftOffers: (_draftId: number, chapter: string) => ({
    data: chapter === 'final_touches' ? finalTouchesOffers : offersResponse,
    isLoading: false,
  }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: [] }),
  useSyncDistinctions: () => ({ mutate: vi.fn() }),
}));

const hedonistic: VisibleOffer = {
  offer_id: 301,
  distinction_id: 31,
  name: 'Hedonistic',
  distinction_name: 'Hedonistic',
  player_line: 'If the vibes are good, you are good.',
  chapter: 'actors_sheet',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: 25,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
  opener_key: 'prompt:protect',
  first_look: false,
  held: false,
  effect_line: '',
  taken_per_feature: false,
  opens_feature: false,
  requires_feature_opened: false,
  cg_max_rank: 0,
};

const voracious: VisibleOffer = {
  offer_id: 302,
  distinction_id: 32,
  name: 'Voracious',
  distinction_name: 'Voracious',
  player_line: 'Need that borders on compulsion.',
  chapter: 'actors_sheet',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: 5,
  max_rank: 3,
  is_locked: false,
  lock_reason: '',
  opener_key: 'prompt:fear',
  first_look: false,
  held: false,
  effect_line: '',
  taken_per_feature: false,
  opens_feature: false,
  requires_feature_opened: false,
  cg_max_rank: 0,
};

const rouault: EnemyOffer = {
  kind: 'group',
  organization_id: 7,
  name: 'the Rouault',
  reach: 'house',
  power_tier: '',
  why: '',
  source: 'lineage',
  reason_id: null,
};
const republic: EnemyOffer = {
  kind: 'group',
  organization_id: 8,
  name: 'The Republic of Luxen',
  reach: 'realm',
  power_tier: '',
  why: 'it does not keep the Gifted',
  source: 'beginning',
  reason_id: null,
};

describe("FinalTouchesStage (Actor's Sheet)", () => {
  beforeEach(() => {
    offersResponse = { offers: [hedonistic, voracious], closed: [] };
  });
  afterEach(() => mutateAsync.mockClear());

  it('asks the three questions with their example lines', () => {
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByLabelText('What would you never do?')).toBeInTheDocument();
    expect(screen.getByLabelText('What would you protect at all costs?')).toBeInTheDocument();
    expect(screen.getByLabelText('What are you deathly afraid of?')).toBeInTheDocument();
    expect(screen.getByText('Ex. Betray a secret. Break a vow. Make a pun.')).toBeInTheDocument();
  });

  it('numbers goals within each horizon and keeps the purse at the head', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      draft_data: {
        goals: [
          { domain_id: 1, notes: 'Rule the docks', points: 10, horizon: 'short_term' },
          { domain_id: 2, notes: 'Keep Tessaline', points: 12, horizon: 'short_term' },
          { domain_id: 1, notes: 'Decide the doors', points: 8, horizon: 'long_term' },
        ],
      },
    });
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText(/Points remaining/)).toBeInTheDocument();
    expect(screen.getByDisplayValue('Keep Tessaline')).toHaveAttribute(
      'id',
      expect.stringMatching(/notes$/)
    );
    expect(screen.getAllByLabelText('Goal 1')).toHaveLength(2);
    expect(screen.getByLabelText('Goal 2')).toHaveDisplayValue('Keep Tessaline');
    await user.click(screen.getAllByRole('button', { name: 'Add a goal' })[1]);
    expect(screen.getAllByLabelText('Goal 2')).toHaveLength(2);
  });

  it('prices an offered group at each degree and writes the ledger line', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ enemy_offers: [rouault, republic] });
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const offers = screen.getByRole('list', { name: 'Enemies offered' });
    expect(within(offers).getByText('the Rouault')).toBeInTheDocument();
    expect(within(offers).getByText('The Republic of Luxen')).toBeInTheDocument();
    await user.click(within(offers).getAllByRole('button', { name: 'Name them' })[0]);
    const degrees = screen.getByRole('group', { name: 'How badly' });
    expect(
      within(degrees).getByRole('button', { name: /thwarted · Awards 16 CG points/ })
    ).toBeInTheDocument();
    expect(
      within(degrees).getByRole('button', { name: /destroy you · Awards 48 CG points/ })
    ).toBeInTheDocument();
    expect(
      within(degrees).getByRole('button', { name: /ruined · Awards 32 CG points · bundles Marked/ })
    ).toBeInTheDocument();
    await user.click(within(degrees).getByRole('button', { name: /thwarted/ }));
    expect(
      screen.getByText(/They want you thwarted: the Rouault · Awards 16 CG points/)
    ).toBeInTheDocument();
    const grids = screen.getAllByRole('table', { name: 'The two scales' });
    expect(grids).toHaveLength(2);
    expect(within(grids[0]).getByRole('cell', { name: '16' })).toHaveClass('on');
  });

  it('offers the First Journal only on an Arx start and folds a skipped one away', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({ draft_data: { first_name: 'Aurelie' } })}
        onRegisterBeforeLeave={vi.fn()}
      />
    );
    const journal = screen.getByRole('heading', { name: /Aurelie's First Journal/ });
    expect(journal).toBeInTheDocument();
    expect(screen.queryByLabelText('What should the world know of you first?')).toBeNull();
    await user.click(within(journal.closest('section')!).getByRole('button', { name: 'Write it' }));
    expect(screen.getByLabelText('What should the world know of you first?')).toBeInTheDocument();
  });

  it('hides the First Journal when the start is not Arx', () => {
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({ introductions_offered: { first_journal: false } })}
        onRegisterBeforeLeave={vi.fn()}
      />
    );
    expect(screen.queryByRole('heading', { name: /First Journal/ })).toBeNull();
    expect(
      screen.getByRole('heading', { name: /An Application to Shroudwatch Academy/ })
    ).toBeInTheDocument();
  });

  it("offers each question's distinctions under that question, headed by its plural noun (#3709)", () => {
    const { container } = renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText('Devotions')).toBeInTheDocument();
    expect(screen.getByText('Fears')).toBeInTheDocument();
    expect(screen.queryByText('Rules')).not.toBeInTheDocument();
    expect(screen.queryByText('Is it a hunger')).not.toBeInTheDocument();
    expect(screen.getAllByText('Distinctions')).toHaveLength(2);
    const order = container.textContent ?? '';
    const protectIdx = order.indexOf('What would you protect at all costs?');
    const devotionsIdx = order.indexOf('Devotions');
    const hedonisticIdx = order.indexOf('Hedonistic');
    const fearIdx = order.indexOf('What are you deathly afraid of?');
    const fearsIdx = order.indexOf('Fears');
    const voraciousIdx = order.indexOf('Voracious');
    const goalsIdx = order.indexOf('Goals');
    expect(protectIdx).toBeGreaterThan(-1);
    expect(devotionsIdx).toBeGreaterThan(protectIdx);
    expect(hedonisticIdx).toBeGreaterThan(devotionsIdx);
    expect(fearIdx).toBeGreaterThan(hedonisticIdx);
    expect(fearsIdx).toBeGreaterThan(fearIdx);
    expect(voraciousIdx).toBeGreaterThan(fearsIdx);
    expect(goalsIdx).toBeGreaterThan(voraciousIdx);
  });

  it('asks why from the reason list, filtered to the kind, and the picked reason opens its offers (#3709)', async () => {
    const user = userEvent.setup();
    const lightSleeper: VisibleOffer = {
      ...hedonistic,
      offer_id: 401,
      distinction_id: 41,
      name: 'Light Sleeper',
      distinction_name: 'Light Sleeper',
      player_line: 'No whole night since.',
      chapter: 'enemy',
      opener_key: 'reason:1',
      cost_per_rank: -5,
      effect_line: '-Daily AP',
      taken_per_feature: false,
      opens_feature: false,
      requires_feature_opened: false,
      cg_max_rank: 0,
    };
    offersResponse = { offers: [hedonistic, voracious, lightSleeper], closed: [] };
    let leave: (() => Promise<boolean>) | null = null;
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({
          enemy_offers: [rouault],
          enemy_reasons: [
            {
              id: 1,
              name: 'You know what they did',
              player_line: 'And they know.',
              fits: 'either',
            },
            { id: 2, name: 'You were meant to marry', player_line: '', fits: 'person' },
          ],
        })}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />
    );
    await user.click(screen.getByRole('button', { name: 'Name them' }));
    const reasons = screen.getByRole('group', { name: /Why they want it/ });
    expect(
      within(reasons).getByRole('button', { name: 'You know what they did' })
    ).toBeInTheDocument();
    expect(
      within(reasons).queryByRole('button', { name: 'You were meant to marry' })
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Light Sleeper')).not.toBeInTheDocument();
    await user.click(within(reasons).getByRole('button', { name: 'You know what they did' }));
    expect(screen.getByText('What it left you with')).toBeInTheDocument();
    expect(screen.getByText('Light Sleeper')).toBeInTheDocument();
    expect(screen.getByText('-Daily AP')).toHaveClass('fx');
    expect(screen.getByText('Awards 5')).toHaveClass('award');
    expect(screen.getByLabelText('In your own words')).toBeInTheDocument();
    await leave!();
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        data: {
          draft_data: expect.objectContaining({
            enemy: expect.objectContaining({ organization_id: 7, reason_id: 1 }),
          }),
        },
      })
    );
  });

  it('prints the closed hint with the closedLead fallback', () => {
    offersResponse = {
      offers: [hedonistic],
      closed: [
        {
          distinction_id: 40,
          name: 'Indolent',
          reason: 'Your route closed it.',
          opener_labels: [],
          opener_ids: [],
        },
      ],
    };
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(
      screen.getByText('Closed by your route: Indolent: Your route closed it.')
    ).toBeInTheDocument();
  });

  it('emits no class hook that cg.css has no rule for (#3667 shape)', async () => {
    const user = userEvent.setup();
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <FinalTouchesStage
          draft={createMockDraft({
            enemy_offers: [rouault],
            draft_data: {
              goals: [{ domain_id: 1, notes: 'A', points: 1, horizon: 'short_term' }],
            },
          })}
          onRegisterBeforeLeave={vi.fn()}
        />
      </div>
    );
    await user.click(screen.getByRole('button', { name: 'Name them' }));
    await user.click(screen.getByRole('button', { name: /ruined/ }));
    for (const door of screen.getAllByRole('button', { name: 'Write it' })) {
      await user.click(door);
    }
    // The person kind and the free-written path emit their own hooks.
    await user.click(screen.getByRole('button', { name: 'A person' }));
    await user.click(screen.getByRole('button', { name: 'Write your own' }));
    // Ranked offer's control raises its rank, and toggle the unranked one, so
    // ChapterOffers's rank-control and pressed-stance markup both render.
    await user.click(screen.getByRole('button', { name: 'Raise Voracious' }));
    await user.click(screen.getByRole('button', { name: /Hedonistic/ }));
    // App-wide utilities and pre-existing folio-chassis classes with no rule
    // reaching the bare element (only a descendant selector) - not created by
    // this task's offers markup, same escape hatch every other class-guard
    // test uses.
    const styledElsewhere = new Set(['leaf-body', 'chosen', 'entry', 'note-group']);
    expect(unreachableClasses(container, styledElsewhere)).toEqual([]);
  });

  it('names the face the world meets behind the Officially dead door (#4396)', async () => {
    const user = userEvent.setup();
    let leave: (() => Promise<boolean>) | null = null;
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft()}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />
    );
    expect(screen.getByRole('heading', { name: 'Officially dead' })).toBeInTheDocument();
    expect(screen.queryByLabelText('The face the world meets')).toBeNull();
    const doors = screen.getAllByRole('button', { name: 'Write it' });
    const door = within(
      screen.getByRole('heading', { name: 'Officially dead' }).closest('section')!
    ).getByRole('button', { name: 'Write it' });
    expect(doors).toContain(door);
    await user.click(door);
    await user.type(screen.getByLabelText('The face the world meets'), 'Cambria');
    await user.type(screen.getByLabelText('Concept'), 'A widow of means');
    await leave!();
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        data: {
          draft_data: expect.objectContaining({
            officially_dead: expect.objectContaining({
              face_name: 'Cambria',
              concept: 'A widow of means',
              background: '',
            }),
          }),
        },
      })
    );
  });

  it('skipping the door takes the face back and saves null (#4396)', async () => {
    const user = userEvent.setup();
    let leave: (() => Promise<boolean>) | null = null;
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({
          draft_data: { officially_dead: { ...EMPTY_FACE_FOR_TEST, face_name: 'Cambria' } },
        })}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />
    );
    expect(screen.getByLabelText('The face the world meets')).toHaveValue('Cambria');
    const section = screen.getByRole('heading', { name: 'Officially dead' }).closest('section')!;
    await user.click(within(section).getByRole('button', { name: 'Skip' }));
    expect(screen.queryByLabelText('The face the world meets')).toBeNull();
    await leave!();
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        data: { draft_data: expect.objectContaining({ officially_dead: null }) },
      })
    );
  });

  it('saves the answers, goals, enemy and introductions in one PATCH on leave', async () => {
    const user = userEvent.setup();
    let leave: (() => Promise<boolean>) | null = null;
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({ enemy_offers: [rouault] })}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />
    );
    await user.type(screen.getByLabelText('What would you never do?'), 'Make a pun');
    await user.click(screen.getByRole('button', { name: 'Name them' }));
    await user.click(screen.getByRole('button', { name: /ruined/ }));
    await leave!();
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        data: {
          draft_data: expect.objectContaining({
            never_do: 'Make a pun',
            enemy: expect.objectContaining({ kind: 'group', organization_id: 7, degree: 'ruined' }),
            introductions: expect.objectContaining({ whispers: '' }),
          }),
        },
      })
    );
  });
});

describe('FinalTouchesStage (the card-unlocked chapter, #4846)', () => {
  const theft = { id: 5, slug: 'theft', name: 'Theft', description: '' };
  const arson = { id: 6, slug: 'arson', name: 'Arson', description: '' };
  const escapeArtist: VisibleOffer = {
    ...hedonistic,
    offer_id: 401,
    distinction_id: 41,
    name: 'Escape Artist',
    distinction_name: 'Escape Artist',
    player_line: 'Locks open for you.',
    chapter: 'final_touches',
    opener_key: 'unlocked:31',
    opener_label: 'Jailbird',
  };
  const HEADING = 'What the cards leave to settle';
  const PROMPT = 'The crime, if you care to name it.';

  beforeEach(() => {
    offersResponse = { offers: [], closed: [] };
  });
  afterEach(() => {
    finalTouchesOffers = { offers: [], closed: [] };
    mutateAsync.mockClear();
  });

  it('is absent when no held card unlocks a line or asks a question', () => {
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.queryByText(HEADING)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(PROMPT)).not.toBeInTheDocument();
  });

  it('ignores a route-closed row no held card would have opened, and counts one it would', () => {
    const closedRow = {
      distinction_id: 51,
      name: 'Marked Hands',
      reason: 'Not on this road.',
      opener_labels: [] as string[],
      opener_ids: [] as number[],
    };
    finalTouchesOffers = { offers: [], closed: [closedRow] };
    const { unmount } = renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.queryByText(HEADING)).not.toBeInTheDocument();
    unmount();
    finalTouchesOffers = {
      offers: [],
      closed: [{ ...closedRow, opener_labels: ['Jailbird'], opener_ids: [401] }],
    };
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText(HEADING)).toBeInTheDocument();
    expect(screen.getByText(/Marked Hands/)).toBeInTheDocument();
  });

  it('shows the lines a held card unlocks, with no crime prompt when no card asks', () => {
    finalTouchesOffers = { offers: [escapeArtist], closed: [] };
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText(HEADING)).toBeInTheDocument();
    expect(screen.getByText('Escape Artist')).toBeInTheDocument();
    expect(screen.getByText('Locks open for you.')).toBeInTheDocument();
    expect(screen.queryByLabelText(PROMPT)).not.toBeInTheDocument();
  });

  it('asks the crime when a held card does, lists the kinds, caps the line and saves it', async () => {
    const user = userEvent.setup();
    let leave: (() => Promise<boolean>) | undefined;
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({ final_touches_prompts: ['crime'], crime_kinds: [theft, arson] })}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />
    );
    expect(screen.getByText(HEADING)).toBeInTheDocument();
    const kind = screen.getByLabelText(PROMPT);
    expect(within(kind).getByRole('option', { name: 'Unnamed' })).toBeInTheDocument();
    expect(within(kind).getByRole('option', { name: 'Theft' })).toBeInTheDocument();
    expect(within(kind).getByRole('option', { name: 'Arson' })).toBeInTheDocument();
    const line = screen.getByLabelText('In a sentence');
    expect(line).toHaveAttribute('maxlength', '500');
    expect(
      screen.getByText('Nothing follows from this unless a GM picks it up.')
    ).toBeInTheDocument();
    await user.selectOptions(kind, '5');
    await user.type(line, 'A purse that was not mine.');
    await leave!();
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          draft_data: expect.objectContaining({
            crime: { kind_id: 5, line: 'A purse that was not mine.' },
          }),
        }),
      })
    );
  });

  it('opens on the crime already saved and saves null once the kind is cleared', async () => {
    const user = userEvent.setup();
    let leave: (() => Promise<boolean>) | undefined;
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({
          final_touches_prompts: ['crime'],
          crime_kinds: [theft],
          draft_data: { crime: { kind_id: 5, line: 'A purse.' } },
        })}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />
    );
    const kind = screen.getByLabelText(PROMPT);
    expect(kind).toHaveValue('5');
    expect(screen.getByLabelText('In a sentence')).toHaveValue('A purse.');
    await user.selectOptions(kind, '');
    await leave!();
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ draft_data: expect.objectContaining({ crime: null }) }),
      })
    );
  });
});

describe('FinalTouchesStage (the grants the cards reconcile, #4852)', () => {
  const HEADING = 'What the cards leave to settle';
  const STORY_PROMPT = 'What people say happened.';
  const ORG_PROMPT = 'The body that marked your coming of age takes you in.';
  const drama = {
    distinction_id: 61,
    name: 'Explosive Drama',
    prompt: 'prestige_story' as const,
    detail: '',
  };
  const honors = {
    distinction_id: 62,
    name: 'With Honors',
    prompt: 'organization' as const,
    detail: '',
  };
  const mentor = {
    distinction_id: 63,
    name: 'Capable Mentor',
    prompt: 'path_aspect' as const,
    detail: 'Warfare',
  };
  const lodge = { id: 7, name: 'The Honor Lodge', is_covert: false };

  beforeEach(() => {
    offersResponse = { offers: [], closed: [] };
  });
  afterEach(() => mutateAsync.mockClear());

  it('renders none of the blocks when no held card raises an ask', () => {
    renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.queryByText(HEADING)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(STORY_PROMPT)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(ORG_PROMPT)).not.toBeInTheDocument();
    expect(screen.queryByText(/lessons settle on/)).not.toBeInTheDocument();
  });

  it('asks the story, the organization and shows the mentor line, then saves both answers', async () => {
    const user = userEvent.setup();
    let leave: (() => Promise<boolean>) | undefined;
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({
          final_touches_prompts: ['prestige_story', 'organization', 'path_aspect'],
          final_touches_cards: [drama, honors, mentor],
          organization_choices: [lodge],
        })}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />
    );
    expect(screen.getByText(HEADING)).toBeInTheDocument();
    expect(screen.getByText('Explosive Drama')).toBeInTheDocument();
    const story = screen.getByLabelText(STORY_PROMPT);
    expect(story).toHaveAttribute('maxlength', '500');
    expect(
      screen.getByText(
        'A sentence or two. This is the story attached to your name, not the truth of it.'
      )
    ).toBeInTheDocument();
    expect(screen.getByText('With Honors')).toBeInTheDocument();
    const pick = screen.getByLabelText(ORG_PROMPT);
    const options = within(pick).getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual(['None', 'The Honor Lodge']);
    expect(screen.getByText('Capable Mentor')).toBeInTheDocument();
    expect(
      screen.getByText("Your mentor's lessons settle on Warfare, the stronger Aspect of your Path.")
    ).toBeInTheDocument();
    expect(screen.getByText('Applied for you.')).toBeInTheDocument();

    await user.type(story, 'They say the duel emptied a chapel.');
    await user.selectOptions(pick, '7');
    await leave!();
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          draft_data: expect.objectContaining({
            prestige_stories: { '61': 'They say the duel emptied a chapel.' },
            organizations: { '62': 7 },
          }),
        }),
      })
    );
  });

  it('reads the generic line before a Path is picked', () => {
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({
          final_touches_prompts: ['path_aspect'],
          final_touches_cards: [{ ...mentor, detail: '' }],
        })}
        onRegisterBeforeLeave={vi.fn()}
      />
    );
    expect(
      screen.getByText(
        "Your mentor's lessons settle on your Path's stronger Aspect, the stronger Aspect of your Path."
      )
    ).toBeInTheDocument();
  });

  it('opens on the saved answers, drops a blanked story and saves null for None', async () => {
    const user = userEvent.setup();
    let leave: (() => Promise<boolean>) | undefined;
    renderWithCharacterCreationProviders(
      <FinalTouchesStage
        draft={createMockDraft({
          final_touches_prompts: ['prestige_story', 'organization'],
          final_touches_cards: [drama, honors],
          organization_choices: [lodge],
          draft_data: { prestige_stories: { '61': 'A chapel.' }, organizations: { '62': 7 } },
        })}
        onRegisterBeforeLeave={(check) => {
          leave = check;
        }}
      />
    );
    const story = screen.getByLabelText(STORY_PROMPT);
    expect(story).toHaveValue('A chapel.');
    const pick = screen.getByLabelText(ORG_PROMPT);
    expect(pick).toHaveValue('7');
    await user.clear(story);
    await user.selectOptions(pick, '');
    await leave!();
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          draft_data: expect.objectContaining({
            prestige_stories: {},
            organizations: { '62': null },
          }),
        }),
      })
    );
  });

  it('emits no class hook that cg.css has no rule for in the grant blocks (#3667 shape)', () => {
    const { container } = renderWithCharacterCreationProviders(
      <div className="interview">
        <FinalTouchesStage
          draft={createMockDraft({
            final_touches_prompts: ['prestige_story', 'organization', 'path_aspect'],
            final_touches_cards: [drama, honors, mentor],
            organization_choices: [lodge],
          })}
          onRegisterBeforeLeave={vi.fn()}
        />
      </div>
    );
    const styledElsewhere = new Set(['leaf-body', 'chosen', 'entry', 'note-group']);
    expect(unreachableClasses(container, styledElsewhere)).toEqual([]);
  });
});
