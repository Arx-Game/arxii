import { act, fireEvent, render, screen } from '@testing-library/react';
import { Provider } from 'react-redux';
import { beforeEach, describe, expect, it } from 'vitest';
import { store } from '@/store/store';
import { addConsoleLine, resetGame, startSession } from '@/store/gameSlice';
import { StaffConsole } from './StaffConsole';

function renderConsole(active = false) {
  return render(
    <Provider store={store}>
      <StaffConsole character="Aria" active={active} />
    </Provider>
  );
}

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
