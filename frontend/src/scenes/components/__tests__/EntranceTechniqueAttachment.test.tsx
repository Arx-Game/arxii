/**
 * Tests for EntranceTechniqueAttachment — technique+target attachment for a
 * Make-an-Entrance pose (#2183).
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { CastableTechnique } from '../../actionTypes';

const mockUseCastableTechniques = vi.fn();

vi.mock('../../actionQueries', () => ({
  useCastableTechniques: (personaId: number | null) => mockUseCastableTechniques(personaId),
}));

import { EntranceTechniqueAttachment } from '../EntranceTechniqueAttachment';

function makeTechnique(overrides: Partial<CastableTechnique> = {}): CastableTechnique {
  return {
    id: 1,
    name: 'Thunderclap Entrance',
    anima_cost: 5,
    tier: 1,
    intensity: 3,
    control: 2,
    hostile: false,
    target_type: 'self',
    reach: 'any',
    target_spec: null,
    ...overrides,
  };
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('EntranceTechniqueAttachment', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCastableTechniques.mockReturnValue({ data: [], isLoading: false });
  });

  it('renders the attach trigger button', () => {
    render(
      <EntranceTechniqueAttachment personaId={9} candidates={[]} value={null} onChange={vi.fn()} />,
      { wrapper: createWrapper() }
    );
    expect(screen.getByTestId('entrance-technique-trigger')).toBeInTheDocument();
  });

  it('shows "No castable techniques" when the list is empty', async () => {
    const user = userEvent.setup();
    render(
      <EntranceTechniqueAttachment personaId={9} candidates={[]} value={null} onChange={vi.fn()} />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByTestId('entrance-technique-trigger'));
    expect(await screen.findByText('No castable techniques')).toBeInTheDocument();
  });

  it('lists castable techniques with hostile marker and anima cost', async () => {
    mockUseCastableTechniques.mockReturnValue({
      data: [
        makeTechnique({ id: 1, name: 'Gentle Bow', hostile: false, anima_cost: 4 }),
        makeTechnique({ id: 2, name: 'Thunderous Arrival', hostile: true, anima_cost: 12 }),
      ],
      isLoading: false,
    });

    const user = userEvent.setup();
    render(
      <EntranceTechniqueAttachment personaId={9} candidates={[]} value={null} onChange={vi.fn()} />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByTestId('entrance-technique-trigger'));

    expect(await screen.findByText('Gentle Bow')).toBeInTheDocument();
    expect(screen.getByText('Thunderous Arrival')).toBeInTheDocument();
    expect(screen.getByText('4 anima')).toBeInTheDocument();
    expect(screen.getByText('12 anima')).toBeInTheDocument();
    // Hostile marker renders only for the hostile technique.
    expect(screen.getAllByTitle('Hostile — may seed or feed a combat encounter')).toHaveLength(1);
  });

  it('picking a self/no-target technique (target_spec=null) commits immediately, no target picker', async () => {
    mockUseCastableTechniques.mockReturnValue({
      data: [makeTechnique({ id: 3, name: 'Solo Flourish', target_spec: null })],
      isLoading: false,
    });
    const onChange = vi.fn();
    const user = userEvent.setup({ pointerEventsCheck: 0 });

    render(
      <EntranceTechniqueAttachment
        personaId={9}
        candidates={[{ id: 100, name: 'Bob' }]}
        value={null}
        onChange={onChange}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByTestId('entrance-technique-trigger'));
    await user.click(await screen.findByText('Solo Flourish'));

    expect(onChange).toHaveBeenCalledWith({ techniqueId: 3 });
    // No target picker should ever have appeared.
    expect(screen.queryByText('Select target')).toBeNull();
  });

  it('picking a technique with a target_spec opens the target picker, then commits with the chosen target', async () => {
    mockUseCastableTechniques.mockReturnValue({
      data: [
        makeTechnique({
          id: 4,
          name: 'Rival Challenge',
          target_spec: {
            kind: 'persona',
            cardinality: 'single',
            filters: { in_same_scene: true, exclude_self: true, must_be_conscious: false },
          },
        }),
      ],
      isLoading: false,
    });
    const onChange = vi.fn();
    const user = userEvent.setup({ pointerEventsCheck: 0 });

    render(
      <EntranceTechniqueAttachment
        personaId={9}
        candidates={[
          { id: 100, name: 'Bob' },
          { id: 101, name: 'Carol' },
        ]}
        value={null}
        onChange={onChange}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByTestId('entrance-technique-trigger'));
    await user.click(await screen.findByText('Rival Challenge'));

    // Target picker appears with the scene's candidates.
    expect(await screen.findByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Carol')).toBeInTheDocument();

    await user.click(screen.getByText('Carol'));

    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ techniqueId: 4, targetPersonaId: 101 })
    );
  });

  it('cancelling the target picker commits nothing', async () => {
    mockUseCastableTechniques.mockReturnValue({
      data: [
        makeTechnique({
          id: 4,
          name: 'Rival Challenge',
          target_spec: {
            kind: 'persona',
            cardinality: 'single',
            filters: { in_same_scene: true, exclude_self: true, must_be_conscious: false },
          },
        }),
      ],
      isLoading: false,
    });
    const onChange = vi.fn();
    const user = userEvent.setup({ pointerEventsCheck: 0 });

    render(
      <EntranceTechniqueAttachment
        personaId={9}
        candidates={[{ id: 100, name: 'Bob' }]}
        value={null}
        onChange={onChange}
      />,
      { wrapper: createWrapper() }
    );

    await user.click(screen.getByTestId('entrance-technique-trigger'));
    await user.click(await screen.findByText('Rival Challenge'));
    await user.click(await screen.findByRole('button', { name: /cancel/i }));

    expect(onChange).not.toHaveBeenCalled();
  });

  it('renders a chip with the attached technique name and detaches on click', async () => {
    mockUseCastableTechniques.mockReturnValue({
      data: [makeTechnique({ id: 5, name: 'Solo Flourish' })],
      isLoading: false,
    });
    const onChange = vi.fn();
    const user = userEvent.setup();

    render(
      <EntranceTechniqueAttachment
        personaId={9}
        candidates={[]}
        value={{ techniqueId: 5 }}
        onChange={onChange}
      />,
      { wrapper: createWrapper() }
    );

    const chip = screen.getByTestId('entrance-technique-chip');
    expect(chip).toHaveTextContent('Solo Flourish');

    await user.click(chip);
    expect(onChange).toHaveBeenCalledWith(null);
  });
});
