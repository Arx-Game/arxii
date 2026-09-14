import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CharactersList } from './CharactersList';

const others = [
  { dbref: '#100', name: 'Alice', thumbnail_url: null, commands: [] },
  { dbref: '#101', name: 'Bob', thumbnail_url: null, commands: [] },
];

describe('CharactersList "you" row (#3856)', () => {
  it('lists the viewer first, tagged you, and counts them among the characters', () => {
    render(
      <CharactersList
        characters={others}
        viewer={{ name: 'Hero', thumbnailUrl: null }}
        onViewerClick={vi.fn()}
      />
    );

    expect(screen.getByText('Characters (3)')).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem');
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining('Hero'),
      expect.stringContaining('Alice'),
      expect.stringContaining('Bob'),
    ]);
    expect(within(rows[0]).getByText('you')).toBeInTheDocument();
  });

  it('clicking the viewer row calls onViewerClick, never onCharacterClick', () => {
    const onViewerClick = vi.fn();
    const onCharacterClick = vi.fn();
    render(
      <CharactersList
        characters={others}
        viewer={{ name: 'Hero', thumbnailUrl: null }}
        onViewerClick={onViewerClick}
        onCharacterClick={onCharacterClick}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /hero/i }));

    expect(onViewerClick).toHaveBeenCalledTimes(1);
    expect(onCharacterClick).not.toHaveBeenCalled();
  });

  it('still says nobody else is here below the viewer when the room is otherwise empty', () => {
    render(<CharactersList characters={[]} viewer={{ name: 'Hero', thumbnailUrl: null }} />);

    expect(screen.getByText('Characters (1)')).toBeInTheDocument();
    expect(screen.getByText('Hero')).toBeInTheDocument();
    expect(screen.getByText('Nobody else here.')).toBeInTheDocument();
  });

  it('renders as before when no viewer is supplied', () => {
    render(<CharactersList characters={others} />);

    expect(screen.getByText('Characters (2)')).toBeInTheDocument();
    expect(screen.queryByText('you')).not.toBeInTheDocument();
  });
});
