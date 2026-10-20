/**
 * CommissionDialog tests (#4512): the form shows what the server will do, and sends the
 * commissioner's own words and dedication with the offer.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { ItemInstance } from '@/inventory/types';
import { CommissionDialog } from '../CommissionDialog';
import type { ServiceOffer } from '../api';

vi.mock('@/inventory/hooks/useInventory', () => ({ useInventory: vi.fn() }));
vi.mock('@/character-creation/queries', () => ({
  useFacets: () => ({ data: [{ id: 7, name: 'Kestrel' }] }),
  useNearFacets: () => ({ data: [], isPending: false }),
  useCreateFacet: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: (term: string) => ({
    results: term.toLowerCase().startsWith('cor') ? [{ id: 31, name: 'Corwen' }] : [],
    isFetching: false,
  }),
}));
vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  dispatchMarketAction: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useInventory } from '@/inventory/hooks/useInventory';
import { dispatchMarketAction } from '../api';

const offer: ServiceOffer = {
  id: 5,
  crafter_name: 'Corwen',
  recipe_kind: 'facet_attach',
  fee: 40,
  shop_room_id: 9,
};

function coat(overrides: Partial<ItemInstance> = {}): ItemInstance {
  return {
    id: 12,
    display_name: 'riding coat',
    custom_name: '',
    custom_description: '',
    dedicated_to_name: null,
    designer_is_holder: false,
    crafter_name: 'Corwen',
    designer_name: null,
    facet_workers: [],
    ...overrides,
  } as ItemInstance;
}

function holding(...items: ItemInstance[]) {
  vi.mocked(useInventory).mockReturnValue({
    data: items,
    isLoading: false,
  } as unknown as ReturnType<typeof useInventory>);
}

// A popover inside a modal dialog leaves the page `pointer-events: none` in jsdom.
const user = userEvent.setup({ pointerEventsCheck: 0 });

async function chooseCoat() {
  await user.click(screen.getByRole('combobox'));
  await user.click(await screen.findByText('riding coat'));
}

function renderDialog() {
  return renderWithProviders(
    <CommissionDialog open onOpenChange={vi.fn()} offer={offer} characterId={3} myName="Linnet" />
  );
}

describe('CommissionDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(dispatchMarketAction).mockResolvedValue('The work is done.');
  });

  it('says the fee is charged whatever the roll', () => {
    holding(coat());
    renderDialog();
    expect(screen.getByText(/charged whatever the roll/i)).toBeInTheDocument();
  });

  it('credits the commissioner as designer in the preview only once they write text', async () => {
    holding(coat({ dedicated_to_name: 'Linnet' }));
    renderDialog();
    await chooseCoat();

    expect(screen.getByTestId('commission-preview')).toHaveTextContent(
      'Made by Corwen for Linnet. Facet work by Corwen.'
    );
    await user.type(screen.getByLabelText(/^Name/), 'Highwind Coat');
    expect(screen.getByTestId('commission-preview')).toHaveTextContent(
      'Made by Corwen for Linnet. Designed by Linnet. Facet work by Corwen.'
    );
  });

  it('locks a dedication that is already written and a design that is not yours', async () => {
    holding(
      coat({
        dedicated_to_name: 'Ottilie',
        custom_name: "Corwen's Coat",
        designer_name: 'Corwen',
        designer_is_holder: false,
      })
    );
    renderDialog();
    await chooseCoat();

    expect(screen.getByTestId('commission-dedication-locked')).toHaveTextContent(
      'A dedication is permanent'
    );
    expect(screen.getByLabelText(/^Name/)).toBeDisabled();
    expect(screen.getByLabelText(/^Description/)).not.toBeDisabled();
  });

  it('sends the name, description and dedication with the offer', async () => {
    holding(coat());
    renderDialog();
    await chooseCoat();

    await user.click(screen.getByRole('button', { name: /choose a facet/i }));
    await user.click(await screen.findByText('Kestrel'));
    await user.type(screen.getByLabelText(/^Name/), 'Highwind Coat');
    await user.type(screen.getByLabelText(/^Description/), 'Grey wool.');
    await user.type(screen.getByLabelText('Choose a persona'), 'Cor');
    await user.click(await screen.findByRole('button', { name: 'Corwen' }));
    await user.click(screen.getByRole('button', { name: 'Commission' }));

    await waitFor(() =>
      expect(dispatchMarketAction).toHaveBeenCalledWith(3, 'market_service_craft', {
        offer_id: 5,
        item_instance_id: 12,
        target_id: 7,
        name: 'Highwind Coat',
        description: 'Grey wool.',
        dedicate_to_id: 31,
      })
    );
  });
});
