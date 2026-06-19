// frontend/src/magic/__tests__/MagicProgressionPage.pathIntent.test.tsx
/** Verifies MagicProgressionPage mounts the PathIntentCard for the active character. */
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';

vi.mock('@/store/hooks', () => ({ useAppSelector: () => 'Ariel' }));
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({ data: [{ name: 'Ariel', character_id: 55 }] }),
}));
vi.mock('../magicProgressionQueries', () => ({
  useMagicProgression: () => ({ data: { stages: [] }, isLoading: false, isError: false }),
}));
vi.mock('../components/PathIntentCard', () => ({
  PathIntentCard: ({ characterId }: { characterId: number }) => (
    <div data-testid="mock-path-intent-card">{characterId}</div>
  ),
}));

import { MagicProgressionPage } from '../pages/MagicProgressionPage';

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

it('mounts PathIntentCard with the resolved character id', () => {
  render(<MagicProgressionPage />, { wrapper: createWrapper() });
  expect(screen.getByTestId('mock-path-intent-card')).toHaveTextContent('55');
});
