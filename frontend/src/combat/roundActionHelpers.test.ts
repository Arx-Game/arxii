import { hopsLeftLine, isMoveAction } from './roundActionHelpers';
import type { PlayerAction } from '@/scenes/actionTypes';

function entry(registryKey: string, description: string, met = true): PlayerAction {
  return {
    backend: 'registry',
    display_name: registryKey,
    description,
    difficulty: null,
    prerequisite_met: met,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Standard' },
    action_template: null,
    ref: {
      backend: 'registry',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: null,
      registry_key: registryKey,
      position_id: null,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}

describe('isMoveAction (#4663)', () => {
  it('counts a step, a take-off, a landing and a pass roll as moves', () => {
    for (const key of ['move_to_position', 'take_flight', 'land', 'pass_held_ground']) {
      expect(isMoveAction(entry(key, ''))).toBe(true);
    }
    expect(isMoveAction(entry('take_position', ''))).toBe(false);
    expect(isMoveAction(entry('set_the_stage', ''))).toBe(false);
  });
});

describe('hopsLeftLine (#4663)', () => {
  it('reads the hops line past a held place note on the first move', () => {
    const actions = [
      entry('move_to_position', "Held by Bandit: you'd stop there."),
      entry('pass_held_ground', 'Slip past'),
      entry('move_to_position', '2 hops left this round.'),
    ];
    expect(hopsLeftLine(actions)).toBe('2 hops left this round.');
  });

  it('is null when every move is refused or no move carries the line', () => {
    expect(hopsLeftLine([entry('move_to_position', '1 hop left this round.', false)])).toBeNull();
    expect(hopsLeftLine([entry('move_to_position', 'A cobbled yard.')])).toBeNull();
  });
});
