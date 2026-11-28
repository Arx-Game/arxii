/**
 * Tests for ActMarkChips (#5327): a chip for each resonance a pose marked, struck through with
 * who undid the reward once it is undone, and "Undo reward" only where the server says the
 * viewer may.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Interaction, ActMark } from '../../types';

const mockUndo = vi.fn();
let undoState: { isPending: boolean; error: Error | null } = { isPending: false, error: null };

vi.mock('../../queries', () => ({
  useUndoResonanceGrant: (_sceneId: string) => ({ mutate: mockUndo, ...undoState }),
}));

import { ActMarkChips } from '../ActMarkChips';

function makeMark(overrides: Partial<ActMark> = {}): ActMark {
  return {
    grant_id: 4,
    resonance_id: 2,
    resonance_name: 'Mercy',
    act_label: 'Frightened the child',
    undone: false,
    undone_by: null,
    can_undo: false,
    ...overrides,
  };
}

function makeInteraction(marks: ActMark[] | undefined): Interaction {
  return {
    id: 1,
    persona: { id: 10, name: 'Daven' },
    content: 'Daven catches the child by the collar.',
    mode: 'pose',
    visibility: 'default',
    timestamp: '2026-01-01T00:00:00Z',
    scene: 1,
    reactions: [],
    is_favorited: false,
    place: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
    pose_kind: 'standard',
    endorsee_sheet_id: null,
    endorsable_resonances: [],
    act_marks: marks,
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
  };
}

describe('ActMarkChips', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    undoState = { isPending: false, error: null };
  });

  it('renders nothing for a pose with no marks', () => {
    const { container } = render(
      <ActMarkChips interaction={makeInteraction(undefined)} sceneId="1" />
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows the resonance and the act it points at, with no Undo for an ordinary viewer', () => {
    render(<ActMarkChips interaction={makeInteraction([makeMark()])} sceneId="1" />);
    expect(screen.getByTestId('act-mark-4')).toHaveTextContent('Mercy · Frightened the child');
    expect(screen.queryByRole('button', { name: 'Undo reward' })).toBeNull();
  });

  it('offers Undo reward when the server says the viewer may, and undoes that grant', async () => {
    const user = userEvent.setup();
    render(
      <ActMarkChips interaction={makeInteraction([makeMark({ can_undo: true })])} sceneId="1" />
    );
    await user.click(screen.getByRole('button', { name: 'Undo reward' }));
    expect(mockUndo).toHaveBeenCalledWith(4);
  });

  it("strikes an undone chip through and says the scene's GM undid it", () => {
    render(
      <ActMarkChips
        interaction={makeInteraction([makeMark({ undone: true, undone_by: 'gm' })])}
        sceneId="1"
      />
    );
    expect(screen.getByTestId('act-mark-4')).toHaveClass('line-through');
    expect(screen.getByTestId('act-mark-undone')).toHaveTextContent(
      "Reward undone by the scene's GM"
    );
    expect(screen.queryByRole('button', { name: 'Undo reward' })).toBeNull();
  });

  it('says only that the reward was undone when no one is named', () => {
    render(
      <ActMarkChips interaction={makeInteraction([makeMark({ undone: true })])} sceneId="1" />
    );
    expect(screen.getByTestId('act-mark-undone')).toHaveTextContent(/^Reward undone$/);
  });

  it('says staff undid the reward when staff did', () => {
    render(
      <ActMarkChips
        interaction={makeInteraction([makeMark({ undone: true, undone_by: 'staff' })])}
        sceneId="1"
      />
    );
    expect(screen.getByTestId('act-mark-undone')).toHaveTextContent('Reward undone by staff');
  });

  it('shows the refusal when an undo is refused', () => {
    undoState = { isPending: false, error: new Error('That reward was already undone.') };
    render(
      <ActMarkChips interaction={makeInteraction([makeMark({ can_undo: true })])} sceneId="1" />
    );
    expect(screen.getByTestId('undo-reward-error')).toHaveTextContent(
      'That reward was already undone.'
    );
  });

  it('never offers Undo on a read-only line', () => {
    render(
      <ActMarkChips
        interaction={makeInteraction([makeMark({ can_undo: true })])}
        sceneId="1"
        interactive={false}
      />
    );
    expect(screen.queryByRole('button', { name: 'Undo reward' })).toBeNull();
  });
});
