import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/magic/queries', () => ({
  useCharacterResonances: () => ({
    data: [
      { resonance: 7, resonance_name: 'Ember' },
      { resonance: 8, resonance_name: 'Tide' },
    ],
  }),
}));

// Stub ThreadPullDialog the way YourTurn's tests do: a button stands in for a chosen pull.
vi.mock('@/magic/components/threads/ThreadPullDialog', () => ({
  ThreadPullDialog: ({
    open,
    combat,
    onSelect,
  }: {
    open: boolean;
    combat?: { involvedTechniqueIds: number[] };
    onSelect: (sel: { resonance_id: number; tier: 1 | 2 | 3; thread_ids: number[] }) => void;
  }) =>
    open ? (
      <div data-testid="thread-pull-dialog-stub">
        <span data-testid="stub-technique-ids">{combat?.involvedTechniqueIds.join(',')}</span>
        <button
          type="button"
          data-testid="simulate-pull-select"
          onClick={() => onSelect({ resonance_id: 5, tier: 2, thread_ids: [10, 11] })}
        >
          Simulate Select Pull
        </button>
      </div>
    ) : null,
}));

import { AreaAttackWarning } from '../AreaAttackWarning';
import { AreaTelegraphLayer } from '../AreaTelegraphLayer';
import { attacksCoveringPlace, telegraphLine } from '../../dodging';
import { CommitmentPanel } from '../CommitmentPanel';
import { DodgePlanPanel } from '../DodgePlanPanel';
import { RoundThreadPull } from '../RoundThreadPull';
import type { components } from '@/generated/api';
import type { EncounterDetail, PendingAttack } from '../../types';

type DodgePlan = components['schemas']['DodgePlan'];

const PLAN: DodgePlan = {
  enabled: true,
  landing_id: null,
  options: [
    { id: 13, name: 'Stage' },
    { id: 14, name: 'Gallery' },
  ],
  cost_line: 'Each dodge costs 2 anima. Each dodge after the first this round is harder.',
  techniques: [],
  technique_id: null,
  into_soulfray: false,
  auto_pull: false,
  auto_pull_resonance_id: null,
  auto_pull_tier: null,
  soulfray_check_in: null,
};

const TECHNIQUE_PLAN: DodgePlan = {
  ...PLAN,
  techniques: [
    {
      id: 31,
      name: 'Shadow Step',
      cost_line: 'Each dodge casts Shadow Step: 3 anima.',
      is_default: true,
    },
    {
      id: 32,
      name: 'Wind Leap',
      cost_line: 'Each dodge casts Wind Leap: 5 anima.',
      is_default: false,
    },
  ],
  technique_id: 31,
};

const SETTINGS_REF = { backend: 'registry', registry_key: 'dodge_settings' };

function ok() {
  return vi.fn().mockResolvedValue({ success: true, message: null });
}

function fire(overrides: Partial<PendingAttack> = {}): PendingAttack {
  return {
    id: 1,
    opponent_id: 10,
    opponent_name: 'Harrow',
    target_participant_id: null,
    target_name: null,
    declared_round: 2,
    resolves_round: 3,
    rounds_until_landing: 0,
    downgrades: 0,
    called_out: false,
    damage_scale: 1,
    cancelled: false,
    attack_name: 'Holy fire',
    covered_position_id: 12,
    covered_position_name: 'Floor',
    ...overrides,
  };
}

describe('DodgePlanPanel', () => {
  it('offers dodging in place, each other reachable place and not dodging, with the cost', () => {
    render(
      <DodgePlanPanel
        plan={PLAN}
        characterSheetId={100}
        currentPositionId={13}
        isLocked={false}
        dispatchAction={ok()}
      />
    );
    expect(screen.getByTestId('dodge-in-place')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Dodge to Gallery')).toBeInTheDocument();
    expect(screen.queryByText('Dodge to Stage')).not.toBeInTheDocument();
    expect(screen.getByText("Don't dodge")).toBeInTheDocument();
    expect(screen.getByTestId('dodge-cost')).toHaveTextContent(PLAN.cost_line);
  });

  it('sends the landing, or dodge false, through combat_dodge', async () => {
    const dispatch = ok();
    render(
      <DodgePlanPanel
        plan={PLAN}
        characterSheetId={100}
        currentPositionId={13}
        isLocked={false}
        dispatchAction={dispatch}
      />
    );
    await userEvent.click(screen.getByText('Dodge to Gallery'));
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: { backend: 'registry', registry_key: 'combat_dodge' },
      kwargs: { position_id: 14 },
    });
    await userEvent.click(screen.getByText("Don't dodge"));
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: { backend: 'registry', registry_key: 'combat_dodge' },
      kwargs: { dodge: false },
    });
  });
});

