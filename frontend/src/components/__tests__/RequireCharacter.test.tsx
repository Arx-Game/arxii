/**
 * Tests for RequireCharacter route guard.
 *
 * Verifies that users without a character see a friendly message,
 * and users with a character see the page content.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { RequireCharacter } from '../RequireCharacter';

function createStore(account: unknown) {
  return configureStore({
    reducer: {
      auth: (_state, action) => {
        if (action.type === 'INIT') return { account };
        return { account };
      },
    },
    preloadedState: { auth: { account } },
  });
}

function renderWithStore(ui: React.ReactElement, account: unknown) {
  const store = createStore(account);
  return render(
    <Provider store={store}>
      <MemoryRouter>{ui}</MemoryRouter>
    </Provider>
  );
}

describe('RequireCharacter', () => {
  it('renders children when user has characters', () => {
    const account = {
      id: 1,
      username: 'testuser',
      available_characters: [{ id: 1, name: 'TestChar' }],
    };
    renderWithStore(
      <RequireCharacter>
        <div>Page content</div>
      </RequireCharacter>,
      account
    );
    expect(screen.getByText('Page content')).toBeInTheDocument();
  });

  it('shows friendly message when user has no characters', () => {
    const account = {
      id: 1,
      username: 'testuser',
      available_characters: [],
    };
    renderWithStore(
      <RequireCharacter>
        <div>Page content</div>
      </RequireCharacter>,
      account
    );
    expect(screen.queryByText('Page content')).not.toBeInTheDocument();
    expect(screen.getByText('You need a character first')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /browse the roster/i })).toBeInTheDocument();
  });

  it('shows message when account is null', () => {
    renderWithStore(
      <RequireCharacter>
        <div>Page content</div>
      </RequireCharacter>,
      null
    );
    expect(screen.queryByText('Page content')).not.toBeInTheDocument();
    expect(screen.getByText('You need a character first')).toBeInTheDocument();
  });

  it('shows message when available_characters is undefined', () => {
    const account = { id: 1, username: 'testuser' };
    renderWithStore(
      <RequireCharacter>
        <div>Page content</div>
      </RequireCharacter>,
      account
    );
    expect(screen.getByText('You need a character first')).toBeInTheDocument();
  });
});
