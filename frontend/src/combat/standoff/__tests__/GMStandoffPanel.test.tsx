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
      { label: 'Greedy', strength: 'Defining', revealed: true },
      { label: 'Loyal', strength: 'Minor', revealed: false },
    ],
    faction_rules: [
      {
        faction_rule_id: 1,
        label: 'House rank 2+',
        angle_text: '',
        difficulty_shift_bands: 1,
        suppresses_cause: false,
        matched_by: ['Aubrin'],
        revealed: false,
      },
      {
        faction_rule_id: 2,
        label: 'Spellcraft',
        angle_text: '',
        difficulty_shift_bands: 1,
        suppresses_cause: false,
        matched_by: [],
        revealed: false,
      },
    ],
    members: [{ opponent_id: 1, name: 'Sellsword A', morale: 70, morale_state: 'steady' }],
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
});
