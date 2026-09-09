import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { GameLayout } from './GameLayout';

describe('GameLayout', () => {
  it('renders one contextual sidebar and narrow-screen pane controls', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <GameLayout
          topBar={<div>top</div>}
          center={<main>story</main>}
          sidebar={<aside>context</aside>}
        />
      </QueryClientProvider>
    );
    expect(screen.getByText('story')).toBeInTheDocument();
    expect(screen.getByText('context')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Story' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sidebar' })).toBeInTheDocument();
  });
});
