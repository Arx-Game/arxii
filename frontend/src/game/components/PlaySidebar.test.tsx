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
});
