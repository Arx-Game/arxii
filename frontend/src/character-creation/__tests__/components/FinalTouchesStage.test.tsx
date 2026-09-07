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
let offersResponse: OffersResponse;
vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync }),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: [] }),
  useSyncDistinctions: () => ({ mutate: vi.fn() }),
}));

const hedonistic: VisibleOffer = {
  offer_id: 301,
  distinction_id: 31,
  name: 'Hedonistic',
  player_line: 'If the vibes are good, you are good.',
  chapter: 'actors_sheet',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: 25,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
};

const voracious: VisibleOffer = {
  offer_id: 302,
  distinction_id: 32,
  name: 'Voracious',
  player_line: 'Need that borders on compulsion.',
  chapter: 'actors_sheet',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: 5,
  max_rank: 3,
  is_locked: false,
  lock_reason: '',
};

const rouault: EnemyOffer = {
  kind: 'group',
  organization_id: 7,
  name: 'the Rouault',
  reach: 'house',
  power_tier: '',
  why: '',
  source: 'lineage',
};
const republic: EnemyOffer = {
  kind: 'group',
  organization_id: 8,
  name: 'The Republic of Luxen',
  reach: 'realm',
  power_tier: '',
  why: 'it does not keep the Gifted',
  source: 'beginning',
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
      within(degrees).getByRole('button', { name: /ruined · Awards 32 CG points · grants Marked/ })
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
    expect(screen.getByRole('heading', { name: /Aurelie's First Journal/ })).toBeInTheDocument();
    expect(screen.queryByLabelText('What should the world know of you first?')).toBeNull();
    await user.click(screen.getAllByRole('button', { name: 'Write it' })[0]);
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

  it("offers this chapter's distinctions between the three questions and the Goals heading (#3675 Task 15)", () => {
    const { container } = renderWithCharacterCreationProviders(
      <FinalTouchesStage draft={createMockDraft()} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText('Is it a hunger')).toBeInTheDocument();
    expect(screen.getByText('Hedonistic')).toBeInTheDocument();
    expect(screen.getByText('Voracious')).toBeInTheDocument();
    const order = container.textContent ?? '';
    const questionsIdx = order.indexOf('What are you deathly afraid of?');
    const offersIdx = order.indexOf('Is it a hunger');
    const goalsIdx = order.indexOf('Goals');
    expect(questionsIdx).toBeGreaterThan(-1);
    expect(offersIdx).toBeGreaterThan(questionsIdx);
    expect(goalsIdx).toBeGreaterThan(offersIdx);
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
