import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FeedBlockControlsContext, type FeedBlockControls } from '../feedBlockControls';
import { FeedBlockFrame } from './FeedBlockFrame';
import { HOLD_MS } from '../hooks/useLineGestures';

function controls(overrides: Partial<FeedBlockControls> = {}): FeedBlockControls {
  return {
    minimized: new Set(),
    minimize: vi.fn(),
    restore: vi.fn(),
    dismiss: vi.fn(),
    minimizeMany: vi.fn(),
    dismissMany: vi.fn(),
    restoreAll: vi.fn(),
    restoreDismissed: vi.fn(),
    ...overrides,
  };
}

function Block({ c, folded = false }: { c: FeedBlockControls; folded?: boolean }) {
  return (
    <FeedBlockControlsContext.Provider value={folded ? { ...c, minimized: new Set(['i:1']) } : c}>
      <FeedBlockFrame
        itemKey="i:1"
        stub="Nyx · 11:29"
        persona={{ id: 7, name: 'Nyx' }}
        keysOf={(id) => (id === 7 ? ['i:1', 'i:4'] : [])}
        allKeys={() => ['i:1', 'i:2', 'i:4']}
      >
        <span data-pose-avatar>N</span>
        <p>A pose.</p>
      </FeedBlockFrame>
    </FeedBlockControlsContext.Provider>
  );
}

function quickRightClick(el: HTMLElement): void {
  fireEvent.pointerDown(el, { button: 2, clientX: 30, clientY: 20 });
  fireEvent.pointerUp(el, { button: 2 });
}

async function openMenuFromAvatar(): Promise<HTMLElement> {
  fireEvent.pointerDown(screen.getByText('N'), { button: 2, clientX: 5, clientY: 5 });
  return screen.findByRole('menu');
}

describe('FeedBlockFrame (#3856, gestures #4128)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders its block plainly with no controls outside a provider (reference views, tests)', () => {
    render(
      <FeedBlockFrame itemKey="i:1" stub="Nyx · 11:29">
        <p>A pose.</p>
      </FeedBlockFrame>
    );
    expect(screen.getByText('A pose.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    quickRightClick(screen.getByText('A pose.'));
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('puts no buttons on the block', () => {
    render(<Block c={controls()} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('a quick right-click on the text folds the block, and unfolds a folded one', () => {
    const c = controls();
    const { rerender } = render(<Block c={c} />);
    quickRightClick(screen.getByText('A pose.'));
    expect(c.minimize).toHaveBeenCalledWith('i:1');

    rerender(<Block c={c} folded />);
    quickRightClick(screen.getByText('Nyx · 11:29'));
    expect(c.restore).toHaveBeenCalledWith('i:1');
  });

  it('a right-click on the avatar opens the sorting menu, headed by the stub', async () => {
    const c = controls();
    render(<Block c={c} />);
    const menu = await openMenuFromAvatar();
    expect(within(menu).getByText('Nyx · 11:29')).toBeInTheDocument();
    const labels = within(menu)
      .getAllByRole('menuitem')
      .map((el) => el.textContent);
    expect(labels).toEqual([
      'Minimize',
      'Hide',
      'Minimize all from Nyx',
      'Hide all from Nyx',
      'Minimize all',
      'Expand all',
      'Unhide all',
    ]);
    expect(c.minimize).not.toHaveBeenCalled();
  });

  it('each menu item acts on the right keys', async () => {
    const c = controls();
    render(<Block c={c} />);
    const press = async (name: string) => {
      const menu = await openMenuFromAvatar();
      fireEvent.click(within(menu).getByRole('menuitem', { name }));
    };
    await press('Minimize');
    expect(c.minimize).toHaveBeenCalledWith('i:1');
    await press('Hide');
    expect(c.dismiss).toHaveBeenCalledWith('i:1');
    await press('Minimize all from Nyx');
    expect(c.minimizeMany).toHaveBeenCalledWith(['i:1', 'i:4']);
    await press('Hide all from Nyx');
    expect(c.dismissMany).toHaveBeenCalledWith(['i:1', 'i:4']);
    await press('Minimize all');
    expect(c.minimizeMany).toHaveBeenCalledWith(['i:1', 'i:2', 'i:4']);
    await press('Expand all');
    expect(c.restoreAll).toHaveBeenCalled();
    await press('Unhide all');
    expect(c.restoreDismissed).toHaveBeenCalled();
  });

  it('a held right-click on the text opens the same menu without folding', async () => {
    const c = controls();
    render(<Block c={c} />);
    const text = screen.getByText('A pose.');
    fireEvent.pointerDown(text, { button: 2, clientX: 30, clientY: 20 });
    await act(async () => {
      vi.advanceTimersByTime(HOLD_MS);
    });
    fireEvent.pointerUp(text, { button: 2 });
    expect(await screen.findByRole('menu')).toBeInTheDocument();
    expect(c.minimize).not.toHaveBeenCalled();
  });

  it('a folded block reads Expand in its menu and offers no per-character items for a note', async () => {
    const c = controls({ minimized: new Set(['n:n1']) });
    render(
      <FeedBlockControlsContext.Provider value={c}>
        <FeedBlockFrame itemKey="n:n1" stub="Look · 11:30">
          <p>A look.</p>
        </FeedBlockFrame>
      </FeedBlockControlsContext.Provider>
    );
    const stubRow = screen.getByText('Look · 11:30');
    fireEvent.pointerDown(stubRow, { button: 2, clientX: 30, clientY: 20 });
    await act(async () => {
      vi.advanceTimersByTime(HOLD_MS);
    });
    const menu = await screen.findByRole('menu');
    const labels = within(menu)
      .getAllByRole('menuitem')
      .map((el) => el.textContent);
    expect(labels).toEqual(['Expand', 'Hide', 'Minimize all', 'Expand all', 'Unhide all']);
  });

  it('shows a folded block as a one-line stub that reopens on press, with a hide control', () => {
    const c = controls({ minimized: new Set(['i:1']) });
    render(<Block c={c} folded />);
    expect(screen.queryByText('A pose.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Nyx · 11:29' }));
    expect(c.restore).toHaveBeenCalledWith('i:1');
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }));
    expect(c.dismiss).toHaveBeenCalledWith('i:1');
  });
});
