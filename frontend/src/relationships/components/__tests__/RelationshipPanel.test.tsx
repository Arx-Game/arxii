/**
 * RelationshipPanel tests (#2159)
 *
 * LIGHT: one test — the own-vs-foreign branching renders the right arm.
 * `OwnRelationshipsList`/`ForeignRelationshipTimeline` each own their own
 * query/rendering logic and are mocked out here.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { RelationshipPanel } from '../RelationshipPanel';

vi.mock('../OwnRelationshipsList', () => ({
  OwnRelationshipsList: ({ characterSheetId }: { characterSheetId?: number }) => (
    <div data-testid="own-relationships-list">own:{characterSheetId}</div>
  ),
}));

vi.mock('../ForeignRelationshipTimeline', () => ({
  ForeignRelationshipTimeline: ({ characterSheetId }: { characterSheetId?: number }) => (
    <div data-testid="foreign-relationship-timeline">foreign:{characterSheetId}</div>
  ),
}));

describe('RelationshipPanel', () => {
  it('branches on isMyCharacter: own sheet renders OwnRelationshipsList, foreign renders ForeignRelationshipTimeline', () => {
    const { rerender } = render(<RelationshipPanel characterSheetId={42} isMyCharacter />);

    expect(screen.getByTestId('own-relationships-list')).toBeInTheDocument();
    expect(screen.queryByTestId('foreign-relationship-timeline')).not.toBeInTheDocument();

    rerender(<RelationshipPanel characterSheetId={42} isMyCharacter={false} />);

    expect(screen.getByTestId('foreign-relationship-timeline')).toBeInTheDocument();
    expect(screen.queryByTestId('own-relationships-list')).not.toBeInTheDocument();
  });
});
