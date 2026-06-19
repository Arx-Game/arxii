/** PathIntentCard tests (#954): current path + declare/clear picker. */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { PathIntentCard } from '../components/PathIntentCard';
import type { PathIntentResponse, PathOptions } from '../types';

vi.mock('../api', () => ({
  getPathIntent: vi.fn(),
  getNextPathOptions: vi.fn(),
  putPathIntent: vi.fn(),
  deletePathIntent: vi.fn(),
}));

import * as api from '../api';

function pathItem(id: number, name: string, stage_display: string) {
  return {
    id,
    name,
    description: '',
    stage: 2,
    stage_display,
    minimum_level: 3,
    is_active: true,
    icon_url: null,
    icon_name: null,
    sort_order: 0,
  };
}

const OPTIONS: PathOptions = {
  current_path: pathItem(1, 'Steel Prospect', 'Prospect'),
  options: [pathItem(3, 'Path of Embers', 'Potential'), pathItem(4, 'Path of Ash', 'Potential')],
} as unknown as PathOptions;

const OPTIONS_TERMINAL: PathOptions = {
  current_path: pathItem(1, 'Steel Prospect', 'Prospect'),
  options: [],
} as unknown as PathOptions;

const OPTIONS_NONE: PathOptions = { current_path: null, options: [] } as unknown as PathOptions;

const NO_INTENT: PathIntentResponse = { intent: null };
const INTENT_EMBERS: PathIntentResponse = {
  intent: {
    id: 9,
    declared_at: '2026-06-01T00:00:00Z',
    intended_path: { id: 3, name: 'Path of Embers', stage: 2, stage_display: 'Potential' },
  },
};

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('PathIntentCard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders nothing when there is no current path', async () => {
    vi.mocked(api.getNextPathOptions).mockResolvedValue(OPTIONS_NONE);
    vi.mocked(api.getPathIntent).mockResolvedValue(NO_INTENT);
    render(<PathIntentCard characterId={42} />, { wrapper: createWrapper() });
    await waitFor(() => expect(api.getNextPathOptions).toHaveBeenCalled());
    expect(screen.queryByTestId('path-intent-card')).not.toBeInTheDocument();
  });

  it('renders current path and selectable options', async () => {
    vi.mocked(api.getNextPathOptions).mockResolvedValue(OPTIONS);
    vi.mocked(api.getPathIntent).mockResolvedValue(NO_INTENT);
    render(<PathIntentCard characterId={42} />, { wrapper: createWrapper() });
    const card = await screen.findByTestId('path-intent-card');
    expect(card).toHaveTextContent('Steel Prospect');
    expect(screen.getByTestId('path-option-3')).toHaveTextContent('Path of Embers');
    expect(screen.getByTestId('path-option-4')).toHaveTextContent('Path of Ash');
    expect(card).not.toHaveTextContent('Audere Majora');
  });

  it('shows empty message and no declare button for a terminal path', async () => {
    vi.mocked(api.getNextPathOptions).mockResolvedValue(OPTIONS_TERMINAL);
    vi.mocked(api.getPathIntent).mockResolvedValue(NO_INTENT);
    render(<PathIntentCard characterId={42} />, { wrapper: createWrapper() });
    await screen.findByTestId('path-intent-card');
    expect(screen.getByTestId('path-options-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('path-intent-declare')).not.toBeInTheDocument();
  });

  it('declaring an option calls putPathIntent with the selected path', async () => {
    vi.mocked(api.getNextPathOptions).mockResolvedValue(OPTIONS);
    vi.mocked(api.getPathIntent).mockResolvedValue(NO_INTENT);
    vi.mocked(api.putPathIntent).mockResolvedValue(INTENT_EMBERS);
    render(<PathIntentCard characterId={42} />, { wrapper: createWrapper() });
    fireEvent.click(await screen.findByTestId('path-option-3'));
    fireEvent.click(screen.getByTestId('path-intent-declare'));
    await waitFor(() => expect(api.putPathIntent).toHaveBeenCalledWith(42, 3));
  });

  it('shows the declared marker + Clear, and Clear calls deletePathIntent', async () => {
    vi.mocked(api.getNextPathOptions).mockResolvedValue(OPTIONS);
    vi.mocked(api.getPathIntent).mockResolvedValue(INTENT_EMBERS);
    vi.mocked(api.deletePathIntent).mockResolvedValue(undefined);
    render(<PathIntentCard characterId={42} />, { wrapper: createWrapper() });
    const declared = await screen.findByTestId('path-option-3');
    expect(declared).toHaveTextContent('declared');
    fireEvent.click(screen.getByTestId('path-intent-clear'));
    await waitFor(() => expect(api.deletePathIntent).toHaveBeenCalledWith(42));
  });
});
