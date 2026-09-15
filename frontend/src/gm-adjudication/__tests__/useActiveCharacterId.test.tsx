import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { useActiveCharacterId } from '../useActiveCharacterId';

// Roster + browsing-identity resolution (mirrors GMAdjudicationPanel.test.tsx)
const mockRosterEntries = vi.fn();
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => mockRosterEntries()),
}));

const mockBrowsingEntryId = vi.fn();
vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { browsingEntryId: mockBrowsingEntryId() }, auth: {} })
  ),
}));

function Probe() {
  const characterId = useActiveCharacterId();
  return <span data-testid="probe">{characterId === null ? 'null' : characterId}</span>;
}

describe('useActiveCharacterId', () => {
  it('resolves the character_id of the roster entry matching the browsing entry id', () => {
    mockRosterEntries.mockReturnValue({
      data: [
        {
          id: 1,
          name: 'GMChar',
          character_id: 42,
          profile_picture_url: null,
          primary_persona_id: null,
          active_persona_id: null,
        },
      ],
    });
    mockBrowsingEntryId.mockReturnValue(1);

    render(<Probe />);

    expect(screen.getByTestId('probe').textContent).toBe('42');
  });

  it('returns null when no roster entry matches the browsing entry id', () => {
    mockRosterEntries.mockReturnValue({
      data: [
        {
          id: 1,
          name: 'GMChar',
          character_id: 42,
          profile_picture_url: null,
          primary_persona_id: null,
          active_persona_id: null,
        },
      ],
    });
    mockBrowsingEntryId.mockReturnValue(2);

    render(<Probe />);

    expect(screen.getByTestId('probe').textContent).toBe('null');
  });
});
