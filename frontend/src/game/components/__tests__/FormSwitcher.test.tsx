import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { SwitchableAlternateSelf } from '../../formQueries';
import { FormSwitcher } from '../FormSwitcher';

const { state } = vi.hoisted(() => ({
  state: { alternates: [] as SwitchableAlternateSelf[] },
}));

vi.mock('../../formQueries', () => ({
  useAlternateSelvesQuery: () => ({ data: state.alternates }),
  useShiftFormMutation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  useRevertFormMutation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
}));

function alternate(id: number, name: string): SwitchableAlternateSelf {
  return {
    id,
    display_name: name,
    persona_name: null,
    form_name: name,
    has_combat_profile: false,
    has_techniques: false,
    is_active: false,
    compulsion: null,
  };
}

describe('FormSwitcher', () => {
  // #4321: with nothing to shift into there is no form control at all, the
  // same rule PersonaSwitcher applies to a single face.
  it('draws nothing for a character with no alternate self', () => {
    state.alternates = [];
    const { container } = render(<FormSwitcher characterSheetId={1} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText('True self')).not.toBeInTheDocument();
  });

  it('shows the worn form once an alternate self exists', () => {
    state.alternates = [alternate(2, 'Wolf')];
    render(<FormSwitcher characterSheetId={1} />);
    expect(screen.getByTitle('Shift into an alternate self')).toHaveTextContent('True self');
  });

  it('marks Revert with its difficulty while a compulsion judges changing back', () => {
    state.alternates = [
      {
        ...alternate(2, 'Wolf'),
        is_active: true,
        compulsion: {
          condition_name: 'Berserk',
          wants_label: 'Attack an opponent',
          attack_target_name: 'Bandit Captain',
          check_name: 'Resist compulsion',
          against: [
            {
              action_key: 'revert_form',
              label: 'revert_form',
              difficulty: 41,
              forbidden: true,
              extra_difficulty: 10,
            },
          ],
        },
      },
    ];
    render(<FormSwitcher characterSheetId={1} />);
    expect(screen.getByTestId('compulsion-difficulty-revert_form')).toHaveTextContent(
      'Forbidden, difficulty 41'
    );
  });
});
