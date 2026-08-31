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

  it('renders caller-supplied right-side controls', () => {
    render(
      <FolioCrumb entries={entries} onSelect={vi.fn()}>
        <button type="button">⌕ find a room</button>
      </FolioCrumb>
    );
    expect(screen.getByText('⌕ find a room')).toBeInTheDocument();
  });
});
