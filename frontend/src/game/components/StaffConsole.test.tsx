import { act, fireEvent, render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { store } from '@/store/store';
import { addConsoleLine, resetGame, startSession } from '@/store/gameSlice';
import { StaffConsole } from './StaffConsole';

const sendConsole = vi.fn();

function renderConsole(active = false) {
  return render(
    <Provider store={store}>
      <StaffConsole character="Aria" active={active} sendConsole={sendConsole} />
    </Provider>
  );
}

describe('StaffConsole restart (#4001)', () => {
  beforeEach(() => {
    store.dispatch(resetGame());
    store.dispatch(startSession('Aria'));
    sendConsole.mockReset();
  });

  it('asks before restarting, and Cancel sends nothing', () => {
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Console' }));
    fireEvent.click(screen.getByRole('button', { name: 'Restart game' }));
    expect(screen.getByText(/come back/)).toBeInTheDocument();
    expect(sendConsole).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByText(/come back/)).not.toBeInTheDocument();
    expect(sendConsole).not.toHaveBeenCalled();
  });

  it('sends @reboot through the console once confirmed', () => {
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Console' }));
    fireEvent.click(screen.getByRole('button', { name: 'Restart game' }));
    fireEvent.click(screen.getByRole('button', { name: 'Restart for everyone' }));
    expect(sendConsole).toHaveBeenCalledTimes(1);
    expect(sendConsole).toHaveBeenCalledWith('Aria', '@reboot');
    expect(screen.queryByText(/come back/)).not.toBeInTheDocument();
  });
});

describe('StaffConsole (#3857)', () => {
  beforeEach(() => {
    store.dispatch(resetGame());
    store.dispatch(startSession('Aria'));
  });

  it('opens on its control and shows the lines the server said back, newest last', () => {
    store.dispatch(addConsoleLine({ character: 'Aria', content: 'Created room East(#412).' }));
    store.dispatch(addConsoleLine({ character: 'Aria', content: 'Created Exit east(#413).' }));
    renderConsole();
    expect(screen.getByRole('button', { name: 'Console, 2 new' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Console, 2 new' }));
    expect(screen.getByRole('dialog', { name: 'Console' })).toBeInTheDocument();
    const lines = screen.getByTestId('staff-console-lines');
    expect(lines).toHaveTextContent('Created room East(#412).');
    expect(lines).toHaveTextContent('Created Exit east(#413).');
    // Opening marks the lines seen; the control (behind the sheet, so hidden to
    // assistive tech while it is open) drops its count.
    expect(screen.getByRole('button', { name: 'Console', hidden: true })).toBeInTheDocument();
  });

  it('opens itself when a line arrives while Commands mode is active, and Clear empties it', () => {
    renderConsole(true);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    act(() => {
      store.dispatch(
        addConsoleLine({ character: 'Aria', content: "Command 'x' is not available." })
      );
    });
    expect(screen.getByRole('dialog', { name: 'Console' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(screen.getByText('Nothing yet. Pick Commands and type one.')).toBeInTheDocument();
  });

  it('echoes the sent line above its answers, muted, and never counts it as new', () => {
    store.dispatch(addConsoleLine({ character: 'Aria', content: '@dig East', sent: true }));
    renderConsole();
    expect(screen.getByRole('button', { name: 'Console' })).toBeInTheDocument();
    act(() => {
      store.dispatch(addConsoleLine({ character: 'Aria', content: 'Created room East(#412).' }));
    });
    expect(screen.getByRole('button', { name: 'Console, 1 new' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Console, 1 new' }));
    const lines = screen.getByTestId('staff-console-lines');
    const echoed = lines.querySelector('[data-sent]');
    expect(echoed).toHaveTextContent('\u203a @dig East');
    expect(echoed?.nextElementSibling).toHaveTextContent('Created room East(#412).');
  });

  it('sits beside the play surface: no dimming overlay, and the page stays reachable', () => {
    store.dispatch(addConsoleLine({ character: 'Aria', content: 'Teleported.' }));
    renderConsole();
    fireEvent.click(screen.getByRole('button', { name: 'Console, 1 new' }));
    expect(screen.getByRole('dialog', { name: 'Console' })).toBeInTheDocument();
    // The sheet's overlay rule (`bg-background/80 backdrop-blur-sm`) must not
    // reach the page, and the control outside the sheet is not aria-hidden.
    expect(document.querySelector('.backdrop-blur-sm')).toBeNull();
    expect(screen.getByRole('button', { name: 'Console' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('stays closed once closed, until the next line arrives', () => {
    renderConsole(true);
    act(() => {
      store.dispatch(addConsoleLine({ character: 'Aria', content: 'Created room East(#412).' }));
    });
    expect(screen.getByRole('dialog', { name: 'Console' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    act(() => {
      store.dispatch(addConsoleLine({ character: 'Aria', content: 'Created Exit east(#413).' }));
    });
    expect(screen.getByRole('dialog', { name: 'Console' })).toBeInTheDocument();
  });
});
