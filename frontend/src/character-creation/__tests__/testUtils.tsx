/**
 * Character Creation Test Utilities
 *
 * Enhanced render utilities and test helpers for character creation tests.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
import { Provider } from 'react-redux';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { configureStore } from '@reduxjs/toolkit';
import { authSlice } from '@/store/authSlice';
import type { AccountData } from '@/evennia_replacements/types';
import { mockPlayerAccount } from './mocks';

// =============================================================================
// Store Setup
// =============================================================================

interface AuthState {
  account: AccountData | null;
}

/**
 * Create a test store with optional preloaded state
 */
export function createTestStore(preloadedState?: { auth?: AuthState }) {
  return configureStore({
    reducer: {
      auth: authSlice.reducer,
    },
    preloadedState,
  });
}

// =============================================================================
// Query Client Setup
// =============================================================================

/**
 * Create a fresh QueryClient for testing
 * Disables retries and caching for predictable test behavior
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

// =============================================================================
// Render Utilities
// =============================================================================

export interface RenderWithProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  /** Initial route entries for MemoryRouter */
  initialEntries?: string[];
  /** Account data to use in auth state */
  account?: AccountData | null;
  /** Custom preloaded state */
  preloadedState?: { auth?: AuthState };
  /** Custom QueryClient instance */
  queryClient?: QueryClient;
}

/**
 * Render a component with all necessary providers for character creation tests
 */
export function renderWithCharacterCreationProviders(
  ui: ReactNode,
  options: RenderWithProvidersOptions = {}
) {
  const {
    initialEntries = ['/character-creation'],
    account = mockPlayerAccount,
    preloadedState,
    queryClient = createTestQueryClient(),
    ...renderOptions
  } = options;

  // Build auth state from account
  const authState: AuthState = {
    account,
  };

  // Merge with any provided preloaded state
  const finalPreloadedState = {
    auth: authState,
    ...preloadedState,
  };

  const store = createTestStore(finalPreloadedState);

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter
            initialEntries={initialEntries}
            future={{
              v7_startTransition: true,
              v7_relativeSplatPath: true,
            }}
          >
            {children}
          </MemoryRouter>
        </QueryClientProvider>
      </Provider>
    );
  }

  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    store,
    queryClient,
  };
}

// =============================================================================
// Query Mocking Utilities
// =============================================================================

/**
 * Set up query data directly in the query client cache
 * Useful for testing components that depend on queries without making API calls
 */
export function seedQueryData<T>(queryClient: QueryClient, queryKey: readonly unknown[], data: T) {
  // Set both the data and mark the query as fresh to prevent refetching
  queryClient.setQueryData(queryKey, data);
  // Ensure the data is considered fresh by setting a high stale time
  queryClient.setQueryDefaults(queryKey, {
    staleTime: Infinity,
  });
}

/**
 * Helper to seed common character creation queries
 */
export function seedCharacterCreationQueries(
  queryClient: QueryClient,
  options: {
    startingAreas?: import('../types').StartingArea[];
    species?: import('../types').Species[];
    families?: import('../types').Family[];
    draft?: import('../types').CharacterDraft | null;
    canCreate?: { can_create: boolean; reason: string };
  }
) {
  // Import keys dynamically to avoid circular dependencies
  const characterCreationKeys = {
    all: ['character-creation'] as const,
    startingAreas: () => [...characterCreationKeys.all, 'starting-areas'] as const,
    species: (areaId: number, heritageId?: number) =>
      [...characterCreationKeys.all, 'species', areaId, heritageId] as const,
    families: (areaId: number) => [...characterCreationKeys.all, 'families', areaId] as const,
    draft: () => [...characterCreationKeys.all, 'draft'] as const,
    canCreate: () => [...characterCreationKeys.all, 'can-create'] as const,
  };

  if (options.startingAreas !== undefined) {
    seedQueryData(queryClient, characterCreationKeys.startingAreas(), options.startingAreas);
  }

  if (options.draft !== undefined) {
    seedQueryData(queryClient, characterCreationKeys.draft(), options.draft);
  }

  if (options.canCreate !== undefined) {
    seedQueryData(queryClient, characterCreationKeys.canCreate(), options.canCreate);
  }

  // Species and families need area ID, so they're handled separately when needed
}

// =============================================================================
// Wait Utilities
// =============================================================================

/**
 * Wait for loading states to resolve
 */
export async function waitForLoadingToFinish() {
  // Small delay to allow React Query to settle
  await new Promise((resolve) => setTimeout(resolve, 0));
}

// =============================================================================
// Assertion Helpers
// =============================================================================

/**
 * Assert that an element has the "selected" visual state
 * (usually indicated by ring-2 ring-primary class)
 */
export function expectSelected(element: HTMLElement) {
  expect(element.className).toMatch(/ring-2/);
  expect(element.className).toMatch(/ring-primary/);
}

/**
 * Assert that an element does NOT have the "selected" visual state
 */
export function expectNotSelected(element: HTMLElement) {
  expect(element.className).not.toMatch(/ring-2.*ring-primary/);
}
