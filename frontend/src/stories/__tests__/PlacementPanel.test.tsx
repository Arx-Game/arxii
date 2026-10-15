import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { PlacementContext } from '@/combat/api';

const CONTEXT: PlacementContext = {
  creature_template: 4,
  name: 'Sellsword',
  cause: 'orders',
  cause_label: 'Orders',
  cause_margin_percent: 10,
  organization: 7,
  organization_name: 'Saltreed Company',
  drives: [
    { property: 11, name: 'Greedy', strength: 2, strength_label: 'Major' },
    { property: 12, name: 'Fearful', strength: 1, strength_label: 'Minor' },
  ],
  inherited_rules: [
    { faction_rule_id: 21, label: 'has_capability: Warding', source: 'Sellsword', level: 0 },
    {
      faction_rule_id: 22,
      label: 'associated_with_org: Saltreed Company',
      source: 'Saltreed Company',
      level: 1,
    },
  ],
};

vi.mock('@/combat/queries', () => ({
  useCreatureTemplates: () => ({ data: [{ id: 4, name: 'Sellsword', tier: 'mook' }] }),
  usePlacementContext: () => ({ data: CONTEXT }),
  usePlacementPicks: (kind: string) => ({
    data:
      kind === 'properties' ? [{ id: 31, name: 'Prudent' }] : [{ id: 8, name: 'Riverland Guilds' }],
  }),
}));

import { OpponentLinesEditor } from '../components/OpponentLinesEditor';
import { placementPayload, placementSummary } from '../components/placementDraft';

const LINE = {
  creature_template: '4',
  count: '6',
  position_name: '',
  opens_as_standoff: true,
};

function renderEditor(onChange = vi.fn(), line: Record<string, unknown> = LINE) {
  render(
    <OpponentLinesEditor
      lines={[line as never]}
      onChange={onChange}
      rowErrors={undefined}
      showStandoffSwitch
      showPlacement
    />
  );
  return onChange;
}

describe('PlacementPanel (#4361)', () => {
  it('shows the template values beside each pick and a spawn summary', () => {
    renderEditor();
    expect(screen.getByText('Standoff for this line')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Orders (template)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Saltreed Company (template)' })).toBeInTheDocument();
    expect(screen.getByLabelText('Greedy here')).toHaveValue('same');
    expect(screen.getByText('Saltreed Company', { selector: 'td' })).toBeInTheDocument();
    expect(screen.getByTestId('placement-summary-0')).toHaveTextContent(
      'Spawns 6 Sellsword: Orders, Greedy (Major), Fearful (Minor), 2 faction rules.'
    );
  });

  it('writes a drive edit and a removal into the line', async () => {
    const user = userEvent.setup();
    const onChange = renderEditor();
    await user.selectOptions(screen.getByLabelText('Greedy here'), '3');
    expect(onChange).toHaveBeenLastCalledWith([
      { ...LINE, drive_edits: [{ property: 11, property_name: 'Greedy', strength: 3 }] },
    ]);
    await user.selectOptions(screen.getByLabelText('Fearful here'), 'remove');
    expect(onChange).toHaveBeenLastCalledWith([
      { ...LINE, drive_edits: [{ property: 12, property_name: 'Fearful', strength: null }] },
    ]);
  });

  it('switches off an inherited rule', async () => {
    const user = userEvent.setup();
    const onChange = renderEditor();
    await user.click(screen.getByLabelText('Off: associated_with_org: Saltreed Company'));
    expect(onChange).toHaveBeenLastCalledWith([{ ...LINE, suppressed_faction_rules: [22] }]);
  });

  it('adds a drive from the property catalog', async () => {
    const user = userEvent.setup();
    const onChange = renderEditor();
    await user.click(screen.getByRole('button', { name: '+ Add a drive' }));
    await user.selectOptions(screen.getByTestId('placement-add-drive-0'), '31');
    expect(onChange).toHaveBeenLastCalledWith([
      { ...LINE, drive_edits: [{ property: 31, property_name: 'Prudent', strength: 1 }] },
    ]);
  });

  it('keeps the standoff switch inside the panel', async () => {
    const user = userEvent.setup();
    const onChange = renderEditor();
    await user.click(screen.getByLabelText('Opens as a standoff'));
    expect(onChange).toHaveBeenLastCalledWith([{ ...LINE, opens_as_standoff: false }]);
  });

  it('builds the payload and the summary from edits', () => {
    const draft = {
      cause_override: 'predation',
      drive_edits: [
        { property: 12, property_name: 'Fearful', strength: null },
        { property: 31, property_name: 'Prudent', strength: 1 },
      ],
      suppressed_faction_rules: [21],
    };
    expect(placementPayload(draft)).toEqual({
      cause_override: 'predation',
      cause_margin_override: null,
      organization: null,
      organization_name: '',
      drive_edits: [
        { property: 12, property_name: 'Fearful', strength: null },
        { property: 31, property_name: 'Prudent', strength: 1 },
      ],
      suppressed_faction_rules: [21],
    });
    expect(placementSummary(CONTEXT, draft, '2')).toBe(
      'Spawns 2 Sellsword: Predation, Greedy (Major), Prudent (Minor), 1 faction rule.'
    );
  });
});
