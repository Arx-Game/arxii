import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { SceneHeader } from './SceneHeader';
import type { SceneDetail } from '../types';

const mockUseEncounterForScene = vi.fn();
vi.mock('@/combat/queries', () => ({
  useEncounterForScene: () => mockUseEncounterForScene(),
}));

// Only the fields SceneHeader actually reads are filled in — cast covers the
// rest of SceneDetail's shape, which this test doesn't exercise.
const SCENE = {
  id: 9,
  name: 'Test Scene',
  description: '',
  is_active: true,
  is_owner: false,
  participants: [],
} as unknown as SceneDetail;

function renderWrapped(scene: SceneDetail = SCENE) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }
  return render(<SceneHeader scene={scene} />, { wrapper: Wrapper });
}

describe('SceneHeader combat badge', () => {
  it('shows an In Combat badge when the scene has an active encounter', () => {
    mockUseEncounterForScene.mockReturnValue({ data: { id: 1 }, isLoading: false, isError: false });

    renderWrapped();

    const badge = screen.getByTestId('scene-header-combat-badge');
    expect(badge).toHaveTextContent('In Combat');
    expect(badge.closest('a')).toHaveAttribute('href', '/scenes/9/combat');
  });

  it('does not show the badge when there is no active encounter', () => {
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    renderWrapped();

    expect(screen.queryByTestId('scene-header-combat-badge')).not.toBeInTheDocument();
  });
});
