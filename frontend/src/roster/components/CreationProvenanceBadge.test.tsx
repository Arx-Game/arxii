import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CreationProvenanceBadge } from './CreationProvenanceBadge';

describe('CreationProvenanceBadge', () => {
  it('names the table for a GM-created character (#1506)', () => {
    render(
      <CreationProvenanceBadge
        provenance="gm_table"
        display="GM-created (for a table)"
        tableName="The Iron Circle"
      />
    );
    expect(screen.getByText('GM-made · The Iron Circle')).toBeInTheDocument();
  });

  it('marks staff-created characters', () => {
    render(<CreationProvenanceBadge provenance="staff" display="Staff-created" tableName={null} />);
    expect(screen.getByText('Staff-created')).toBeInTheDocument();
  });

  it('falls back to the API label for player-created characters', () => {
    render(
      <CreationProvenanceBadge provenance="player" display="Player-created" tableName={null} />
    );
    expect(screen.getByText('Player-created')).toBeInTheDocument();
  });
});
