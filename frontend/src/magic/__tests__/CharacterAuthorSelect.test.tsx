import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import type { MyRosterEntry } from '@/roster/types';
import { CharacterAuthorSelect } from '../components/CharacterAuthorSelect';

function makeEntry(overrides: Partial<MyRosterEntry> & { character_id: number }): MyRosterEntry {
  return {
    id: overrides.character_id,
    name: `Character ${overrides.character_id}`,
    profile_picture_url: null,
    primary_persona_id: null,
    active_persona_id: null,
    ...overrides,
  };
}

describe('CharacterAuthorSelect', () => {
  it('renders nothing when the account plays no characters', () => {
    const { container } = render(
      <CharacterAuthorSelect entries={[]} value={null} onChange={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for a single-character account (zero-click)', () => {
    const entries = [makeEntry({ character_id: 7, name: 'Solo' })];
    const { container } = render(
      <CharacterAuthorSelect entries={entries} value={7} onChange={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a selector with one option per character when the account has >1', () => {
    const entries = [
      makeEntry({ character_id: 1, name: 'Alice' }),
      makeEntry({ character_id: 2, name: 'Bob' }),
    ];
    render(<CharacterAuthorSelect entries={entries} value={1} onChange={vi.fn()} />);
    // The trigger reflects the selected character's name.
    expect(screen.getByRole('combobox')).toHaveTextContent('Alice');
  });

  it('emits the chosen character_id when a different character is picked', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const entries = [
      makeEntry({ character_id: 1, name: 'Alice' }),
      makeEntry({ character_id: 2, name: 'Bob' }),
    ];
    render(<CharacterAuthorSelect entries={entries} value={1} onChange={onChange} />);

    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: 'Bob' }));

    expect(onChange).toHaveBeenCalledWith(2);
  });
});
