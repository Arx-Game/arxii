import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PlaySidebar } from './PlaySidebar';

vi.mock('./HistoryNavigator', () => ({
  HistoryNavigator: () => <div data-testid="history-navigator">History content</div>,
}));
vi.mock('./ConversationSidebar', () => ({
  ConversationSidebar: () => <div data-testid="conversation-sidebar">Conversations content</div>,
}));
vi.mock('./DisplaySettings', () => ({ DisplaySettings: () => null }));

describe('PlaySidebar', () => {
  it('keeps History mounted (hidden, not removed) when switching to Here', async () => {
    const user = userEvent.setup();
    render(<PlaySidebar here={<div>Here content</div>} onThreadClick={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /history/i }));
    expect(screen.getByTestId('history-navigator')).toBeVisible();
    await user.click(screen.getByRole('button', { name: /here/i }));
    // History's DOM node still exists (mounted), just not visible — proves
    // its internal state (scroll position, in-flight search) survives.
    expect(screen.getByTestId('history-navigator')).not.toBeVisible();
  });

  it("remembers each mode's own scroll position across a switch away and back", async () => {
    const user = userEvent.setup();
    render(<PlaySidebar here={<div>Here content</div>} onThreadClick={vi.fn()} />);
    const scrollEl = screen.getByTestId('play-sidebar-scroll');

    // jsdom never computes real layout, so scrollHeight/clientHeight are 0 by
    // default — stub them so a non-zero scrollTop assignment is meaningful
    // and so the restoring effect's read-back reflects what was "scrolled".
    Object.defineProperty(scrollEl, 'scrollHeight', { value: 2000, configurable: true });
    Object.defineProperty(scrollEl, 'clientHeight', { value: 200, configurable: true });

    // Start on "Here" (the default mode with no threading prop) and scroll it.
    scrollEl.scrollTop = 400;
    scrollEl.dispatchEvent(new Event('scroll'));

    // Switch to History — its never-visited position defaults to 0, not
    // Here's leftover 400.
    await user.click(screen.getByRole('button', { name: /history/i }));
    expect(scrollEl.scrollTop).toBe(0);

    // Scroll History to a different position.
    scrollEl.scrollTop = 900;
    scrollEl.dispatchEvent(new Event('scroll'));

    // Switch back to Here — its own remembered 400 is restored, not History's
    // 900 and not a reset to 0.
    await user.click(screen.getByRole('button', { name: /here/i }));
    expect(scrollEl.scrollTop).toBe(400);

    // And switching back to History restores ITS remembered 900.
    await user.click(screen.getByRole('button', { name: /history/i }));
    expect(scrollEl.scrollTop).toBe(900);
  });
});
