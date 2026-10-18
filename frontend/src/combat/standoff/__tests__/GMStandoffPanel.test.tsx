import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { components } from '@/generated/api';

const mutate = vi.fn();
let error: Error | null = null;
vi.mock('@/combat/queries', () => ({
  useStandoffMorale: () => ({ mutate, isPending: false, error, reset: vi.fn() }),
}));

import { GMStandoffPanel } from '../GMStandoffPanel';

type GMGroupView = components['schemas']['GMGroupView'];

function group(patch: Partial<GMGroupView> = {}): GMGroupView {
  return {
    group_id: 3,
    name: 'Saltreed sellswords',
    state: 'open',
    member_count: 6,
    cause: 'Orders',
    cause_revealed: true,
    cause_fires: false,
    cause_reason: '',
    cause_margin_percent: 25,
    cause_clock: '',
    effective_margin_percent: 25,
    proposal_reason: '',
    pending_prompt_id: null,
    last_decision: '',
    override_standing: false,
    emboldened_bands: 0,
    terms_ease: 0,
    has_morale: true,
    morale_state: 'steady',
    party_force: 41,
    effective_party_force: 41,
    group_force: 30,
    drives: [
      { label: 'Greedy', strength: 'Defining', revealed: true, edited: false },
      { label: 'Loyal', strength: 'Minor', revealed: false, edited: false },
    ],
    faction_rules: [
      {
        faction_rule_id: 1,
        label: 'House rank 2+',
        angle_text: '',
        difficulty_shift_bands: 1,
        cause_effect: 'none',
        matched_by: ['Aubrin'],
        revealed: false,
        source: 'Saltreed Company',
      },
      {
        faction_rule_id: 2,
        label: 'Spellcraft',
        angle_text: '',
        difficulty_shift_bands: 1,
        cause_effect: 'none',
        matched_by: [],
        revealed: false,
        source: 'Sellsword',
      },
    ],
    members: [{ opponent_id: 1, name: 'Sellsword A', morale: 70, morale_state: 'steady' }],
    affiliation: '',
    cause_edited: false,
    affiliation_edited: false,
    is_named_npc: false,
    speaks: [],
    regards: [],
    ...patch,
  };
}

function renderPanel(g: GMGroupView = group()) {
  return render(
    <GMStandoffPanel
      encounterId={9}
      standoff={{ place: 'the gate', participants: ['Aubrin', 'Wrenna'], groups: [g] }}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  error = null;
});

