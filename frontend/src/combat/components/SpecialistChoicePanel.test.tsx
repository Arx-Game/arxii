import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { SpecialistChoicePanel } from './SpecialistChoicePanel';

const mutate = vi.fn();
vi.mock('../queries', () => ({
  useResolvePendingSelection: () => ({ mutate, isPending: false }),
}));

const selection = {
  id: 7,
  participant_id: 3,
  selection_type: 'weakness',
  options: [
    { id: 'armor', label: 'Armor Crack', description: 'Expose a seam.' },
    { id: 'flame', label: 'Fear of Flame', description: '' },
  ],
  selected_option_id: null,
  target_opponent_id: 4,
  target_opponent_name: 'The boss',
  created_at: '2026-09-19T00:00:00Z',
  resolved: false,
};

describe('SpecialistChoicePanel', () => {
  it('withholds the panel when no choice is pending', () => {
    render(<SpecialistChoicePanel encounterId={11} selections={[]} />);
    expect(screen.queryByTestId('specialist-choice-panel')).not.toBeInTheDocument();
  });

  it('lets the player choose and apply an authored option', () => {
    render(<SpecialistChoicePanel encounterId={11} selections={[selection]} />);
    fireEvent.click(screen.getByRole('button', { name: /Armor Crack/ }));
    fireEvent.click(screen.getByRole('button', { name: /Apply choice/ }));
    expect(mutate).toHaveBeenCalledWith({ selectionId: 7, optionId: 'armor' });
  });
});
