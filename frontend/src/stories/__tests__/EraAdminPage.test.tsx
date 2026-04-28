/**
 * EraAdminPage Tests
 *
 * Covers:
 *  - Renders timeline + era list rows
 *  - "+ Create Era" button opens EraFormDialog
 *  - Advance dialog shows correct era name and submits
 *  - Archive dialog shows correct era name and submits
 *  - EraTimeline shows correct status color classes
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { EraAdminPage } from '../pages/EraAdminPage';
import type { Era, PaginatedResponse } from '../types';

// ---------------------------------------------------------------------------
// Mock API module
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  listEras: vi.fn(),
  advanceEra: vi.fn(),
  archiveEra: vi.fn(),
  createEra: vi.fn(),
  updateEra: vi.fn(),
  deleteEra: vi.fn(),
  getEra: vi.fn(),
}));

import * as api from '../api';

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------

const concludedEra: Era = {
  id: 1,
  name: 'dawn_age',
  display_name: 'Dawn Age',
  season_number: 1,
  description: 'The beginning.',
  status: 'concluded',
  activated_at: '2024-01-01T00:00:00Z',
  concluded_at: '2024-06-01T00:00:00Z',
  created_at: '2024-01-01T00:00:00Z',
  story_count: 5,
};

const activeEra: Era = {
  id: 2,
  name: 'age_of_embers',
  display_name: 'Age of Embers',
  season_number: 2,
  description: 'Fire and ash.',
  status: 'active',
  activated_at: '2024-06-01T00:00:00Z',
  concluded_at: null,
  created_at: '2024-01-15T00:00:00Z',
  story_count: 12,
};

const upcomingEra: Era = {
  id: 3,
  name: 'silver_age',
  display_name: 'Silver Age',
  season_number: 3,
  description: 'Peace and prosperity.',
  status: 'upcoming',
  activated_at: null,
  concluded_at: null,
  created_at: '2025-01-01T00:00:00Z',
  story_count: 0,
};

const paginatedResponse: PaginatedResponse<Era> = {
  count: 3,
  next: null,
  previous: null,
  results: [concludedEra, activeEra, upcomingEra],
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('EraAdminPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders era timeline and list after loading', async () => {
    vi.mocked(api.listEras).mockResolvedValue(paginatedResponse);
    render(<EraAdminPage />, { wrapper: createWrapper() });

    // Loading skeleton first
    expect(screen.getByTestId('era-page-skeleton')).toBeInTheDocument();

    // Then content appears
    await waitFor(() => {
      expect(screen.getByTestId('era-timeline')).toBeInTheDocument();
    });

    // List renders all three eras (display names appear in both timeline and list)
    expect(screen.getByTestId('era-list')).toBeInTheDocument();
    expect(screen.getAllByText('Dawn Age').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Age of Embers').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Silver Age').length).toBeGreaterThanOrEqual(1);
  });

  it('shows Create Era button', async () => {
    vi.mocked(api.listEras).mockResolvedValue(paginatedResponse);
    render(<EraAdminPage />, { wrapper: createWrapper() });
    await waitFor(() => screen.getByTestId('create-era-button'));
    expect(screen.getByTestId('create-era-button')).toBeInTheDocument();
  });

  it('opens form dialog when Create Era is clicked', async () => {
    vi.mocked(api.listEras).mockResolvedValue(paginatedResponse);
    render(<EraAdminPage />, { wrapper: createWrapper() });
    await waitFor(() => screen.getByTestId('create-era-button'));
    await userEvent.click(screen.getByTestId('create-era-button'));
    expect(screen.getByText('Create Era')).toBeInTheDocument();
  });

  it('opens Advance dialog when Advance button is clicked for upcoming era', async () => {
    vi.mocked(api.listEras).mockResolvedValue(paginatedResponse);
    render(<EraAdminPage />, { wrapper: createWrapper() });

    await waitFor(() => screen.getByTestId(`era-row-${upcomingEra.id}`));
    const row = screen.getByTestId(`era-row-${upcomingEra.id}`);
    await userEvent.click(within(row).getByText('Advance'));

    // Dialog title appears
    expect(screen.getByText(/Advance to Season 3\?/i)).toBeInTheDocument();
    // Confirm button appears
    expect(screen.getByTestId('advance-era-confirm')).toBeInTheDocument();
  });

  it('submits advance and shows toast on success', async () => {
    vi.mocked(api.listEras).mockResolvedValue(paginatedResponse);
    vi.mocked(api.advanceEra).mockResolvedValue({ ...upcomingEra, status: 'active' });
    render(<EraAdminPage />, { wrapper: createWrapper() });

    await waitFor(() => screen.getByTestId(`era-row-${upcomingEra.id}`));
    const row = screen.getByTestId(`era-row-${upcomingEra.id}`);
    await userEvent.click(within(row).getByText('Advance'));

    await userEvent.click(screen.getByTestId('advance-era-confirm'));

    await waitFor(() => {
      expect(api.advanceEra).toHaveBeenCalledWith(upcomingEra.id);
      expect(toast.success).toHaveBeenCalled();
    });
  });

  it('opens Archive dialog when Archive button is clicked for active era', async () => {
    vi.mocked(api.listEras).mockResolvedValue(paginatedResponse);
    render(<EraAdminPage />, { wrapper: createWrapper() });

    await waitFor(() => screen.getByTestId(`era-row-${activeEra.id}`));
    const row = screen.getByTestId(`era-row-${activeEra.id}`);
    await userEvent.click(within(row).getByText('Archive'));

    // Dialog title appears
    expect(screen.getByText('Archive Era?')).toBeInTheDocument();
    // Confirm button appears
    expect(screen.getByTestId('archive-era-confirm')).toBeInTheDocument();
  });

  it('submits archive and shows toast on success', async () => {
    vi.mocked(api.listEras).mockResolvedValue(paginatedResponse);
    vi.mocked(api.archiveEra).mockResolvedValue({ ...activeEra, status: 'concluded' });
    render(<EraAdminPage />, { wrapper: createWrapper() });

    await waitFor(() => screen.getByTestId(`era-row-${activeEra.id}`));
    const row = screen.getByTestId(`era-row-${activeEra.id}`);
    await userEvent.click(within(row).getByText('Archive'));

    await userEvent.click(screen.getByTestId('archive-era-confirm'));

    await waitFor(() => {
      expect(api.archiveEra).toHaveBeenCalledWith(activeEra.id);
      expect(toast.success).toHaveBeenCalled();
    });
  });
});

// ---------------------------------------------------------------------------
// EraTimeline status color tests
// ---------------------------------------------------------------------------

import { EraTimeline } from '../components/EraTimeline';

describe('EraTimeline', () => {
  it('renders a node per era', () => {
    const eras: Era[] = [concludedEra, activeEra, upcomingEra];
    render(
      <MemoryRouter>
        <EraTimeline eras={eras} />
      </MemoryRouter>
    );
    expect(screen.getByTestId(`era-node-${concludedEra.id}`)).toBeInTheDocument();
    expect(screen.getByTestId(`era-node-${activeEra.id}`)).toBeInTheDocument();
    expect(screen.getByTestId(`era-node-${upcomingEra.id}`)).toBeInTheDocument();
  });

  it('shows "No eras defined" when empty', () => {
    render(
      <MemoryRouter>
        <EraTimeline eras={[]} />
      </MemoryRouter>
    );
    expect(screen.getByText(/No eras defined yet/i)).toBeInTheDocument();
  });

  it('active era node has green ring class', () => {
    render(
      <MemoryRouter>
        <EraTimeline eras={[activeEra]} />
      </MemoryRouter>
    );
    const node = screen.getByTestId(`era-node-${activeEra.id}`);
    // The dot div is a child of the button; check the button's first-child div
    const dot = node.querySelector('div');
    expect(dot?.className).toContain('ring-green-200');
  });

  it('concluded era node has gray class', () => {
    render(
      <MemoryRouter>
        <EraTimeline eras={[concludedEra]} />
      </MemoryRouter>
    );
    const node = screen.getByTestId(`era-node-${concludedEra.id}`);
    const dot = node.querySelector('div');
    expect(dot?.className).toContain('bg-gray-400');
  });

  it('upcoming era node has amber class', () => {
    render(
      <MemoryRouter>
        <EraTimeline eras={[upcomingEra]} />
      </MemoryRouter>
    );
    const node = screen.getByTestId(`era-node-${upcomingEra.id}`);
    const dot = node.querySelector('div');
    expect(dot?.className).toContain('bg-amber-400');
  });
});
