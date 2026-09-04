import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { useActiveCharacterId } from '../useActiveCharacterId';

// Roster + active-character resolution (mirrors GMAdjudicationPanel.test.tsx)
const mockRosterEntries = vi.fn();
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => mockRosterEntries()),
}));

const mockActiveCharacterName = vi.fn();
vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: mockActiveCharacterName() }, auth: {} })
  ),
}));

function Probe() {
  const characterId = useActiveCharacterId();
  return <span data-testid="probe">{characterId === null ? 'null' : characterId}</span>;
}

describe('useActiveCharacterId', () => {
  it('resolves the character_id of the roster entry matching the active character name', () => {
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
    mockActiveCharacterName.mockReturnValue('GMChar');

    render(<Probe />);

    expect(screen.getByTestId('probe').textContent).toBe('42');
  });

  it('returns null when no roster entry matches the active character name', () => {
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
    mockActiveCharacterName.mockReturnValue('SomeoneElse');

    render(<Probe />);

    expect(screen.getByTestId('probe').textContent).toBe('null');
  });
});
