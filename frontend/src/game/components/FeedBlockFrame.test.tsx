import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FeedBlockControlsContext, type FeedBlockControls } from '../feedBlockControls';
import { FeedBlockFrame } from './FeedBlockFrame';

function controls(overrides: Partial<FeedBlockControls> = {}): FeedBlockControls {
  return {
    minimized: new Set(),
    minimize: vi.fn(),
    restore: vi.fn(),
    dismiss: vi.fn(),
    ...overrides,
  };
}

describe('FeedBlockFrame (#3856)', () => {
  it('renders its block plainly with no controls outside a provider (reference views, tests)', () => {
    render(
      <FeedBlockFrame itemKey="i:1" stub="Nyx · 11:29">
        <p>A pose.</p>
      </FeedBlockFrame>
    );
    expect(screen.getByText('A pose.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('offers minimise and dismiss on the block, each acting on this block only', () => {
    const c = controls();
    render(
      <FeedBlockControlsContext.Provider value={c}>
        <FeedBlockFrame itemKey="i:1" stub="Nyx · 11:29">
          <p>A pose.</p>
        </FeedBlockFrame>
      </FeedBlockControlsContext.Provider>
    );
    fireEvent.click(screen.getByRole('button', { name: 'Minimise' }));
    expect(c.minimize).toHaveBeenCalledWith('i:1');
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(c.dismiss).toHaveBeenCalledWith('i:1');
  });

  it('shows a minimised block as a one-line stub that reopens on press', () => {
    const c = controls({ minimized: new Set(['i:1']) });
    render(
      <FeedBlockControlsContext.Provider value={c}>
        <FeedBlockFrame itemKey="i:1" stub="Nyx · 11:29">
          <p>A pose.</p>
        </FeedBlockFrame>
      </FeedBlockControlsContext.Provider>
    );
    expect(screen.queryByText('A pose.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Nyx · 11:29' }));
    expect(c.restore).toHaveBeenCalledWith('i:1');
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(c.dismiss).toHaveBeenCalledWith('i:1');
  });
});
