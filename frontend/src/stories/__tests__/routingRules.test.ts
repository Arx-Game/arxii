import { describe, expect, it } from 'vitest';
import { formatRoutingRule, formatRoutingRules } from '../routingRules';
import type { TransitionRoutingRule } from '../types';

const beatRule: TransitionRoutingRule = {
  id: 1,
  beat: 4,
  beat_title: 'Hostage exchange',
  required_outcome: 'failure',
  required_outcome_key: '',
  stake: null,
  stake_summary: '',
  required_stake_column: '',
};

const stakeRule: TransitionRoutingRule = {
  id: 2,
  beat: 4,
  beat_title: 'Hostage exchange',
  required_outcome: '',
  required_outcome_key: '',
  stake: 9,
  stake_summary: 'The hostage',
  required_stake_column: 'loss',
};

describe('formatRoutingRule', () => {
  it('renders a beat rule as title = OUTCOME', () => {
    expect(formatRoutingRule(beatRule)).toBe('Hostage exchange = FAILURE');
  });

  it('appends the option key when set', () => {
    expect(
      formatRoutingRule({
        ...beatRule,
        required_outcome: 'success',
        required_outcome_key: 'negotiate',
      })
    ).toBe('Hostage exchange = SUCCESS (negotiate)');
  });

  it('falls back to beat #id when the title is blank', () => {
    expect(formatRoutingRule({ ...beatRule, beat_title: '' })).toBe('beat #4 = FAILURE');
  });

  it('renders a stake rule from the player summary', () => {
    expect(formatRoutingRule(stakeRule)).toBe('The hostage = LOSS');
  });

  it('falls back to stake #id when the summary is blank', () => {
    expect(formatRoutingRule({ ...stakeRule, stake_summary: '' })).toBe('stake #9 = LOSS');
  });
});

describe('formatRoutingRules', () => {
  it('joins rules with a middle dot and is empty without rules', () => {
    expect(formatRoutingRules([beatRule, stakeRule])).toBe(
      'Hostage exchange = FAILURE · The hostage = LOSS'
    );
    expect(formatRoutingRules([])).toBe('');
    expect(formatRoutingRules(undefined)).toBe('');
  });
});
