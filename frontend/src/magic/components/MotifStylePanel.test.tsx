/**
 * MotifStylePanel tests (#2030) — player-facing Motif style-binding management.
 *
 * Mirrors SpellbookTab.test.tsx's renderWithProviders setup + the
 * mock-the-hook-module idiom used by SineatingRequestDialog.test.tsx (no msw).
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { MotifStylePanel } from './MotifStylePanel';
import type {
  useMotifStyleBindings,
  useStyleCatalog,
  useCharacterResonances,
  useBindMotifStyle,
  useUnbindMotifStyle,
} from '../queries';

vi.mock('../queries', () => ({
  useMotifStyleBindings: vi.fn(),
  useStyleCatalog: vi.fn(),
  useCharacterResonances: vi.fn(),
  useBindMotifStyle: vi.fn(),
  useUnbindMotifStyle: vi.fn(),
}));

import * as magicQueries from '../queries';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockBindings = [
  {
    style_id: 1,
    style_name: 'Sardonic',
    audacity: 'Bold',
    resonance_id: 3,
    resonance_name: 'Starfire',
  },
  {
    style_id: 2,
    style_name: 'Wry',
    audacity: 'Subtle',
    resonance_id: 3,
    resonance_name: 'Starfire',
  },
  {
    style_id: 4,
    style_name: 'Grandiloquent',
    audacity: 'Bold',
    resonance_id: 5,
    resonance_name: 'Moonveil',
  },
];

const mockCatalog = {
  count: 2,
  next: null,
  previous: null,
  results: [
    { id: 1, name: 'Sardonic', description: 'Cutting wit.', audacity: 'Bold' },
    { id: 4, name: 'Grandiloquent', description: 'Overblown flourish.', audacity: 'Bold' },
  ],
};

const mockResonances = [
  {
    id: 3,
    character_sheet: 10,
    resonance: 3,
    resonance_name: 'Starfire',
    resonance_detail: { id: 3, name: 'Starfire' },
    balance: 50,
    lifetime_earned: 200,
  },
  {
    id: 5,
    character_sheet: 10,
    resonance: 5,
    resonance_name: 'Moonveil',
    resonance_detail: { id: 5, name: 'Moonveil' },
    balance: 20,
    lifetime_earned: 80,
  },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setupMocks(options?: {
  bindings?: typeof mockBindings;
  bindingsLoading?: boolean;
  catalog?: typeof mockCatalog;
  resonances?: typeof mockResonances;
  bindOverrides?: { isPending?: boolean; isError?: boolean; error?: Error | null };
  unbindOverrides?: { isPending?: boolean; isError?: boolean; error?: Error | null };
}) {
  const bindMutate = vi.fn();
  const unbindMutate = vi.fn();

  vi.mocked(magicQueries.useMotifStyleBindings).mockReturnValue({
    data: { bindings: options?.bindings ?? mockBindings },
    isLoading: options?.bindingsLoading ?? false,
  } as unknown as ReturnType<typeof useMotifStyleBindings>);

  vi.mocked(magicQueries.useStyleCatalog).mockReturnValue({
    data: options?.catalog ?? mockCatalog,
    isLoading: false,
  } as unknown as ReturnType<typeof useStyleCatalog>);

  vi.mocked(magicQueries.useCharacterResonances).mockReturnValue({
    data: options?.resonances ?? mockResonances,
    isLoading: false,
  } as unknown as ReturnType<typeof useCharacterResonances>);

  vi.mocked(magicQueries.useBindMotifStyle).mockReturnValue({
    mutate: bindMutate,
    isPending: options?.bindOverrides?.isPending ?? false,
    isError: options?.bindOverrides?.isError ?? false,
    error: options?.bindOverrides?.error ?? null,
  } as unknown as ReturnType<typeof useBindMotifStyle>);

  vi.mocked(magicQueries.useUnbindMotifStyle).mockReturnValue({
    mutate: unbindMutate,
    isPending: options?.unbindOverrides?.isPending ?? false,
    isError: options?.unbindOverrides?.isError ?? false,
    error: options?.unbindOverrides?.error ?? null,
  } as unknown as ReturnType<typeof useUnbindMotifStyle>);

  return { bindMutate, unbindMutate };
}

describe('MotifStylePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders current bindings grouped by resonance', () => {
    setupMocks({});
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);

    const starfireGroup = screen.getByTestId('motif-style-group-3');
    expect(starfireGroup).toHaveTextContent('Starfire');
    expect(starfireGroup).toHaveTextContent('Sardonic');
    expect(starfireGroup).toHaveTextContent('Wry');

    const moonveilGroup = screen.getByTestId('motif-style-group-5');
    expect(moonveilGroup).toHaveTextContent('Moonveil');
    expect(moonveilGroup).toHaveTextContent('Grandiloquent');
  });

  it('scopes bindings + mutations to the viewed character, not any active puppet', () => {
    setupMocks({});
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);

    // The cross-character-scoping fix (#2030 review): the bindings query and
    // both mutation hooks must be given THIS character's id (which backs the
    // X-Character-ID header server-side) rather than defaulting to whatever
    // character the account currently puppets.
    expect(magicQueries.useMotifStyleBindings).toHaveBeenCalledWith(10);
    expect(magicQueries.useBindMotifStyle).toHaveBeenCalledWith(10);
    expect(magicQueries.useUnbindMotifStyle).toHaveBeenCalledWith(10);
  });

  it('shows an empty-bindings message when there are none', () => {
    setupMocks({ bindings: [] });
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);
    expect(screen.getByTestId('motif-style-bindings-empty')).toBeInTheDocument();
  });

  it('fires the unbind mutation with the style_id when Unbind is clicked', async () => {
    const { unbindMutate } = setupMocks({});
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);

    await userEvent.click(screen.getByTestId('unbind-style-1'));

    expect(unbindMutate).toHaveBeenCalledWith({ style_id: 1 });
  });

  it('submits the bind form with the selected style_id and resonance_id', async () => {
    const { bindMutate } = setupMocks({});
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);

    await userEvent.selectOptions(screen.getByTestId('motif-style-select'), '4');
    await userEvent.selectOptions(screen.getByTestId('motif-resonance-select'), '5');
    await userEvent.click(screen.getByTestId('motif-style-bind-submit'));

    expect(bindMutate).toHaveBeenCalledWith({ style_id: 4, resonance_id: 5 }, expect.anything());
  });

  it('disables Bind until both a style and a resonance are chosen', async () => {
    setupMocks({});
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);

    expect(screen.getByTestId('motif-style-bind-submit')).toBeDisabled();

    await userEvent.selectOptions(screen.getByTestId('motif-style-select'), '4');
    expect(screen.getByTestId('motif-style-bind-submit')).toBeDisabled();

    await userEvent.selectOptions(screen.getByTestId('motif-resonance-select'), '5');
    expect(screen.getByTestId('motif-style-bind-submit')).toBeEnabled();
  });

  it('explains that a resonance must be claimed first when there are none', () => {
    setupMocks({ resonances: [] });
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);
    expect(screen.getByTestId('motif-style-no-resonances')).toBeInTheDocument();
    expect(screen.queryByTestId('motif-style-select')).not.toBeInTheDocument();
  });

  it('renders the 400 detail message on a bind error', () => {
    setupMocks({
      bindOverrides: { isError: true, error: new Error('Audacity cap exceeded for this tier.') },
    });
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);

    expect(screen.getByTestId('motif-style-bind-error')).toHaveTextContent(
      'Audacity cap exceeded for this tier.'
    );
  });

  it('renders the 400 detail message on an unbind error', () => {
    setupMocks({
      unbindOverrides: { isError: true, error: new Error('No such binding.') },
    });
    renderWithProviders(<MotifStylePanel characterSheetId={10} />);

    expect(screen.getByTestId('motif-style-unbind-error')).toHaveTextContent('No such binding.');
  });
});
