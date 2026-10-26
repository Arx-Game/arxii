/**
 * GMFeatureControls (#4675): the GM tab's Add feature control. Shown only when the
 * GM's actions carry gm_attach_feature; adds with the picked place, type and square;
 * removes a listed feature; refreshes the encounter after either.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mockUseCombatEncounter = vi.fn();
const mockDispatch = vi.fn();
const mockUseFeatureTypes = vi.fn();
vi.mock('@/combat/queries', () => ({
  combatKeys: { encounter: (id: number) => ['combat', 'encounter', id] },
  useCombatEncounter: () => mockUseCombatEncounter(),
  useDispatchPlayerAction: () => ({ mutateAsync: mockDispatch, isPending: false }),
  useFeatureTypes: (enabled: boolean) => mockUseFeatureTypes(enabled),
}));

const mockUseAvailableActions = vi.fn();
vi.mock('@/scenes/actionQueries', () => ({
  availableActionsKeys: { forCharacter: (id: number) => ['available-actions', id] },
  useAvailableActionsQuery: () => mockUseAvailableActions(),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import { GMFeatureControls } from '../GMFeatureControls';

const ATTACH_REF = {
  backend: 'registry',
  challenge_instance_id: null,
  approach_id: null,
  technique_id: null,
  registry_key: 'gm_attach_feature',
};

function withActions(keys: string[]) {
  mockUseAvailableActions.mockReturnValue({
    data: { results: keys.map((key) => ({ ref: { ...ATTACH_REF, registry_key: key } })) },
  });
}

const ENCOUNTER = {
  id: 7,
  position_nodes: [
    {
      id: 1,
      name: 'Floor',
      features: [{ id: 11, name: 'Chandelier', art_url: null, square_x: 6, square_y: 4 }],
    },
    { id: 2, name: 'Stage', features: [] },
  ],
};

let client: QueryClient;
function renderControls() {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<GMFeatureControls sceneId={3} encounterId={7} characterId={5} />, {
    wrapper: Wrapper,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  mockUseCombatEncounter.mockReturnValue({ data: ENCOUNTER });
  mockUseFeatureTypes.mockReturnValue({
    data: [
      { id: 21, name: 'Chandelier', reach: 'adjacent', art_url: null },
      { id: 22, name: 'Rope', reach: 'any_place', art_url: null },
    ],
  });
  mockDispatch.mockResolvedValue({
    backend: 'registry',
    deferred: false,
    success: true,
    message: 'You add the Rope to Stage.',
  });
});

describe('GMFeatureControls', () => {
  it('shows nothing, and loads no feature types, without the gm_attach_feature entry', () => {
    withActions(['move_to_position']);
    const { container } = renderControls();
    expect(container).toBeEmptyDOMElement();
    expect(mockUseFeatureTypes).toHaveBeenCalledWith(false);
  });

  it('adds the picked feature type to the picked place on the given square', async () => {
    withActions(['gm_attach_feature']);
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const user = userEvent.setup();
    renderControls();

    const add = screen.getByRole('button', { name: 'Add feature' });
    expect(add).toBeDisabled();
    await user.selectOptions(screen.getByLabelText('Place'), 'Stage');
    await user.selectOptions(screen.getByLabelText('Feature'), 'Rope');
    await user.type(screen.getByLabelText('Square x'), '7');
    expect(add).toBeDisabled(); // half a square
    await user.type(screen.getByLabelText('Square y'), '3');
    await user.click(add);

    expect(mockDispatch).toHaveBeenCalledWith({
      ref: ATTACH_REF,
      kwargs: { position_id: 2, feature_type_id: 22, square_x: 7, square_y: 3 },
    });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('You add the Rope to Stage.'));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['combat', 'encounter', 7] });
  });

  it('adds without a square when both are blank', async () => {
    withActions(['gm_attach_feature']);
    const user = userEvent.setup();
    renderControls();

    await user.selectOptions(screen.getByLabelText('Place'), 'Floor');
    await user.selectOptions(screen.getByLabelText('Feature'), 'Chandelier');
    await user.click(screen.getByRole('button', { name: 'Add feature' }));

    expect(mockDispatch).toHaveBeenCalledWith({
      ref: ATTACH_REF,
      kwargs: { position_id: 1, feature_type_id: 21 },
    });
  });

  it('removes a listed feature by its id', async () => {
    withActions(['gm_attach_feature']);
    const user = userEvent.setup();
    renderControls();

    expect(screen.getByTestId('gm-feature-11')).toHaveTextContent('Chandelier · Floor');
    await user.click(screen.getByRole('button', { name: 'Remove Chandelier from Floor' }));

    expect(mockDispatch).toHaveBeenCalledWith({
      ref: expect.objectContaining({ registry_key: 'gm_detach_feature', feature_id: 11 }),
      kwargs: {},
    });
  });

  it('toasts a refusal and does not refresh', async () => {
    withActions(['gm_attach_feature']);
    mockDispatch.mockResolvedValue({
      backend: 'registry',
      deferred: false,
      success: false,
      message: 'That square is outside Stage.',
    });
    const invalidate = vi.spyOn(client, 'invalidateQueries');
    const user = userEvent.setup();
    renderControls();

    await user.selectOptions(screen.getByLabelText('Place'), 'Stage');
    await user.selectOptions(screen.getByLabelText('Feature'), 'Rope');
    await user.click(screen.getByRole('button', { name: 'Add feature' }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('That square is outside Stage.'));
    expect(invalidate).not.toHaveBeenCalled();
  });

  it('says so when the feature types cannot be loaded', () => {
    withActions(['gm_attach_feature']);
    mockUseFeatureTypes.mockReturnValue({ data: undefined, isError: true });
    renderControls();

    expect(screen.getByRole('alert')).toHaveTextContent('Feature types could not be loaded.');
    expect(screen.getByRole('button', { name: 'Add feature' })).toBeDisabled();
  });
});
