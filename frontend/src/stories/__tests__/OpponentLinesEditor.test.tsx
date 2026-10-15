import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/combat/queries', () => ({
  useCreatureTemplates: () => ({ data: [] }),
}));

import { OpponentLinesEditor } from '../components/OpponentLinesEditor';

const LINES = [{ creature_template: '1', count: '2', position_name: '', opens_as_standoff: false }];

describe('OpponentLinesEditor standoff switch', () => {
  it('shows the checkbox only with showStandoffSwitch', () => {
    const { rerender } = render(
      <OpponentLinesEditor lines={LINES} onChange={vi.fn()} rowErrors={undefined} />
    );
    expect(screen.queryByLabelText('Opens as a standoff')).toBeNull();
    rerender(
      <OpponentLinesEditor
        lines={LINES}
        onChange={vi.fn()}
        rowErrors={undefined}
        showStandoffSwitch
      />
    );
    expect(screen.getByLabelText('Opens as a standoff')).not.toBeChecked();
  });

  it('writes opens_as_standoff into the line, and new lines default to false', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <OpponentLinesEditor
        lines={LINES}
        onChange={onChange}
        rowErrors={undefined}
        showStandoffSwitch
      />
    );
    await user.click(screen.getByLabelText('Opens as a standoff'));
    expect(onChange).toHaveBeenCalledWith([{ ...LINES[0], opens_as_standoff: true }]);
    await user.click(screen.getByRole('button', { name: 'Add opponent' }));
    expect(onChange).toHaveBeenLastCalledWith([
      LINES[0],
      { creature_template: '', count: '1', position_name: '', opens_as_standoff: false },
    ]);
  });
});
