/**
 * MotifFacetPanel (#5021): the player ties facets to each claimed resonance and unties
 * them. Mocks the magic hooks (MotifStylePanel.test.tsx's idiom); the FacetPicker is the
 * real one, over a mocked facet vocabulary.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { MotifFacetPanel } from './MotifFacetPanel';

vi.mock('../queries', () => ({
  useMotifStyleBindings: vi.fn(),
  useCharacterResonances: vi.fn(),
  useSetMotifFacet: vi.fn(),
}));
vi.mock('@/character-creation/queries', () => ({
  useFacets: () => ({
    data: [
      { id: 1, name: 'Wolf', description: '' },
      { id: 2, name: 'Silk', description: '' },
    ],
  }),
  useNearFacets: () => ({ data: [], isPending: false }),
  useCreateFacet: () => ({ mutate: vi.fn() }),
}));

import * as magicQueries from '../queries';

const RESONANCES = [
  { id: 3, character_sheet: 10, resonance: 3, resonance_name: 'Wildfire' },
  { id: 5, character_sheet: 10, resonance: 5, resonance_name: 'Tidewater' },
];
const TIES = [{ facet_id: 1, facet_name: 'Wolf', resonance_id: 3, resonance_name: 'Wildfire' }];

function setup(options: { resonances?: unknown[]; error?: string } = {}) {
  const mutate = vi.fn();
  vi.mocked(magicQueries.useMotifStyleBindings).mockReturnValue({
    data: { bindings: [], facet_bindings: TIES },
  } as unknown as ReturnType<typeof magicQueries.useMotifStyleBindings>);
  vi.mocked(magicQueries.useCharacterResonances).mockReturnValue({
    data: options.resonances ?? RESONANCES,
  } as unknown as ReturnType<typeof magicQueries.useCharacterResonances>);
  vi.mocked(magicQueries.useSetMotifFacet).mockReturnValue({
    mutate,
    isPending: false,
    isError: Boolean(options.error),
    error: options.error ? new Error(options.error) : null,
  } as unknown as ReturnType<typeof magicQueries.useSetMotifFacet>);
  renderWithProviders(<MotifFacetPanel characterSheetId={10} />);
  return { mutate };
}

describe('MotifFacetPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows each claimed resonance with the facets tied to it', () => {
    setup();
    const wildfire = screen.getByTestId('motif-facet-group-3');
    expect(wildfire).toHaveTextContent('Wildfire');
    expect(wildfire).toHaveTextContent('Wolf');
    expect(screen.getByTestId('motif-facet-group-5')).not.toHaveTextContent('Wolf');
    expect(magicQueries.useSetMotifFacet).toHaveBeenCalledWith(10);
    expect(magicQueries.useMotifStyleBindings).toHaveBeenCalledWith(10);
  });

  it('unties a facet', async () => {
    const { mutate } = setup();
    await userEvent.click(screen.getByRole('button', { name: 'Untie Wolf' }));
    expect(mutate).toHaveBeenCalledWith({ facet_id: 1, resonance_id: 3, tie: false });
  });

  it('ties a picked facet to that resonance', async () => {
    const { mutate } = setup();
    const tidewater = screen.getByTestId('motif-facet-group-5');
    await userEvent.click(
      Array.from(tidewater.querySelectorAll('button')).find((b) =>
        b.textContent?.includes('Add facet')
      )!
    );
    await userEvent.click(await screen.findByText('Silk'));
    expect(mutate).toHaveBeenCalledWith({ facet_id: 2, resonance_id: 5, tie: true });
  });

  it("shows the server's refusal", () => {
    setup({ error: 'Your Howl of the Pack flourish needs that facet.' });
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Your Howl of the Pack flourish needs that facet.'
    );
  });

  it('renders nothing without a claimed resonance', () => {
    setup({ resonances: [] });
    expect(screen.queryByTestId('motif-facet-panel')).not.toBeInTheDocument();
  });
});
