/**
 * CodexPage staff line tests (#3775).
 *
 * Staff sees every Codex entry (Task 7's backend change); this line on the
 * page tells them so, so a staff account never mistakes that view for what
 * a player sees.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import { CodexPage } from '../pages/CodexPage';
import { mockAccount, mockStaffAccount } from '@/test/mocks/account';

// Mutable so each test can pick which account `useAccount` returns.
let account = mockAccount;
vi.mock('@/store/hooks', () => ({ useAccount: () => account }));
vi.mock('../queries', () => ({
  useCodexTree: () => ({ data: [], isLoading: false }),
  useCodexSearch: () => ({ data: undefined, isLoading: false }),
}));
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({ data: [] }),
}));

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <CodexPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CodexPage staff line', () => {
  it('shows the staff view line for staff', () => {
    account = mockStaffAccount;
    renderPage();
    expect(screen.getByText(/Staff view: every entry is shown/)).toBeInTheDocument();
  });

  it('hides it for players', () => {
    account = mockAccount;
    renderPage();
    expect(screen.queryByText(/Staff view/)).not.toBeInTheDocument();
  });
});
