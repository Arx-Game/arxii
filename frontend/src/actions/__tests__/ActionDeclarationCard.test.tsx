/**
 * Tests for ActionDeclarationCard — Phase 5.1 skeleton tests.
 * Task 5.2 and 5.3 tests added in subsequent commits.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import type { ReactNode } from 'react';
import { ActionDeclarationCard } from '../ActionDeclarationCard';
import type { ActionContext } from '../types';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function emptyContext(overrides?: Partial<ActionContext>): ActionContext {
  return {
    slot: 'focused',
    effort: 'MEDIUM',
    strainCommitment: 0,
    ...overrides,
  };
}

describe('ActionDeclarationCard — Task 5.1 skeleton', () => {
  it('renders with empty context (no technique picked yet)', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/pick a technique/i)).toBeInTheDocument();
  });

  it('renders all section headings', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/^technique$/i)).toBeInTheDocument();
    expect(screen.getByText(/^target$/i)).toBeInTheDocument();
    expect(screen.getByText(/^effort$/i)).toBeInTheDocument();
    expect(screen.getByText(/^cost$/i)).toBeInTheDocument();
    expect(screen.getByText(/thread pulls/i)).toBeInTheDocument();
  });

  it('renders the slot name in the header', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        actionContext={emptyContext({ slot: 'passive-physical' })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/passive physical/i)).toBeInTheDocument();
  });
});
