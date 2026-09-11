import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PlaySidebar, type SidebarMode } from './PlaySidebar';
import type { ComponentProps } from 'react';

vi.mock('./HistoryNavigator', () => ({
  HistoryNavigator: () => <div data-testid="history-navigator">History content</div>,
}));
vi.mock('./ConversationSidebar', () => ({
  ConversationSidebar: () => <div data-testid="conversation-sidebar">Conversations content</div>,
}));
vi.mock('./DisplaySettings', () => ({ DisplaySettings: () => null }));

/**
 * `PlaySidebar` is now a controlled component (#3761) — `GamePage` owns
 * `mode`. This harness mirrors that ownership for tests that exercise
 * click-driven mode switching, so the assertions about mounted/hidden
 * bodies and per-mode scroll memory keep testing real behavior instead of
 * an inert mock.
 */
function ControlledPlaySidebar(
  props: Omit<ComponentProps<typeof PlaySidebar>, 'mode' | 'onModeChange'> & {
    initialMode?: SidebarMode;
  }
) {
  const { initialMode, ...rest } = props;
  const [mode, setMode] = useState<SidebarMode>(initialMode ?? 'here');
  return <PlaySidebar {...rest} mode={mode} onModeChange={setMode} />;
}

describe('PlaySidebar', () => {
  it('keeps History mounted (hidden, not removed) when switching to Here', async () => {
    const user = userEvent.setup();
    render(<ControlledPlaySidebar here={<div>Here content</div>} onThreadClick={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: /history/i }));
    expect(screen.getByTestId('history-navigator')).toBeVisible();
    await user.click(screen.getByRole('button', { name: /here/i }));
    // History's DOM node still exists (mounted), just not visible — proves
    // its internal state (scroll position, in-flight search) survives.
    expect(screen.getByTestId('history-navigator')).not.toBeVisible();
  });

  it("remembers each mode's own scroll position across a switch away and back", async () => {
    const user = userEvent.setup();
    render(<ControlledPlaySidebar here={<div>Here content</div>} onThreadClick={vi.fn()} />);
    const scrollEl = screen.getByTestId('play-sidebar-scroll');

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

  it('renders the mode passed via the mode prop, not internal state', () => {
    const onModeChange = vi.fn();
    render(
      <PlaySidebar
        here={<div>here content</div>}
        mode="conversations"
        onModeChange={onModeChange}
        onThreadClick={vi.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /conversations/i })).toHaveAttribute(
      'aria-current',
      'page'
    );
  });

  it('calls onModeChange instead of managing mode internally', async () => {
    const user = userEvent.setup();
    const onModeChange = vi.fn();
    render(
      <PlaySidebar
        here={<div>here content</div>}
        mode="here"
        onModeChange={onModeChange}
        onThreadClick={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /history/i }));
    expect(onModeChange).toHaveBeenCalledWith('history');
  });
});
