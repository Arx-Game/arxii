import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { FeedNote } from '@/hooks/types';
import { FeedNoteBlock } from './FeedNoteBlock';

const note = (kind: FeedNote['kind'], content: string, subject?: string): FeedNote => ({
  id: 'n1',
  kind,
  content,
  ...(subject ? { subject } : {}),
  timestamp: '2026-09-14T22:00:00.000Z',
});

describe('FeedNoteBlock (#3856)', () => {
  it('renders a look with its subject as the title and the appearance as prose', () => {
    render(<FeedNoteBlock note={note('look', 'A tall woman in grey.', 'Aurelia')} />);

    const block = screen.getByTestId('feed-note');
    expect(block).toHaveAttribute('data-kind', 'look');
    expect(screen.getByText('Aurelia')).toBeInTheDocument();
    expect(screen.getByText('A tall woman in grey.')).toBeInTheDocument();
    expect(screen.getByText('A tall woman in grey.')).not.toHaveClass('font-mono');
  });

  it('renders a look without a subject as the body alone', () => {
    render(<FeedNoteBlock note={note('look', 'Rain rests on the stones.')} />);

    expect(screen.getByText('Rain rests on the stones.')).toBeInTheDocument();
    expect(screen.queryByText('undefined')).not.toBeInTheDocument();
  });

  it('marks an error as an alert in the destructive tokens', () => {
    render(<FeedNoteBlock note={note('error', "Command 'lok' is not available.")} />);

    const block = screen.getByRole('alert');
    expect(block).toHaveAttribute('data-kind', 'error');
    expect(block.className).toContain('destructive');
    expect(screen.getByText("Command 'lok' is not available.")).toBeInTheDocument();
  });

  it.each(['item', 'system'] as const)('renders a %s line as a plain boxed note', (kind) => {
    render(<FeedNoteBlock note={note(kind, 'You take the lantern.')} />);

    const block = screen.getByTestId('feed-note');
    expect(block).toHaveAttribute('data-kind', kind);
    expect(block).not.toHaveAttribute('role');
    expect(block.className).not.toContain('destructive');
  });

  it.each(['arrive', 'move', 'ambience'] as const)('renders %s as a bare italic line', (kind) => {
    render(<FeedNoteBlock note={note(kind, 'Corvin arrives from the east.')} />);

    const block = screen.getByTestId('feed-note');
    expect(block).toHaveAttribute('data-kind', kind);
    expect(block.className).toContain('italic');
    expect(block.className).not.toContain('bg-muted');
  });

  it('keeps Evennia colour markup in the body and drops anything unsafe', () => {
    render(
      <FeedNoteBlock
        note={note('item', '<span class="color-010">Lantern</span><img src=x onerror="alert(1)">')}
      />
    );

    const lantern = screen.getByText('Lantern');
    expect(lantern).toHaveClass('text-green-400');
    expect(document.querySelector('img')).not.toHaveAttribute('onerror');
  });
});
