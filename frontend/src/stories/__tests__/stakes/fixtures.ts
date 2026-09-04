/**
 * Shared fixture builders for the stakes editor test suite (#3561).
 */

import type { Beat, Stake, StakeRewardLine, StakeResolution, StakeTemplate } from '../../types';

export function makeBeat(overrides: Partial<Beat> = {}): Beat {
  return {
    id: 200,
    episode: 100,
    episode_title: 'The Reckoning',
    chapter_title: 'Act I',
    story_id: 1,
    story_title: 'Who Am I?',
    predicate_type: 'outcome_tier',
    outcome: 'unsatisfied',
    visibility: 'hinted',
    kind: 'task',
    internal_description: 'The villain escapes or is captured',
    player_hint: 'Confront the villain',
    order: 1,
    agm_eligible: false,
    advances: true,
    risk: 'moderate',
    target_level: 5,
    scenario: null,
    required_mission: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    can_mark: true,
    ...overrides,
  } as Beat;
}

export function makeStake(overrides: Partial<Stake> = {}): Stake {
  return {
    id: 10,
    beat: 200,
    template: 5,
    subject_kind: 'personal_jeopardy',
    severity: 2,
    subject_sheet: null,
    subject_item: null,
    subject_society: null,
    subject_organization: null,
    subject_asset: null,
    subject_label: '',
    player_summary: 'Everyone risks their standing with the court.',
    outcomes: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  } as Stake;
}

export function makeTemplate(overrides: Partial<StakeTemplate> = {}): StakeTemplate {
  return {
    id: 5,
    name: 'Courtly disfavor',
    subject_kind: 'personal_jeopardy',
    severity: 2,
    min_risk: 'low',
    max_risk: 'high',
    player_summary_template: 'Standing with the court is at risk.',
    description: '',
    is_active: true,
    ...overrides,
  } as StakeTemplate;
}

export function makeResolution(overrides: Partial<StakeResolution> = {}): StakeResolution {
  return {
    id: 30,
    stake: 10,
    column: 'win',
    outcome_key: '',
    consequence_pool: null,
    escalates_to_risk: '',
    narrative_summary: '',
    forfeits_subject_item: false,
    subject_standing_delta: 0,
    npc_regard_delta: 0,
    sets_subject_lifecycle: '',
    machine_match_lifecycle_state: '',
    transitions_subject_asset: '',
    reward_lines: [],
    ...overrides,
  } as StakeResolution;
}

export function makeRewardLine(overrides: Partial<StakeRewardLine> = {}): StakeRewardLine {
  return {
    id: 50,
    resolution: 30,
    sink: 'money',
    amount: 10,
    resonance: null,
    item_template: null,
    clue: null,
    codex_entry: null,
    item_template_name: '',
    clue_name: '',
    codex_entry_name: '',
    ...overrides,
  } as StakeRewardLine;
}
