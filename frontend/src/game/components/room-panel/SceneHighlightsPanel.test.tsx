import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/scenes/queries', () => ({
  fetchScene: vi.fn(),
  sceneKeys: { detail: (id: number | string) => ['scene', String(id)] },
}));

// Stub HighlightReel: this test only cares that the section starts collapsed
// and threads sceneId/canGm through once opened — HighlightReel's own
// behavior is covered by its own test suite.
vi.mock('@/scenes/components/HighlightReel', () => ({
  HighlightReel: ({ sceneId, canGm }: { sceneId: string; canGm?: boolean }) => (
    <div data-testid="highlight-reel">
      reel {sceneId} gm:{String(canGm)}
    </div>
  ),
}));

import { SceneHighlightsPanel } from './SceneHighlightsPanel';
import { fetchScene } from '@/scenes/queries';

const mockFetchScene = vi.mocked(fetchScene);

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(<SceneHighlightsPanel sceneId={5} />, { wrapper });
}

describe('SceneHighlightsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('is collapsed by default and does not mount HighlightReel until opened', async () => {
    mockFetchScene.mockResolvedValue({ viewer_can_gm: true });
    renderPanel();

    const trigger = await screen.findByRole('button', { name: /Highlights/ });
    expect(screen.queryByTestId('highlight-reel')).not.toBeInTheDocument();

    await userEvent.click(trigger);

    expect(await screen.findByTestId('highlight-reel')).toHaveTextContent('reel 5 gm:true');
    expect(mockFetchScene).toHaveBeenCalledWith('5');
  });
});
