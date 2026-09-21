/**
 * The owner's write block on their own tie page (#3957).
 *
 * The rules under test are the ones a reviewer would otherwise have to take on trust:
 * awareness only ever moves forward, a label is never deleted, and a former label has
 * no doors left to open.
 */
import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LabelsAndAp } from '../LabelsAndAp';
import { makeLabel, makeTie, TYPES } from './fixtures';

const declare = vi.fn();
const shift = vi.fn();
const end = vi.fn();
const awareness = vi.fn();
const allocation = vi.fn();

vi.mock('@/relationships/queries', () => ({
  useRelationshipTypes: () => ({ data: TYPES, isLoading: false }),
  useDeclareLabel: () => ({ mutate: declare, isPending: false }),
  useShiftLabel: () => ({ mutate: shift, isPending: false }),
  useEndLabel: () => ({ mutate: end, isPending: false }),
  useAdvanceAwareness: () => ({ mutate: awareness, isPending: false }),
  useSetTieAllocation: () => ({ mutate: allocation, isPending: false }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

function renderBlock(tie = makeTie()) {
  return render(<LabelsAndAp tie={tie} targetPersonaId={91} />);
}

function labelRow(name: string) {
  return screen.getByText(name).closest('.refsheet-entry') as HTMLElement;
}

describe('LabelsAndAp', () => {
  it('names the other side without opening a second heading, and prefills the AP set', () => {
    renderBlock();
    expect(screen.getByText('Corvin Ashe')).toBeInTheDocument();
    // The plate above already carries them in an h2; a second one at the same weight
    // reads as a duplicate to anyone hearing the page.
    expect(screen.queryByRole('heading', { name: 'Corvin Ashe' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('AP this week')).toHaveValue('9');
  });

  it('sends the AP the owner typed for this tie', () => {
    renderBlock();
    fireEvent.change(screen.getByLabelText('AP this week'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: 'Keep' }));
    expect(allocation).toHaveBeenCalledWith(
      { target_persona_id: 91, ap_amount: 12 },
      expect.anything()
    );
  });

  it('marks a label and says what it replaced, without printing a real-world date', () => {
    renderBlock();
    const lover = labelRow('Lover');
    expect(within(lover).getByText('Clandestine')).toBeInTheDocument();
    expect(within(lover).getByText('Replaced Friend')).toBeInTheDocument();
    expect(within(labelRow('Enemy')).getByText('Private')).toBeInTheDocument();
    // `since` is a posting timestamp, not an IC one — it has no business on an IC label.
    expect(screen.queryByText(/since /)).not.toBeInTheDocument();
    expect(screen.queryByText(/20\d\d/)).not.toBeInTheDocument();
  });

  it('offers only the awareness moves that go forward', () => {
    renderBlock();
    const lover = labelRow('Lover');
    expect(within(lover).getByRole('button', { name: 'Make public' })).toBeInTheDocument();
    expect(
      within(lover).queryByRole('button', { name: 'Make clandestine' })
    ).not.toBeInTheDocument();

    const enemy = labelRow('Enemy');
    expect(within(enemy).getByRole('button', { name: 'Make clandestine' })).toBeInTheDocument();
    expect(within(enemy).getByRole('button', { name: 'Make public' })).toBeInTheDocument();
  });

  it('gives a public label no awareness door at all', () => {
    renderBlock(makeTie({ labels: [makeLabel({ id: 1, awareness: 'public' })] }));
    const lover = labelRow('Lover');
    expect(within(lover).queryByRole('button', { name: /^Make / })).not.toBeInTheDocument();
    // A public label carries no marker at all, so it gets no aside either.
    expect(within(lover).queryByText(/Private|Clandestine|former/)).not.toBeInTheDocument();
  });

  it('moves a label forward when the door is used', () => {
    renderBlock();
    fireEvent.click(within(labelRow('Enemy')).getByRole('button', { name: 'Make clandestine' }));
    expect(awareness).toHaveBeenCalledWith(
      { label_id: 2, awareness: 'clandestine' },
      expect.anything()
    );
  });

  it('confirms before ending a label, and never deletes one', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderBlock();
    fireEvent.click(within(labelRow('Lover')).getByRole('button', { name: 'End' }));
    expect(confirm).toHaveBeenCalledWith('End Lover?');
    expect(end).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(within(labelRow('Lover')).getByRole('button', { name: 'End' }));
    expect(end).toHaveBeenCalledWith({ label_id: 1 }, expect.anything());
    confirm.mockRestore();
  });

  it('leaves a former label with no doors, and says only that it is former', () => {
    renderBlock();
    const former = labelRow('Friend · former');
    expect(within(former).queryByRole('button')).not.toBeInTheDocument();
    expect(within(former).getByText('former')).toBeInTheDocument();
    // The awareness of an ended label is not a live fact.
    expect(within(former).queryByText(/^Private$|^Clandestine$/)).not.toBeInTheDocument();
  });

  it('opens the shift block from the Change door on a label', () => {
    renderBlock();
    fireEvent.click(within(labelRow('Lover')).getByRole('button', { name: 'Change' }));
    expect(screen.getByText('Relationship Shift')).toBeInTheDocument();
    expect(screen.getByText('Lover becomes')).toBeInTheDocument();
  });

  it('opens the picker behind Declare another, without the types already held', () => {
    renderBlock();
    const door = screen.getByRole('button', { name: 'Declare another' });
    expect(door).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(door);
    expect(door).toHaveAttribute('aria-expanded', 'true');
    // Lover is open on this tie, so it is not offered again; Friend has ended, so it is.
    expect(screen.queryByRole('button', { name: /^Lover/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Friend/ })).toBeInTheDocument();
    expect(screen.getByText('Teaching')).toBeInTheDocument();
    expect(screen.getByText('with Student')).toBeInTheDocument();
  });

  it('declares at private unless the owner says otherwise', () => {
    renderBlock();
    fireEvent.click(screen.getByRole('button', { name: 'Declare another' }));
    fireEvent.click(screen.getByRole('button', { name: /^Mentor/ }));
    expect(screen.getByRole('button', { name: 'Private' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Declare' }));
    expect(declare).toHaveBeenCalledWith(
      { target_persona_id: 91, type_id: 11, awareness: 'private' },
      expect.anything()
    );
  });

  it('will not let a write fire before the target persona has resolved', () => {
    render(<LabelsAndAp tie={makeTie()} targetPersonaId={null} />);
    expect(screen.getByRole('button', { name: 'Keep' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Declare another' }));
    fireEvent.click(screen.getByRole('button', { name: /^Mentor/ }));
    expect(screen.getByRole('button', { name: 'Declare' })).toBeDisabled();
    expect(allocation).not.toHaveBeenCalled();
    expect(declare).not.toHaveBeenCalled();
  });

  it('offers the shift select grouped, without the types already held open', () => {
    renderBlock();
    fireEvent.click(within(labelRow('Lover')).getByRole('button', { name: 'Change' }));
    const select = screen.getByRole('combobox', { name: 'Lover becomes' });
    const groups = within(select).getAllByRole('group');
    expect(groups.map((group) => group.getAttribute('label'))).toEqual(['Company', 'Teaching']);
    // Lover is this label's own type and Enemy is held open, so neither is on offer;
    // Friend has ended, so it is.
    expect(within(select).getByRole('option', { name: 'Friend' })).toBeInTheDocument();
    expect(within(select).queryByRole('option', { name: 'Lover' })).not.toBeInTheDocument();
  });
});
