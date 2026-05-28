import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';

import { CreateMissionPage } from '../pages/CreateMissionPage';
import * as queries from '../queries';
import { ApiValidationError } from '../api';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CreateMissionPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CreateMissionPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(queries, 'useMissionCategories').mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof queries.useMissionCategories>);
  });

  it('renders the form with required fields', () => {
    vi.spyOn(queries, 'useCreateMissionTemplate').mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateMissionTemplate>);

    renderPage();
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/summary/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create/i })).toBeInTheDocument();
  });

  it('blocks submit when level_band_min > level_band_max', async () => {
    const mutateAsync = vi.fn();
    vi.spyOn(queries, 'useCreateMissionTemplate').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateMissionTemplate>);

    renderPage();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'lore' } });
    fireEvent.change(screen.getByLabelText(/level band min/i), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText(/level band max/i), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));
    await waitFor(() => {
      expect(screen.getByText(/min cannot exceed max/i)).toBeInTheDocument();
    });
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('submits valid form and navigates to canvas on success', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: 42, name: 'Heist' });
    vi.spyOn(queries, 'useCreateMissionTemplate').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateMissionTemplate>);

    renderPage();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Heist' } });
    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'lore' } });
    fireEvent.change(screen.getByLabelText(/level band min/i), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/level band max/i), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/risk tier/i), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/cooldown.*amount/i), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));
    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          name: 'Heist',
          summary: 'lore',
          level_band_min: 1,
          level_band_max: 5,
          risk_tier: 2,
          cooldown: 'P7D',
        })
      );
      expect(mockNavigate).toHaveBeenCalledWith('/staff/missions/42/canvas');
    });
  });

  it('shows rename toast when response name differs from submitted', async () => {
    const mutateAsync = vi.fn().mockResolvedValue({ id: 7, name: 'Heist 2' });
    vi.spyOn(queries, 'useCreateMissionTemplate').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateMissionTemplate>);

    renderPage();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Heist' } });
    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'lore' } });
    fireEvent.change(screen.getByLabelText(/level band min/i), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/level band max/i), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/risk tier/i), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/cooldown.*amount/i), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Saved as "Heist 2" — "Heist" was taken.');
    });
  });

  it('displays inline field errors when API returns 400 with field errors', async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(
        new ApiValidationError({ name: ['A mission with this name already exists.'] })
      );
    vi.spyOn(queries, 'useCreateMissionTemplate').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateMissionTemplate>);

    renderPage();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Taken' } });
    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'lore' } });
    fireEvent.change(screen.getByLabelText(/level band min/i), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/level band max/i), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/risk tier/i), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/cooldown.*amount/i), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));
    await waitFor(() => {
      expect(screen.getByText(/already exists/i)).toBeInTheDocument();
    });
  });

  it('flattens nested DRF errors instead of showing [object Object]', async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(new ApiValidationError({ categories: [{ pk: ['Invalid pk "999"'] }] }));
    vi.spyOn(queries, 'useCreateMissionTemplate').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateMissionTemplate>);

    renderPage();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'lore' } });
    fireEvent.change(screen.getByLabelText(/level band min/i), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/level band max/i), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/risk tier/i), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/cooldown.*amount/i), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));
    await waitFor(() => {
      const errorText = screen.getByText(/Invalid pk/i);
      expect(errorText).toBeInTheDocument();
      // Confirm we do NOT show literal "[object Object]" anywhere
      expect(screen.queryByText(/\[object Object\]/i)).not.toBeInTheDocument();
    });
  });

  it('displays a banner when API returns a detail-only error (401/403/500)', async () => {
    const mutateAsync = vi
      .fn()
      .mockRejectedValue(
        new ApiValidationError({ detail: 'Authentication credentials were not provided.' })
      );
    vi.spyOn(queries, 'useCreateMissionTemplate').mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useCreateMissionTemplate>);

    renderPage();
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'X' } });
    fireEvent.change(screen.getByLabelText(/summary/i), { target: { value: 'lore' } });
    fireEvent.change(screen.getByLabelText(/level band min/i), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/level band max/i), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText(/risk tier/i), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText(/cooldown.*amount/i), { target: { value: '1' } });
    fireEvent.click(screen.getByRole('button', { name: /create/i }));
    await waitFor(() => {
      expect(screen.getByText(/authentication credentials/i)).toBeInTheDocument();
    });
  });
});
