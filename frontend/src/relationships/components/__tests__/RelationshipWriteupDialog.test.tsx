/**
 * RelationshipWriteupDialog (#3575): the payload carries exactly the id for the
 * target kind it was opened with.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const mutate = vi.fn();
vi.mock('../../queries', () => ({
  useRelationshipTracks: () => ({ data: [{ id: 7, name: 'Loyalty' }] }),
  useCreateFirstImpression: () => ({ mutate, isPending: false }),
  useCreateDevelopment: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateCapstone: () => ({ mutate: vi.fn(), isPending: false }),
  useRedistributePoints: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { RelationshipWriteupDialog } from '../RelationshipWriteupDialog';

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText('Points'), { target: { value: '3' } });
  fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'At the gate' } });
  fireEvent.change(screen.getByLabelText('Writeup'), { target: { value: 'It did not flinch.' } });
  fireEvent.submit(screen.getByRole('button', { name: 'Record' }).closest('form')!);
}

describe('RelationshipWriteupDialog target kinds', () => {
  it('sends target_companion_id for a companion target', () => {
    mutate.mockClear();
    render(
      <RelationshipWriteupDialog
        open
        onOpenChange={() => {}}
        mode="impression"
        target={{ kind: 'companion', companionId: 42 }}
        targetName="Ash"
        initialTrackId={7}
      />
    );
    fillAndSubmit();
    expect(mutate).toHaveBeenCalledTimes(1);
    const body = mutate.mock.calls[0][0];
    expect(body.target_companion_id).toBe(42);
    expect(body.target_persona_id).toBeUndefined();
  });

  it('sends target_persona_id for a persona target', () => {
    mutate.mockClear();
    render(
      <RelationshipWriteupDialog
        open
        onOpenChange={() => {}}
        mode="impression"
        target={{ kind: 'persona', personaId: 9 }}
        targetName="Someone"
        initialTrackId={7}
      />
    );
    fillAndSubmit();
    const body = mutate.mock.calls[0][0];
    expect(body.target_persona_id).toBe(9);
    expect(body.target_companion_id).toBeUndefined();
  });
});
