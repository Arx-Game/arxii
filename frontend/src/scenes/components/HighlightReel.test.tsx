import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../queries', () => ({
  fetchHighlightReel: vi.fn(),
  fetchInteraction: vi.fn(),
}));

// Stub PoseUnit: revealing a moment only needs to prove the pose is fetched + rendered;
// PoseUnit's own deep dependency tree is out of scope here.
vi.mock('./PoseUnit', () => ({
  PoseUnit: ({ interaction }: { interaction: { id: number } }) => (
    <div data-testid="pose-unit">pose {interaction.id}</div>
  ),
}));

import { HighlightReel } from './HighlightReel';
import { fetchHighlightReel, fetchInteraction } from '../queries';

const mockFetchReel = vi.mocked(fetchHighlightReel);
const mockFetchInteraction = vi.mocked(fetchInteraction);

function renderReel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return render(<HighlightReel sceneId="5" />, { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
});

it('renders nothing for an empty reel', async () => {
  mockFetchReel.mockResolvedValue({ featured: null, index: [] });
  renderReel();
  await waitFor(() => expect(mockFetchReel).toHaveBeenCalled());
  expect(screen.queryByRole('button', { name: /Highlight Reel/ })).not.toBeInTheDocument();
});

it('is collapsed by default and seals the featured moment until revealed', async () => {
  mockFetchReel.mockResolvedValue({
    featured: { interaction_id: 11 },
    index: [{ interaction_id: 22, rank: 1 }],
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  mockFetchInteraction.mockResolvedValue({ id: 11 } as any);
  renderReel();

  // Section header appears, but the sealed cards stay hidden while collapsed.
  const header = await screen.findByRole('button', { name: /Highlight Reel/ });
  expect(
    screen.queryByRole('button', { name: /Top moment of this scene/ })
  ).not.toBeInTheDocument();

  // Open the section: sealed featured + index entries appear, but no pose content yet.
  await userEvent.click(header);
  expect(screen.getByRole('button', { name: /Top moment of this scene/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Moment #1/ })).toBeInTheDocument();
  expect(screen.queryByTestId('pose-unit')).not.toBeInTheDocument();
  expect(mockFetchInteraction).not.toHaveBeenCalled();
});

it('reveals a pose only when its sealed card is opened', async () => {
  mockFetchReel.mockResolvedValue({ featured: { interaction_id: 11 }, index: [] });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  mockFetchInteraction.mockResolvedValue({ id: 11 } as any);
  renderReel();

  await userEvent.click(await screen.findByRole('button', { name: /Highlight Reel/ }));
  await userEvent.click(screen.getByRole('button', { name: /Top moment of this scene/ }));

  await waitFor(() => expect(mockFetchInteraction).toHaveBeenCalledWith(11));
  expect(await screen.findByTestId('pose-unit')).toHaveTextContent('pose 11');
});
