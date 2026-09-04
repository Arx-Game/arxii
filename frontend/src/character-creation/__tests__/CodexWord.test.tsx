/**
 * CodexWord (#3540 OOC sweep): links a single in-world term via CodexTerm
 * when an exact-name codex entry exists, and quietly falls back to plain
 * text when it does not (render-or-vanish, no error state).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { codexKeys } from '@/codex/queries';
import { CodexWord } from '../folio/CodexWord';
import { mockCodexEntry } from './fixtures';
import { seedQueryData } from './testUtils';

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
}

describe('CodexWord', () => {
  it('renders a CodexTerm button when the query returns an exact-name match', () => {
    const queryClient = createTestQueryClient();
    seedQueryData(queryClient, codexKeys.entryByName('Gifted'), mockCodexEntry(30));

    render(
      <QueryClientProvider client={queryClient}>
        <CodexWord name="Gifted">Gifted</CodexWord>
      </QueryClientProvider>
    );

    expect(screen.getByRole('button', { name: 'Gifted' })).toBeInTheDocument();
  });

  it('renders plain text when the query returns no match', () => {
    const queryClient = createTestQueryClient();
    seedQueryData(queryClient, codexKeys.entryByName('Glimpse'), null);

    render(
      <QueryClientProvider client={queryClient}>
        <CodexWord name="Glimpse">Glimpse</CodexWord>
      </QueryClientProvider>
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('Glimpse')).toBeInTheDocument();
  });
});