describe('GMStandoffPanel', () => {
  it('shows a Territory clock and what a rule does to the cause (#4415)', () => {
    renderPanel(
      group({
        cause: 'Territory',
        cause_clock: 'Patience: 2 of 3 actions.',
        faction_rules: [
          {
            faction_rule_id: 4,
            label: 'has_capability: Spellcraft',
            angle_text: '',
            difficulty_shift_bands: 0,
            cause_effect: 'provoke',
            matched_by: ['Wrenna'],
            revealed: false,
            source: 'Den wolf',
          },
        ],
      })
    );
    const box = screen.getByTestId('gm-standoff-group');
    expect(within(box).getByTestId('gm-standoff-cause-clock')).toHaveTextContent(
      'Patience: 2 of 3 actions.'
    );
    expect(within(box).getByText(/provokes them/)).toBeInTheDocument();
  });

  it('judges the force line on the margin a hungry group widened (#4415)', () => {
    renderPanel(
      group({
        cause: 'Hunger',
        cause_margin_percent: 0,
        effective_margin_percent: 40,
        effective_party_force: 10,
        group_force: 8,
      })
    );
    const box = screen.getByTestId('gm-standoff-group');
    expect(within(box).getByText(/Force: party 10, them 8\./)).toBeInTheDocument();
    expect(within(box).queryByText(/Party outweighs them/)).toBeNull();
  });

  it('shows no clock for a cause without one', () => {
    renderPanel();
    expect(screen.queryByTestId('gm-standoff-cause-clock')).toBeNull();
  });

  it('marks what the placement edited and where each rule came from (#4361)', () => {
    renderPanel(
      group({
        affiliation: 'Saltreed Company',
        affiliation_edited: true,
        cause_edited: true,
        drives: [{ label: 'Greedy', strength: 'Defining', revealed: false, edited: true }],
      })
    );
    const box = screen.getByTestId('gm-standoff-group');
    expect(within(box).getAllByText('edited here')).toHaveLength(2);
    expect(within(box).getByText('set on this line')).toBeInTheDocument();
    expect(within(box).getByText('Affiliation')).toBeInTheDocument();
    expect(within(box).getByText('Sellsword')).toBeInTheDocument();
  });

  it('renders the profile, matches and force', () => {
    renderPanel();
    const box = screen.getByTestId('gm-standoff-group');
    expect(within(box).getByText('Saltreed sellswords')).toBeInTheDocument();
    expect(within(box).getByText('holds: will not attack first')).toBeInTheDocument();
    expect(within(box).getByText(/read by the party/)).toBeInTheDocument();
    expect(within(box).getByText('read')).toBeInTheDocument();
    expect(within(box).getByText('unread')).toBeInTheDocument();
    expect(within(box).getByText(/Sellsword A 70 \(steady\)/)).toBeInTheDocument();
    expect(within(box).getByText('Aubrin')).toBeInTheDocument();
    expect(within(box).getByText('nobody')).toBeInTheDocument();
    expect(
      within(box).getByText(/Force: party 41, them 30\. Party outweighs them\./)
    ).toBeInTheDocument();
    expect(screen.getByText('In the standoff: Aubrin, Wrenna.')).toBeInTheDocument();
  });

  it('shows the firing cause, proposed and emboldened chips, and the prompt pointer', () => {
    renderPanel(
      group({
        state: 'proposed',
        emboldened_bands: 1,
        cause_fires: true,
        cause_reason: 'provoked',
        pending_prompt_id: 5,
        proposal_reason: 'Critical failure on a press.',
        effective_party_force: 20,
      })
    );
    expect(screen.getByText('proposed')).toBeInTheDocument();
    expect(screen.getByText('emboldened')).toBeInTheDocument();
    expect(screen.getByText('fires: provoked')).toBeInTheDocument();
    expect(
      screen.getByText(/Critical failure on a press\. Decide it in the GM prompts/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/Party outweighs them/)).toBeNull();
  });

  it("shows the GM's last decision once no proposal is pending", () => {
    renderPanel(group({ last_decision: 'Held for one action.' }));
    expect(screen.getByTestId('standoff-last-decision')).toHaveTextContent(
      'Last decision: Held for one action.'
    );
  });

  it('hides the morale control when the group has no morale', () => {
    renderPanel(group({ has_morale: false }));
    expect(screen.queryByRole('button', { name: 'Shake' })).toBeNull();
  });

  it('refuses shake without a reason, then posts it with one', async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole('button', { name: 'Shake' }));
    const confirm = screen.getByTestId('standoff-morale-confirm');
    expect(
      within(confirm).getByText('moves them one state: steady to faltering')
    ).toBeInTheDocument();
    const submit = within(confirm).getByRole('button', { name: 'Shake' });
    expect(submit).toBeDisabled();
    await user.click(submit);
    expect(mutate).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('Reason (required)'), 'Their captain fell');
    await user.click(submit);
    expect(mutate).toHaveBeenCalledWith(
      { group_id: 3, direction: 'shake', reason: 'Their captain fell' },
      expect.anything()
    );
  });

  it('shows the server refusal', async () => {
    error = new Error('Group has no morale to change.');
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole('button', { name: 'Steady' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Group has no morale to change.');
  });

  it('shows a named NPC group with what it speaks and its regard per player (#4373)', () => {
    renderPanel(
      group({
        name: 'Maud Test',
        is_named_npc: true,
        member_count: 1,
        speaks: ['Riverland test common'],
        regards: [{ participant: 'Wrenna Test', regard: -150, label: 'negative', bands: 1 }],
      })
    );
    const box = screen.getByTestId('gm-standoff-group');
    expect(box).toHaveTextContent('named NPC');
    expect(screen.getByTestId('gm-standoff-speaks')).toHaveTextContent('Riverland test common');
    expect(screen.getByTestId('gm-standoff-regard')).toHaveTextContent(
      'Wrenna Test: negative (-150)'
    );
  });

  it('says a group with no language speaks none', () => {
    renderPanel(group());
    expect(screen.getByTestId('gm-standoff-speaks')).toHaveTextContent('no language');
    expect(screen.queryByTestId('gm-standoff-regard')).toBeNull();
  });
});
