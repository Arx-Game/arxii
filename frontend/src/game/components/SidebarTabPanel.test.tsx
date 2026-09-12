/**
 * SidebarTabPanel tests.
 *
 * Verifies the tab-label override (Task 9) and the lazy-mount behavior
 * for the events / codex tabs.
 */

import { useState } from 'react';
import type { ComponentProps } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SidebarTabPanel } from './SidebarTabPanel';

/**
 * `SidebarTabPanel` is now a controlled component (#3761) — `GamePage` owns
 * `activeTab`. This harness mirrors that ownership for tests that exercise
 * click-driven tab switching, so the lazy-mount assertions keep testing real
 * behavior instead of an inert mock.
 */
function ControlledSidebarTabPanel(
  props: Omit<ComponentProps<typeof SidebarTabPanel>, 'activeTab' | 'onTabChange'> & {
    initialTab?: string;
  }
) {
  const { initialTab, ...rest } = props;
  const [activeTab, setActiveTab] = useState(initialTab ?? 'room');
  return <SidebarTabPanel {...rest} activeTab={activeTab} onTabChange={setActiveTab} />;
}

describe('SidebarTabPanel', () => {
  it('defaults the room tab label to "Room" when no override is provided', () => {
    render(
      <SidebarTabPanel
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div>Events</div>}
        activeTab="room"
        onTabChange={vi.fn()}
      />
    );
    expect(screen.getByRole('tab', { name: /room/i })).toBeInTheDocument();
  });

  it('uses roomTabLabel when provided', () => {
    render(
      <SidebarTabPanel
        roomTabLabel="Sera Whitewater"
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div>Events</div>}
        activeTab="room"
        onTabChange={vi.fn()}
      />
    );
    expect(screen.getByRole('tab', { name: /sera whitewater/i })).toBeInTheDocument();
  });

  it('truncates long tab labels visually but exposes the full label via title', () => {
    const longName = 'A Very Long Character Name That Should Not Blow Up The Tab';
    render(
      <SidebarTabPanel
        roomTabLabel={longName}
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div>Events</div>}
        activeTab="room"
        onTabChange={vi.fn()}
      />
    );
    const tab = screen.getByRole('tab', { name: new RegExp(longName, 'i') });
    expect(tab.getAttribute('title')).toBe(longName);
    // The label span carries the truncate utility class.
    const span = tab.querySelector('span');
    expect(span).not.toBeNull();
    expect(span?.className).toMatch(/truncate/);
  });

  it('does not mount events panel until its tab is activated', async () => {
    const user = userEvent.setup();
    render(
      <ControlledSidebarTabPanel
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div data-testid="events-mount">Events mounted</div>}
      />
    );
    expect(screen.queryByTestId('events-mount')).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /events/i }));
    expect(screen.getByTestId('events-mount')).toBeInTheDocument();
  });

  it('renders the tab passed via activeTab, not internal state', () => {
    render(
      <SidebarTabPanel
        roomPanel={<div>room</div>}
        eventsPanel={<div>events</div>}
        activeTab="stories"
        onTabChange={vi.fn()}
        storiesPanel={<div data-testid="stories-content">stories!</div>}
      />
    );
    expect(screen.getByTestId('stories-content')).toBeInTheDocument();
  });

  it('calls onTabChange instead of managing activeTab internally', async () => {
    const user = userEvent.setup();
    const onTabChange = vi.fn();
    render(
      <SidebarTabPanel
        roomPanel={<div>room</div>}
        eventsPanel={<div>events</div>}
        activeTab="room"
        onTabChange={onTabChange}
      />
    );
    await user.click(screen.getByRole('tab', { name: /who/i }));
    expect(onTabChange).toHaveBeenCalledWith('who');
  });
});