describe('DodgePlanPanel dodge settings', () => {
  function renderPanel(plan: DodgePlan, dispatch = ok(), isLocked = false) {
    render(
      <DodgePlanPanel
        plan={plan}
        characterSheetId={100}
        currentPositionId={13}
        isLocked={isLocked}
        dispatchAction={dispatch}
      />
    );
    return dispatch;
  }

  it('picks the technique that answers her dodges, marking her default', async () => {
    const dispatch = renderPanel(TECHNIQUE_PLAN);
    expect(screen.getByTestId('dodge-technique-cost')).toHaveTextContent(
      'Each dodge casts Shadow Step: 3 anima.'
    );
    expect(screen.queryByTestId('dodge-technique-save-default')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('combobox', { name: 'Dodge with' }));
    expect(
      await screen.findByRole('option', { name: 'Shadow Step (default)' })
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('option', { name: 'Wind Leap' }));
    expect(dispatch).toHaveBeenLastCalledWith({ ref: SETTINGS_REF, kwargs: { technique_id: 32 } });
  });

  it('saves the chosen technique as her default', async () => {
    const dispatch = renderPanel({ ...TECHNIQUE_PLAN, technique_id: 32 });
    expect(screen.getByTestId('dodge-technique-cost')).toHaveTextContent('Wind Leap: 5 anima');
    await userEvent.click(screen.getByRole('button', { name: 'Save as my default' }));
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: SETTINGS_REF,
      kwargs: { technique_id: 32, save_default: true },
    });
  });

  it('hides the technique picker when no technique can answer her dodges', () => {
    renderPanel(PLAN);
    expect(screen.queryByTestId('dodge-technique')).not.toBeInTheDocument();
  });

  it('turns dodging into Soulfray on', async () => {
    const dispatch = renderPanel(TECHNIQUE_PLAN);
    const toggle = screen.getByRole('switch', { name: 'Dodge even into Soulfray' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(toggle);
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: SETTINGS_REF,
      kwargs: { into_soulfray: true },
    });
  });

  it('checks in when her dodges would cast into Soulfray', async () => {
    const dispatch = renderPanel({
      ...TECHNIQUE_PLAN,
      into_soulfray: true,
      soulfray_check_in: {
        stage_name: 'Fraying',
        stage_description: 'Your soul thins at the edges.',
        has_death_risk: true,
      },
    });
    const gate = screen.getByTestId('dodge-soulfray-check-in');
    expect(gate).toHaveTextContent('DANGER: Soulfray Warning: Fraying');
    expect(gate).toHaveTextContent('Your soul thins at the edges.');
    expect(gate).toHaveTextContent('Your automatic dodges cast into Soulfray.');
    const keep = screen.getByRole('checkbox', { name: 'Keep dodging into Soulfray' });
    expect(keep).toBeChecked();
    await userEvent.click(keep);
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: SETTINGS_REF,
      kwargs: { into_soulfray: false },
    });
  });

  it('turns the defensive pull on with a resonance and tier', async () => {
    const dispatch = renderPanel(TECHNIQUE_PLAN);
    const toggle = screen.getByRole('switch', { name: 'Pull threads for defense when attacked' });
    expect(toggle).toBeDisabled();
    await userEvent.click(screen.getByRole('combobox', { name: 'Resonance' }));
    await userEvent.click(await screen.findByRole('option', { name: 'Tide' }));
    await userEvent.click(screen.getByRole('combobox', { name: 'Tier' }));
    await userEvent.click(await screen.findByRole('option', { name: 'Tier 3' }));
    expect(dispatch).not.toHaveBeenCalled();
    await userEvent.click(toggle);
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: SETTINGS_REF,
      kwargs: { auto_pull: true, pull_resonance_id: 8, pull_tier: 3 },
    });
  });

  it('turns a saved defensive pull off', async () => {
    const dispatch = renderPanel({
      ...TECHNIQUE_PLAN,
      auto_pull: true,
      auto_pull_resonance_id: 7,
      auto_pull_tier: 2,
    });
    await userEvent.click(
      screen.getByRole('switch', { name: 'Pull threads for defense when attacked' })
    );
    expect(dispatch).toHaveBeenLastCalledWith({ ref: SETTINGS_REF, kwargs: { auto_pull: false } });
  });

  it('locks every setting once her turn is locked', () => {
    renderPanel(TECHNIQUE_PLAN, ok(), true);
    expect(screen.getByRole('combobox', { name: 'Dodge with' })).toBeDisabled();
    expect(screen.getByRole('switch', { name: 'Dodge even into Soulfray' })).toBeDisabled();
    expect(
      screen.getByRole('switch', { name: 'Pull threads for defense when attacked' })
    ).toBeDisabled();
  });
});

