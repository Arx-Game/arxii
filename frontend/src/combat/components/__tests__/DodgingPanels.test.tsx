import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { AreaAttackWarning } from '../AreaAttackWarning';
import { AreaTelegraphLayer } from '../AreaTelegraphLayer';
import { attacksCoveringPlace, telegraphLine } from '../../dodging';
import { CommitmentPanel } from '../CommitmentPanel';
import { DodgePlanPanel } from '../DodgePlanPanel';
import type { EncounterDetail, PendingAttack } from '../../types';

const PLAN = {
  enabled: true,
  landing_id: null,
  options: [
    { id: 13, name: 'Stage' },
    { id: 14, name: 'Gallery' },
  ],
  cost_line: 'Each dodge costs 2 anima. Each dodge after the first this round is harder.',
};

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
      <DodgePlanPanel plan={PLAN} currentPositionId={13} isLocked={false} dispatchAction={ok()} />
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
        steadyPlan={{ enabled: false, cost_line: '4 anima each', bonus_hint: '+6' }}
        currentPositionId={13}
        isLocked={false}
        dispatchAction={dispatch}
      />
    );
    expect(screen.queryByTestId('dodge-plan')).not.toBeInTheDocument();
    expect(screen.getByTestId('steady-cost')).toHaveTextContent('4 anima each · +6');
    await userEvent.click(screen.getByTestId('steady-toggle'));
    expect(dispatch).toHaveBeenLastCalledWith({
      ref: { backend: 'registry', registry_key: 'combat_steady' },
      kwargs: { steady: true },
    });
  });
});
