/**
 * GMSlot tests (#3478 task 5) — the Hall's GM/Staff operational tile,
 * rendered inside `CharactersBand`'s grid for a GM or staff account.
 * Mirrors `CharactersBand.test.tsx`'s provider/mock conventions.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GMSlot } from '../GMSlot';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { MyRosterEntry } from '@/roster/types';

interface MockAccount {
  is_gm?: boolean;
  is_staff?: boolean;
}

let mockAccount: MockAccount | null = null;

vi.mock('@/store/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/store/hooks')>();
  return {
    ...actual,
    useAccount: () => mockAccount,
  };
});

interface MockMineData {
  id: number;
  level: string;
  level_display: string;
  contact_times?: string;
  ooc_info?: string;
}

let mockMineData: MockMineData | undefined;

vi.mock('../queries', () => ({
  useGMProfileMineQuery: () => ({
    data: mockMineData,
    isLoading: false,
    isError: mockMineData === undefined,
  }),
  useMintGMCharacterMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateGMProfileMineMutation: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/game/personaQueries', () => ({
  useCharacterPersonasQuery: () => ({ data: [] }),
  useSetActivePersonaMutation: () => ({ mutate: vi.fn(), isPending: false }),
}));

const gmEntry: MyRosterEntry = {
  id: 10,
  name: 'Warden Vex',
  character_id: 99,
  profile_picture_url: null,
  primary_persona_id: null,
  active_persona_id: null,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'GM',
};

const approvedMineData: MockMineData = {
  id: 1,
  level: 'apprentice',
  level_display: 'Apprentice',
  contact_times: '',
  ooc_info: '',
};

describe('GMSlot', () => {
  afterEach(() => {
    mockAccount = null;
    mockMineData = undefined;
    vi.clearAllMocks();
  });

  it('renders nothing for a non-GM non-staff account', () => {
    mockAccount = { is_gm: false, is_staff: false };
    const { container } = renderWithProviders(
      <GMSlot gmEntry={undefined} isDocked={false} onSelect={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a "Create GM Profile" plate for a GM account with no GM entry', () => {
    mockAccount = { is_gm: true, is_staff: false };
    renderWithProviders(<GMSlot gmEntry={undefined} isDocked={false} onSelect={vi.fn()} />);
    expect(screen.getByTestId('create-gm-profile')).toBeInTheDocument();
  });

  it('renders a "Create GM Profile" plate for a staff account with no GM entry', () => {
    mockAccount = { is_gm: false, is_staff: true };
    renderWithProviders(<GMSlot gmEntry={undefined} isDocked={false} onSelect={vi.fn()} />);
    expect(screen.getByTestId('create-gm-profile')).toBeInTheDocument();
  });

  it('clicking "Create GM Profile" opens the create dialog', async () => {
    const user = userEvent.setup();
    mockAccount = { is_gm: true };
    renderWithProviders(<GMSlot gmEntry={undefined} isDocked={false} onSelect={vi.fn()} />);

    await user.click(screen.getByTestId('create-gm-profile'));

    expect(screen.getByRole('heading', { name: 'Create GM Profile' })).toBeInTheDocument();
  });

  it('renders the GM card with name, "(GM)" chip, and edit affordance when an entry exists', () => {
    mockAccount = { is_gm: true };
    mockMineData = approvedMineData;
    renderWithProviders(<GMSlot gmEntry={gmEntry} isDocked={false} onSelect={vi.fn()} />);

    expect(screen.getByText('Warden Vex')).toBeInTheDocument();
    expect(screen.getByText('(GM)')).toBeInTheDocument();
    expect(screen.getByTestId('edit-gm-profile')).toBeInTheDocument();
  });

  it('hides the edit affordance when `mine` 404s (staff without an approved GMProfile)', () => {
    mockAccount = { is_staff: true };
    mockMineData = undefined;
    renderWithProviders(
      <GMSlot
        gmEntry={{ ...gmEntry, character_type: 'STAFF' }}
        isDocked={false}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByText('Warden Vex')).toBeInTheDocument();
    expect(screen.queryByTestId('edit-gm-profile')).not.toBeInTheDocument();
  });

  it('renders nothing for a non-GM non-staff account even when a GM entry is passed', () => {
    mockAccount = { is_gm: false, is_staff: false };
    const { container } = renderWithProviders(
      <GMSlot gmEntry={gmEntry} isDocked={false} onSelect={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('selecting the card fires onSelect with the GM entry', async () => {
    const user = userEvent.setup();
    mockAccount = { is_gm: true };
    mockMineData = approvedMineData;
    const onSelect = vi.fn();
    renderWithProviders(<GMSlot gmEntry={gmEntry} isDocked={false} onSelect={onSelect} />);

    await user.click(screen.getByText('Warden Vex'));

    expect(onSelect).toHaveBeenCalledWith(gmEntry);
  });

  it('links to the existing Tables page rather than duplicating it', () => {
    mockAccount = { is_gm: true };
    mockMineData = approvedMineData;
    renderWithProviders(<GMSlot gmEntry={gmEntry} isDocked={false} onSelect={vi.fn()} />);

    expect(screen.getByRole('link', { name: /tables/i })).toHaveAttribute('href', '/tables');
  });

  it('clicking the edit affordance opens the edit dialog', async () => {
    const user = userEvent.setup();
    mockAccount = { is_gm: true };
    mockMineData = approvedMineData;
    renderWithProviders(<GMSlot gmEntry={gmEntry} isDocked={false} onSelect={vi.fn()} />);

    await user.click(screen.getByTestId('edit-gm-profile'));

    expect(screen.getByRole('heading', { name: 'Edit GM Profile' })).toBeInTheDocument();
  });
});