describe('RoundThreadPull', () => {
  function renderPull(dispatch: ReturnType<typeof ok>) {
    return render(
      <RoundThreadPull
        characterSheetId={100}
        encounterId={1}
        participantId={2}
        techniqueIds={[31, 32]}
        roundNumber={4}
        isLocked={false}
        dispatchAction={dispatch}
      />
    );
  }

  it('opens the pull dialog with her techniques and sends combat_pull, then hides', async () => {
    const dispatch = vi
      .fn()
      .mockResolvedValue({ success: true, message: 'You pull 2 threads for the round.' });
    renderPull(dispatch);
    await userEvent.click(screen.getByRole('button', { name: 'Pull threads for the round' }));
    expect(screen.getByTestId('stub-technique-ids')).toHaveTextContent('31,32');
    await userEvent.click(screen.getByTestId('simulate-pull-select'));
    expect(dispatch).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'combat_pull' },
      kwargs: { pull_resonance_id: 5, pull_tier: 2, pull_thread_ids: [10, 11] },
    });
    await waitFor(() => expect(screen.queryByTestId('round-pull-btn')).not.toBeInTheDocument());
  });

  it('keeps the button when the pull is refused', async () => {
    const dispatch = vi.fn().mockResolvedValue({
      success: false,
      message: 'You have already pulled a thread this round.',
    });
    renderPull(dispatch);
    await userEvent.click(screen.getByRole('button', { name: 'Pull threads for the round' }));
    await userEvent.click(screen.getByTestId('simulate-pull-select'));
    await waitFor(() => expect(dispatch).toHaveBeenCalled());
    expect(screen.getByTestId('round-pull-btn')).toBeInTheDocument();
  });
});

describe('AreaAttackWarning', () => {
  it('warns only about attacks covering her place and offers to leap clear or brace', async () => {
    const dispatch = ok();
    render(
      <AreaAttackWarning
        attacks={[fire(), fire({ id: 2, covered_position_id: 99, covered_position_name: 'Bar' })]}
        currentPositionId={12}
        plan={{ ...PLAN, options: [{ id: 12, name: 'Floor' }, ...PLAN.options] }}
        isLocked={false}
        dispatchAction={dispatch}
      />
    );
    expect(screen.getByText(/will cover the whole Floor when it lands/)).toBeInTheDocument();
    expect(screen.queryByText(/whole Bar/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByText('Leap clear to Stage'));
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: { backend: 'registry', registry_key: 'combat_dodge' },
      kwargs: { position_id: 13 },
    });
    expect(screen.getByTestId('area-brace')).toBeInTheDocument();
  });

  it('ignores cancelled attacks and attacks on other places', () => {
    expect(attacksCoveringPlace([fire({ cancelled: true })], 12)).toEqual([]);
    expect(attacksCoveringPlace([fire()], 13)).toEqual([]);
    expect(attacksCoveringPlace([fire()], null)).toEqual([]);
  });
});

describe('AreaTelegraphLayer', () => {
  it('says when it lands', () => {
    expect(telegraphLine('Holy fire', 0)).toBe('Holy fire lands here at the end of this round');
    expect(telegraphLine('Holy fire', 1)).toBe('Holy fire lands here next round');
    expect(telegraphLine('Holy fire', 3)).toBe('Holy fire lands here in 3 rounds');
  });

  it('tints the covered place and skips a place with no area', () => {
    render(
      <svg>
        <AreaTelegraphLayer
          areas={new Map([[12, { x: 2, y: 2, w: 8, h: 9, derived: false }]])}
          telegraphs={[
            { id: 1, positionId: 12, attackName: 'Holy fire', roundsUntilLanding: 0 },
            { id: 2, positionId: 99, attackName: 'Holy fire', roundsUntilLanding: 0 },
          ]}
        />
      </svg>
    );
    expect(screen.getByTestId('area-telegraph-12')).toBeInTheDocument();
    expect(screen.queryByTestId('area-telegraph-99')).not.toBeInTheDocument();
  });
});

describe('CommitmentPanel reactions', () => {
  it('counts reactions made this round, with no cap', () => {
    const encounter = {
      sustained_actions: [],
      protection_commitments: [],
      participants: [
        { id: 1, character_name: 'Ondrelle', reactions_used: 3 },
        { id: 2, character_name: 'Bram', reactions_used: 0 },
      ],
    } as unknown as EncounterDetail;
    render(<CommitmentPanel encounter={encounter} />);
    expect(screen.getByText('Ondrelle: 3 reactions this round')).toBeInTheDocument();
    expect(screen.queryByText(/Bram/)).not.toBeInTheDocument();
  });

  it('turns the steady plan on and off through combat_steady', async () => {
    const dispatch = ok();
    render(
      <DodgePlanPanel
        plan={null}
        characterSheetId={100}
        steadyPlan={{
          enabled: false,
          cost_line: '4 anima each',
          bonus_hint: '+6',
          capability_name: 'Calming presence',
        }}
        currentPositionId={13}
        isLocked={false}
        dispatchAction={dispatch}
      />
    );
    expect(screen.queryByTestId('dodge-plan')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Reactions' })).toBeInTheDocument();
    expect(screen.getByTestId('steady-cost')).toHaveTextContent(
      '(Calming presence) · 4 anima each · +6'
    );
    expect(screen.getByTestId('reaction-shared-note')).toHaveTextContent(
      'Each reaction this round makes the next one harder, steadying and dodging alike.'
    );
    const toggle = screen.getByRole('switch', { name: 'Steady allies who lose to a compulsion' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await userEvent.click(toggle);
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: { backend: 'registry', registry_key: 'combat_steady' },
      kwargs: { steady: true },
    });
  });
});
