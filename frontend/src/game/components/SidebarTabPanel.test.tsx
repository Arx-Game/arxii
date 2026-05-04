/**
 * SidebarTabPanel tests.
 *
 * Verifies the tab-label override (Task 9) and the lazy-mount behavior
 * for the events / codex tabs.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { SidebarTabPanel } from './SidebarTabPanel';

describe('SidebarTabPanel', () => {
  it('defaults the room tab label to "Room" when no override is provided', () => {
    render(
      <SidebarTabPanel roomPanel={<div>Room contents</div>} eventsPanel={<div>Events</div>} />
    );
    expect(screen.getByRole('tab', { name: /room/i })).toBeInTheDocument();
  });

  it('uses roomTabLabel when provided', () => {
    render(
      <SidebarTabPanel
        roomTabLabel="Sera Whitewater"
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div>Events</div>}
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
      <SidebarTabPanel
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div data-testid="events-mount">Events mounted</div>}
      />
    );
    expect(screen.queryByTestId('events-mount')).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /events/i }));
    expect(screen.getByTestId('events-mount')).toBeInTheDocument();
  });
});
