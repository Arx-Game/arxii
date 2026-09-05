/**
 * useBrowsingIdentity tests (#3479): resolves `gameSlice.browsingEntryId`
 * against the roster-entries query into `{ entryId, name, entry }`.
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';

const mockBrowsingEntryId = vi.fn();
vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { browsingEntryId: mockBrowsingEntryId() }, auth: {} })
  ),
}));

const mockRosterEntries = vi.fn();
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => mockRosterEntries()),
}));

import { useBrowsingIdentity } from '../useBrowsingIdentity';

function Probe() {
  const { entryId, name, entry } = useBrowsingIdentity();
  return (
    <span data-testid="probe">
      {JSON.stringify({ entryId, name, characterId: entry?.character_id ?? null })}
    </span>
  );
}

describe('useBrowsingIdentity', () => {
  it("returns the stored identity's name and entry", () => {
    mockBrowsingEntryId.mockReturnValue(1);
    mockRosterEntries.mockReturnValue({
      data: [
        { id: 1, name: 'Aria', character_id: 42 },
        { id: 2, name: 'Bianca', character_id: 43 },
      ],
    });

    render(<Probe />);

    expect(screen.getByTestId('probe').textContent).toBe(
      JSON.stringify({ entryId: 1, name: 'Aria', characterId: 42 })
    );
  });

  it('returns a null identity with no browsing entry stored', () => {
    mockBrowsingEntryId.mockReturnValue(null);
    mockRosterEntries.mockReturnValue({ data: [] });

    render(<Probe />);

    expect(screen.getByTestId('probe').textContent).toBe(
      JSON.stringify({ entryId: null, name: null, characterId: null })
    );
  });

  it('returns a null identity while the roster query has not resolved yet', () => {
    mockBrowsingEntryId.mockReturnValue(1);
    mockRosterEntries.mockReturnValue({ data: undefined });

    render(<Probe />);

    expect(screen.getByTestId('probe').textContent).toBe(
      JSON.stringify({ entryId: 1, name: null, characterId: null })
    );
  });
});
