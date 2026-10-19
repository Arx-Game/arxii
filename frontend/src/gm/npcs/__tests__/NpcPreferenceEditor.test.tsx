import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { PersonalityTrait } from '../npcFormApi';
import { NpcPreferenceEditor } from '../NpcPreferenceEditor';

const duty: PersonalityTrait = {
  id: 9,
  name: 'Duty',
  description: 'Persuade checks that invoke his men.',
  eased_check: 'Persuade',
};

describe('NpcPreferenceEditor', () => {
  it('keeps the add controls when no trait is authored, with the reason as the option', () => {
    render(<NpcPreferenceEditor traits={[]} lines={[]} onChange={vi.fn()} />);
    expect(screen.getByLabelText('Trait')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'No traits authored yet' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add trait' })).toBeDisabled();
  });

  it("shows the chosen trait's description and eased check as the row's note", () => {
    render(
      <NpcPreferenceEditor
        traits={[duty]}
        lines={[{ trait: 9, valence: 'likes' }]}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByTestId('trait-note')).toHaveTextContent(
      'Persuade checks that invoke his men. Eases Persuade.'
    );
  });

  it('names no eased check on a dislike', () => {
    render(
      <NpcPreferenceEditor
        traits={[duty]}
        lines={[{ trait: 9, valence: 'dislikes' }]}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByTestId('trait-note')).toHaveTextContent(
      /^Persuade checks that invoke his men\.$/
    );
  });

  it('adds a line from the pickers', async () => {
    const onChange = vi.fn();
    render(<NpcPreferenceEditor traits={[duty]} lines={[]} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText('Trait'), '9');
    await userEvent.click(screen.getByRole('button', { name: 'Add trait' }));
    expect(onChange).toHaveBeenCalledWith([{ trait: 9, valence: 'likes' }]);
  });
});
