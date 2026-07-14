import { screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { AgreementsPanel } from '../components/AgreementsPanel';
import type { Will } from '../estatesQueries';

vi.mock('../estatesQueries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../estatesQueries')>()),
  useWillQuery: vi.fn(),
  useSettlementsQuery: vi.fn(),
  useClaimsQuery: vi.fn(),
  useWillMutations: vi.fn(),
}));
import {
  useClaimsQuery,
  useSettlementsQuery,
  useWillMutations,
  useWillQuery,
} from '../estatesQueries';

const mockWill = vi.mocked(useWillQuery);
const mockSettlements = vi.mocked(useSettlementsQuery);
const mockClaims = vi.mocked(useClaimsQuery);
const mockMutations = vi.mocked(useWillMutations);

const WILL: Will = {
  id: 1,
  character_sheet: 7,
  testament_text: 'To my heirs, everything.',
  updated_at: '2026-07-14T00:00:00Z',
  bequests: [],
  executors: [{ id: 3, will: 1, persona: 9, persona_name: 'Elara' }],
  is_frozen: false,
} as unknown as Will;

function setQueries({
  will = null,
  frozen = false,
  settlements = [],
  claims = [],
}: {
  will?: Will | null;
  frozen?: boolean;
  settlements?: unknown[];
  claims?: unknown[];
}) {
  const value = will ? { ...will, is_frozen: frozen } : null;
  mockWill.mockReturnValue({ data: value, isLoading: false } as unknown as ReturnType<
    typeof useWillQuery
  >);
  mockSettlements.mockReturnValue({ data: settlements } as unknown as ReturnType<
    typeof useSettlementsQuery
  >);
  mockClaims.mockReturnValue({ data: claims } as unknown as ReturnType<typeof useClaimsQuery>);
  mockMutations.mockReturnValue({
    createWill: { mutate: vi.fn(), isPending: false },
    updateTestament: { mutate: vi.fn(), isPending: false },
    addBequest: { mutate: vi.fn(), isPending: false },
    removeBequest: { mutate: vi.fn(), isPending: false },
    addExecutor: { mutate: vi.fn(), isPending: false },
    removeExecutor: { mutate: vi.fn(), isPending: false },
  } as unknown as ReturnType<typeof useWillMutations>);
}

describe('AgreementsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('invites writing a will when none exists', () => {
    setQueries({});
    renderWithProviders(<AgreementsPanel characterSheetId={7} />);
    expect(screen.getByText(/No will written/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Write will' })).toBeInTheDocument();
  });

  it('shows the sealed banner and disables editing once frozen', () => {
    setQueries({ will: WILL, frozen: true });
    renderWithProviders(<AgreementsPanel characterSheetId={7} />);
    expect(screen.getByText(/sealed/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Update testament' })).toBeDisabled();
  });

  it('lists executors and pending settlements awaiting the viewer', () => {
    setQueries({
      will: WILL,
      settlements: [
        {
          id: 5,
          character_sheet: 11,
          deceased_name: 'Fred',
          deadline: '2026-07-28T00:00:00Z',
          status: 'pending',
        },
      ],
    });
    renderWithProviders(<AgreementsPanel characterSheetId={7} />);
    expect(screen.getByText('Elara')).toBeInTheDocument();
    expect(screen.getByText(/Estates Awaiting You/)).toBeInTheDocument();
    expect(screen.getByText('Fred')).toBeInTheDocument();
  });
});
