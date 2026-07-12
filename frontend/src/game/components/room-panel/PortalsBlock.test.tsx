import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { usePortalDestinationsQuery } from '@/locations/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { PortalsBlock } from './PortalsBlock';

vi.mock('@/locations/queries', () => ({
  usePortalDestinationsQuery: vi.fn(),
}));

vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(),
}));

const mockUsePortalDestinationsQuery = vi.mocked(usePortalDestinationsQuery);
const mockUseDispatchPlayerAction = vi.mocked(useDispatchPlayerAction);

function mockDispatch(mutate = vi.fn()) {
  mockUseDispatchPlayerAction.mockReturnValue({
    mutate,
    isPending: false,
  } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  return mutate;
}

describe('PortalsBlock', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when the query is disabled (no active character)', () => {
    mockUsePortalDestinationsQuery.mockReturnValue({
      data: undefined,
    } as unknown as ReturnType<typeof usePortalDestinationsQuery>);
    mockDispatch();

    const { container } = renderWithProviders(<PortalsBlock characterId={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the destination list is empty', () => {
    mockUsePortalDestinationsQuery.mockReturnValue({
      data: [],
    } as unknown as ReturnType<typeof usePortalDestinationsQuery>);
    mockDispatch();

    const { container } = renderWithProviders(<PortalsBlock characterId={42} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders a compact list of destinations (kind, anchor, room)', () => {
    mockUsePortalDestinationsQuery.mockReturnValue({
      data: [
        {
          anchor_id: 1,
          room_id: 501,
          room_name: 'Sable Hold',
          kind_name: 'Mirror',
          anchor_name: 'a tall silvered mirror',
        },
      ],
    } as unknown as ReturnType<typeof usePortalDestinationsQuery>);
    mockDispatch();

    renderWithProviders(<PortalsBlock characterId={42} />);

    expect(screen.getByText('Mirror')).toBeInTheDocument();
    expect(screen.getByText(/a tall silvered mirror/)).toBeInTheDocument();
    expect(screen.getByText(/Sable Hold/)).toBeInTheDocument();
    expect(screen.getByTestId('portal-travel-1')).toBeInTheDocument();
  });

  it('dispatches the travel_to registry action with the destination room id on Travel click', async () => {
    const user = userEvent.setup();
    const mutate = mockDispatch();
    mockUsePortalDestinationsQuery.mockReturnValue({
      data: [
        {
          anchor_id: 7,
          room_id: 501,
          room_name: 'Sable Hold',
          kind_name: 'Mirror',
          anchor_name: 'a tall silvered mirror',
        },
      ],
    } as unknown as ReturnType<typeof usePortalDestinationsQuery>);

    renderWithProviders(<PortalsBlock characterId={42} />);

    await user.click(screen.getByTestId('portal-travel-7'));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'travel_to' },
        kwargs: { target: 501 },
      });
    });
  });
});
