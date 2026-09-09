import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { FolioCrumb } from '../FolioCrumb';

const entries = [
  { id: 1, name: 'Nitera', level_display: 'World' },
  { id: 2, name: 'Arx', level_display: 'City' },
  { id: 3, name: 'Central Ward', level_display: 'Ward' },
];

describe('FolioCrumb', () => {
  it('renders every ancestor as a clickable button and the current node as bold, inert text', () => {
    render(<FolioCrumb entries={entries} onSelect={vi.fn()} />);

    expect(screen.getAllByTestId('folio-crumb-ancestor')).toHaveLength(2);
    const current = screen.getByTestId('folio-crumb-current');
    expect(current).toHaveTextContent('Central Ward');
    expect(current.tagName).toBe('B');
  });

  it('calls onSelect with the clicked ancestor id, never the current node', async () => {
    const onSelect = vi.fn();
    render(<FolioCrumb entries={entries} onSelect={onSelect} />);

    await userEvent.click(screen.getByText('Nitera'));
    expect(onSelect).toHaveBeenCalledWith(1);

    await userEvent.click(screen.getByText('Arx'));
    expect(onSelect).toHaveBeenCalledWith(2);

    expect(onSelect).not.toHaveBeenCalledWith(3);
  });

  it('shows a level tag beside the current node (and every ancestor that has one)', () => {
    render(<FolioCrumb entries={entries} onSelect={vi.fn()} />);

    const levelTags = screen.getAllByTestId('folio-crumb-level');
    expect(levelTags).toHaveLength(3);
    expect(screen.getByTestId('folio-crumb-current').parentElement).toHaveTextContent('Ward');
    expect(levelTags.map((tag) => tag.textContent)).toEqual(['World', 'City', 'Ward']);
  });

  it('omits the level tag when an entry carries no level_display', () => {
    render(<FolioCrumb entries={[{ id: 1, name: 'Nitera' }]} onSelect={vi.fn()} />);
    expect(screen.queryByTestId('folio-crumb-level')).not.toBeInTheDocument();
  });

  it('offers an insert point only between entries a level can fit between', async () => {
    const onInsertBetween = vi.fn();
    const ladder = [
      { id: 1, name: 'Nitera', level_display: 'World', level: 80 },
      { id: 2, name: 'Arx', level_display: 'City', level: 40 },
      { id: 3, name: 'Central Ward', level_display: 'Ward', level: 30 },
    ];
    render(<FolioCrumb entries={ladder} onSelect={vi.fn()} onInsertBetween={onInsertBetween} />);

    // World ❯ City admits a continent, kingdom or region; City ❯ Ward admits nothing.
    const inserts = screen.getAllByTestId('folio-crumb-insert');
    expect(inserts).toHaveLength(1);
    expect(inserts[0]).toHaveAccessibleName('add a level between Nitera and Arx');

    await userEvent.click(inserts[0]);
    expect(onInsertBetween).toHaveBeenCalledWith(ladder[0], ladder[1]);
  });

  it('a room straight under a city takes a ward, neighborhood or building above it', () => {
    const ladder = [
      { id: 2, name: 'Arx City', level_display: 'City', level: 40 },
      { id: 100, name: 'The City Center', kind: 'room' as const },
    ];
    render(<FolioCrumb entries={ladder} onSelect={vi.fn()} onInsertBetween={vi.fn()} />);
    expect(screen.getByTestId('folio-crumb-insert')).toHaveAccessibleName(
      'add a level between Arx City and The City Center'
    );
  });

  it('shows no insert points when the caller offers no handler', () => {
    const ladder = [
      { id: 1, name: 'Nitera', level_display: 'World', level: 80 },
      { id: 2, name: 'Arx', level_display: 'City', level: 40 },
    ];
    render(<FolioCrumb entries={ladder} onSelect={vi.fn()} />);
    expect(screen.queryByTestId('folio-crumb-insert')).not.toBeInTheDocument();
  });

  it('renders caller-supplied right-side controls', () => {
    render(
      <FolioCrumb entries={entries} onSelect={vi.fn()}>
        <button type="button">⌕ find a room</button>
      </FolioCrumb>
    );
    expect(screen.getByText('⌕ find a room')).toBeInTheDocument();
  });
});
