import { ReactNode } from 'react';
import { render } from '@testing-library/react';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { store } from '@/store/store';

/**
 * Render a component wrapped with common providers.
 *
 * @param ui The component to render.
 */
export function renderWithProviders(
  ui: ReactNode,
  { initialEntries }: { initialEntries?: string[] } = {}
) {
  const queryClient = new QueryClient();

  return render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
}
