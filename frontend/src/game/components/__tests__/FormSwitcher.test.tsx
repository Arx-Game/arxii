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
});
