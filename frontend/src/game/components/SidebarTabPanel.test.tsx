/**
 * SidebarTabPanel tests.
 *
 * The nine reference sections live under an "Actions" fold at the foot of the
 * room view (#3856 PR 3): the fold is open by default, a section opens in
 * place of the room with a way back, the sections mount lazily, and the
 * component stays controlled by `GamePage` (#3761).
 */

import { useState } from 'react';
import type { ComponentProps } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { SidebarTabPanel } from './SidebarTabPanel';

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
  it('shows the room with the Actions fold open below it, eight sections in a grid', () => {
    render(
      <SidebarTabPanel
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div>Events</div>}
        activeTab="room"
        onTabChange={vi.fn()}
      />
    );
    expect(screen.getByText('Room contents')).toBeInTheDocument();
    const fold = screen.getByTestId('actions-fold') as HTMLDetailsElement;
    expect(fold.open).toBe(true);
    expect(within(fold).getByText('Actions')).toBeInTheDocument();
    const names = within(fold)
      .getAllByRole('button')
      .map((button) => button.textContent?.trim());
    expect(names).toEqual([
      'Who',
      'Stories',
      'Events',
      'Codex',
      'Status',
      'Items',
      'Journal',
      'Travel',
    ]);
    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
  });

  it('a section opens in place of the room with a way back that names the room', async () => {
    const user = userEvent.setup();
    render(
      <ControlledSidebarTabPanel
        roomTabLabel="Quiet courtyard"
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div data-testid="events-mount">Events mounted</div>}
      />
    );
    expect(screen.queryByTestId('events-mount')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Events' }));
    expect(screen.getByTestId('events-mount')).toBeInTheDocument();
    expect(screen.queryByText('Room contents')).not.toBeInTheDocument();
    const back = screen.getByRole('button', { name: /Quiet courtyard/ });
    expect(back).toHaveTextContent(/←\s*Quiet courtyard/);
    // The fold stays under the section, so another section is one press away,
    // and the open one is marked.
    const fold = screen.getByTestId('actions-fold');
    expect(within(fold).getByRole('button', { name: 'Events' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await user.click(within(fold).getByRole('button', { name: 'Who' }));
    expect(screen.getByText('No presence to show.')).toBeInTheDocument();
    expect(screen.queryByTestId('events-mount')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Quiet courtyard/ }));
    expect(screen.getByText('Room contents')).toBeInTheDocument();
    expect(screen.queryByTestId('events-mount')).not.toBeInTheDocument();
  });

  it('the way back names the focused subject when the room tab label is overridden', () => {
    const longName = 'A Very Long Character Name That Should Not Blow Up The Panel';
    render(
      <SidebarTabPanel
        roomTabLabel={longName}
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div>Events</div>}
        activeTab="who"
        onTabChange={vi.fn()}
        presencePanel={<div>Who is here</div>}
      />
    );
    const back = screen.getByRole('button', { name: new RegExp(longName) });
    expect(back.getAttribute('title')).toBe(longName);
    expect(back.querySelector('span.truncate')).not.toBeNull();
  });

  it('renders the section passed via activeTab, not internal state', () => {
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
    await user.click(screen.getByRole('button', { name: 'Who' }));
    expect(onTabChange).toHaveBeenCalledWith('who');
  });

  it('the fold closes and opens on its summary, and its sections stay reachable', async () => {
    const user = userEvent.setup();
    render(
      <ControlledSidebarTabPanel
        roomPanel={<div>Room contents</div>}
        eventsPanel={<div>Events</div>}
        statusPanel={<div>Status here</div>}
      />
    );
    await user.click(screen.getByText('Actions'));
    expect((screen.getByTestId('actions-fold') as HTMLDetailsElement).open).toBe(false);
    // The sections stay reachable even folded: the grid is only hidden.
    await user.click(screen.getByText('Actions'));
    await user.click(screen.getByRole('button', { name: 'Status' }));
    expect(screen.getByText('Status here')).toBeInTheDocument();
  });
});
