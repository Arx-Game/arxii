import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NarratedEventTag } from '../NarratedEventTag';

const crossing = {
  prompt_id: 1,
  kind: 'crossing' as const,
  kind_label: 'Crossing',
  subject_name: 'Rowan Ashcombe',
  subject_persona_id: 30,
};

describe('NarratedEventTag', () => {
  it('marks a room line as part of the event', () => {
    render(<NarratedEventTag narrates={crossing} receiverPersonaIds={[]} />);
    expect(screen.getByText("✦ part of Rowan Ashcombe's Crossing")).toBeInTheDocument();
  });

  // Ruling R11-1: the full displayed subject name, not its first word (the
  // demo used "visible only to Rowan"; see the component's own docstring).
  it('marks a private vision as visible only to its player, by full name', () => {
    render(<NarratedEventTag narrates={crossing} receiverPersonaIds={[30]} />);
    expect(
      screen.getByText("✦ part of Rowan Ashcombe's Crossing · visible only to Rowan Ashcombe")
    ).toBeInTheDocument();
  });

  it('renders nothing for an ordinary row', () => {
    const { container } = render(<NarratedEventTag narrates={null} receiverPersonaIds={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders "a {kind_label}" for a subject-less event (a stake outcome)', () => {
    const stakeOutcome = {
      prompt_id: 2,
      kind: 'stake_outcome' as const,
      kind_label: 'Stake outcome',
    };
    render(<NarratedEventTag narrates={stakeOutcome} receiverPersonaIds={[]} />);
    expect(screen.getByText('✦ part of a Stake outcome')).toBeInTheDocument();
  });

  it('does not add the private suffix when receivers are more than just the subject', () => {
    render(<NarratedEventTag narrates={crossing} receiverPersonaIds={[30, 31]} />);
    expect(screen.getByText("✦ part of Rowan Ashcombe's Crossing")).toBeInTheDocument();
  });

  // Fix round 1, item 12: a persona id with no resolved name must not produce
  // a suffix naming nobody ("visible only to ").
  it('does not add the private suffix when subject_name is empty, even if the persona id matches', () => {
    const noName = { ...crossing, subject_name: '' };
    render(<NarratedEventTag narrates={noName} receiverPersonaIds={[30]} />);
    expect(screen.getByText('✦ part of a Crossing')).toBeInTheDocument();
    expect(screen.queryByText(/visible only to/)).toBeNull();
  });
});
