/**
 * NPCRoleEditorPage — AddOfferForm's clue_reveal branch (#3428).
 *
 * Scoped to the new kind: the widened kind union, the "Clue Reveal"
 * SelectItem, the clue-slug field it reveals, and the details-create branch
 * (createOffer succeeds -> createClueDetails.mutate({offer, clue: slug})).
 * Every other kind's own behavior (mission/permit) is exercised elsewhere;
 * this file only proves clue_reveal didn't regress the shared submit path.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { NPCRoleEditorPage } from './NPCRoleEditorPage';
import * as queries from '../queries';
import type { NPCRole } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

// Radix Select is flaky under jsdom (portals/pointer capture) — every editor
// test in this codebase swaps it for a plain native <select> instead
// (see boundaries/__tests__/PlayerBoundaryFormDialog.test.tsx for the
// established pattern this mirrors).
vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
    disabled,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
    disabled?: boolean;
  }) => (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onValueChange?.(e.target.value)}
      data-testid="mock-select"
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useParams: () => ({ id: '7' }), useNavigate: () => vi.fn() };
});

vi.mock('@/missions/queries', () => ({
  useMissionTemplates: vi.fn(() => ({
    data: { count: 0, next: null, previous: null, results: [] },
  })),
  usePredicateLeaves: vi.fn(() => ({ data: [], isSuccess: true })),
}));

// Explicit factory (not automock) — matches this codebase's established
// react-query-hook mocking convention (see PlayerBoundaryFormDialog.test.tsx).
vi.mock('../queries', () => ({
  useRoles: vi.fn(),
  useRole: vi.fn(),
  useOffersForRole: vi.fn(),
  useMissionDetailsForRole: vi.fn(),
  useCreateRole: vi.fn(),
  usePatchRole: vi.fn(),
  useDeleteRole: vi.fn(),
  usePermitDetailsForRole: vi.fn(),
  useCreatePermitDetails: vi.fn(),
  usePatchPermitDetails: vi.fn(),
  useCreateOffer: vi.fn(),
  usePatchOffer: vi.fn(),
  useDeleteOffer: vi.fn(),
  useCreateMissionDetails: vi.fn(),
  usePatchMissionDetails: vi.fn(),
  useClueDetailsForRole: vi.fn(),
  useCreateClueDetails: vi.fn(),
  usePatchClueDetails: vi.fn(),
}));

const ROLE: NPCRole = {
  id: 7,
  name: 'Threshold Warden',
  description: '',
  default_description_template: '',
  default_rapport_starting_value: 0,
  faction_affiliation: null,
  is_active: true,
};

const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };

function mockNoOpMutation() {
  return { mutate: vi.fn(), isPending: false, isError: false, error: undefined } as unknown;
}

describe('NPCRoleEditorPage — AddOfferForm clue_reveal branch', () => {
  let createOfferMutate: ReturnType<typeof vi.fn>;
  let createClueDetailsMutate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(queries.useRole).mockReturnValue({ data: ROLE, isLoading: false } as ReturnType<
      typeof queries.useRole
    >);
    vi.mocked(queries.usePatchRole).mockReturnValue(
      mockNoOpMutation() as ReturnType<typeof queries.usePatchRole>
    );
    vi.mocked(queries.useDeleteRole).mockReturnValue(
      mockNoOpMutation() as ReturnType<typeof queries.useDeleteRole>
    );
    vi.mocked(queries.useOffersForRole).mockReturnValue({
      data: EMPTY_PAGE,
      isLoading: false,
    } as ReturnType<typeof queries.useOffersForRole>);
    vi.mocked(queries.useMissionDetailsForRole).mockReturnValue({
      data: EMPTY_PAGE,
    } as ReturnType<typeof queries.useMissionDetailsForRole>);
    vi.mocked(queries.usePermitDetailsForRole).mockReturnValue({
      data: EMPTY_PAGE,
    } as ReturnType<typeof queries.usePermitDetailsForRole>);
    vi.mocked(queries.useClueDetailsForRole).mockReturnValue({
      data: EMPTY_PAGE,
    } as ReturnType<typeof queries.useClueDetailsForRole>);
    vi.mocked(queries.useCreateMissionDetails).mockReturnValue(
      mockNoOpMutation() as ReturnType<typeof queries.useCreateMissionDetails>
    );
    vi.mocked(queries.useDeleteOffer).mockReturnValue(
      mockNoOpMutation() as ReturnType<typeof queries.useDeleteOffer>
    );

    createOfferMutate = vi.fn();
    vi.mocked(queries.useCreateOffer).mockReturnValue({
      mutate: createOfferMutate,
      isPending: false,
      isError: false,
      error: undefined,
    } as unknown as ReturnType<typeof queries.useCreateOffer>);

    createClueDetailsMutate = vi.fn();
    vi.mocked(queries.useCreateClueDetails).mockReturnValue({
      mutate: createClueDetailsMutate,
      isPending: false,
      isError: false,
      error: undefined,
    } as unknown as ReturnType<typeof queries.useCreateClueDetails>);
  });

  // Scoped to the AddOfferForm's own subtree (data-testid="add-offer-form") — the
  // page also renders RoleFieldsCard's Name/Description/Template textboxes above
  // it, so an unscoped getAllByRole('textbox') would pick those up too.
  async function openAddOfferForm() {
    renderWithProviders(<NPCRoleEditorPage />);
    await userEvent.click(await screen.findByRole('button', { name: /add offer/i }));
    return within(screen.getByTestId('add-offer-form'));
  }

  it('reveals the clue-slug field once Clue Reveal is picked as the kind', async () => {
    const form = await openAddOfferForm();

    expect(form.queryByPlaceholderText('torn-letter')).not.toBeInTheDocument();

    const kindSelect = form.getAllByTestId('mock-select')[0];
    await userEvent.selectOptions(kindSelect, 'clue_reveal');

    expect(form.getByPlaceholderText('torn-letter')).toBeInTheDocument();
  });

  it('keeps Add disabled until both a label and a clue slug are entered', async () => {
    const form = await openAddOfferForm();

    const kindSelect = form.getAllByTestId('mock-select')[0];
    await userEvent.selectOptions(kindSelect, 'clue_reveal');

    const addButton = form.getByRole('button', { name: /^add$/i });
    expect(addButton).toBeDisabled();

    await userEvent.type(form.getByPlaceholderText('torn-letter'), 'lantern-signal');
    expect(addButton).toBeDisabled();

    // Label lives in the generic Field the way every kind shares — no
    // placeholder, so it's the plain textbox left after the slug field.
    const inputs = form.getAllByRole('textbox');
    const labelInput = inputs.find((el) => el !== form.getByPlaceholderText('torn-letter'));
    await userEvent.type(labelInput as HTMLElement, 'Ask about the smugglers');

    expect(addButton).toBeEnabled();
  });

  it('creates the offer then the clue-reveal details with the new offer id + slug', async () => {
    createOfferMutate.mockImplementation((_body, opts) => {
      opts.onSuccess({ id: 99, role: 7, kind: 'clue_reveal', label: 'Ask about the smugglers' });
    });

    const form = await openAddOfferForm();

    const kindSelect = form.getAllByTestId('mock-select')[0];
    await userEvent.selectOptions(kindSelect, 'clue_reveal');

    const slugInput = form.getByPlaceholderText('torn-letter');
    await userEvent.type(slugInput, 'lantern-signal');
    const inputs = form.getAllByRole('textbox');
    const labelInput = inputs.find((el) => el !== slugInput) as HTMLElement;
    await userEvent.type(labelInput, 'Ask about the smugglers');

    await userEvent.click(form.getByRole('button', { name: /^add$/i }));

    expect(createOfferMutate).toHaveBeenCalledWith(
      { role: 7, kind: 'clue_reveal', label: 'Ask about the smugglers' },
      expect.anything()
    );
    expect(createClueDetailsMutate).toHaveBeenCalledWith(
      { offer: 99, clue: 'lantern-signal' },
      expect.anything()
    );
  });
});
