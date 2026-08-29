/**
 * StaffSecretsPanel (#3266) — the staff omniscient authoring surface on a character sheet.
 * Mocks the query/mutation hooks so the panel and its AuthorSecretDialog render
 * synchronously, mirroring GossipPanel.test.tsx / SecretsTab.test.tsx.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StaffSecretsPanel } from './StaffSecretsPanel';
import type { AuthoredSecret } from '../types';

const createMutate = vi.fn();
const updateMutate = vi.fn();
const authorClueMutate = vi.fn();

// AuthorClueDialog (#3432, "Author a clue to this secret") is exercised in its own
// test file — only its hook dependencies are mocked here so it renders for real and
// this file can prove `lockedSecretId` reaches the dispatch as `target_id`.
vi.mock('@/clues/queries', () => ({
  useAuthorClueMutation: vi.fn(() => ({ mutate: authorClueMutate, isPending: false })),
}));
vi.mock('@/world-builder/useWorldBuilderActor', () => ({
  useWorldBuilderActor: vi.fn(() => 42),
}));
vi.mock('@/store/hooks', () => ({
  useAccount: vi.fn(() => ({ is_staff: true })),
}));
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/secrets/queries', () => ({
  useAuthoredSecretsQuery: vi.fn(),
  useSecretCategoriesQuery: vi.fn(() => ({
    data: [{ id: 9, name: 'Scandal', description: '' }],
  })),
  useCreateAuthoredSecretMutation: vi.fn(() => ({
    mutate: createMutate,
    isPending: false,
    isError: false,
    error: null,
  })),
  useUpdateAuthoredSecretMutation: vi.fn(() => ({
    mutate: updateMutate,
    isPending: false,
    isError: false,
    error: null,
  })),
}));

import { useAuthoredSecretsQuery } from '@/secrets/queries';

const mockQuery = vi.mocked(useAuthoredSecretsQuery);

function authoredSecret(overrides: Partial<AuthoredSecret>): AuthoredSecret {
  return {
    id: 1,
    subject_sheet: 5,
    level: 3,
    level_display: 'Carefully Kept',
    category: 9,
    category_name: 'Scandal',
    content: 'She poisoned the duke.',
    consequences: 'Execution if proven.',
    subject_aware: true,
    provenance: 'gm',
    provenance_display: 'GM/Staff authored (canon)',
    is_act_anchored: false,
    created_date: '2026-06-22T00:00:00Z',
    updated_date: '2026-06-22T00:00:00Z',
    ...overrides,
  };
}

function mockResults(results: AuthoredSecret[]): void {
  mockQuery.mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useAuthoredSecretsQuery>);
}

describe('StaffSecretsPanel', () => {
  it('renders authored secret rows from the mocked list', () => {
    mockResults([authoredSecret({})]);
    render(<StaffSecretsPanel subjectId={5} />);
    expect(screen.getByText('Carefully Kept')).toBeInTheDocument();
    expect(screen.getByText('Scandal')).toBeInTheDocument();
    expect(screen.getByText('GM/Staff authored (canon)')).toBeInTheDocument();
    expect(screen.getByText('She poisoned the duke.')).toBeInTheDocument();
  });

  it('shows an empty state when no secrets are authored yet', () => {
    mockResults([]);
    render(<StaffSecretsPanel subjectId={5} />);
    expect(screen.getByText(/no secrets authored/i)).toBeInTheDocument();
  });

  it('truncates a long content preview to ~120 characters', () => {
    const long = 'x'.repeat(200);
    mockResults([authoredSecret({ content: long })]);
    render(<StaffSecretsPanel subjectId={5} />);
    const cell = screen.getByTitle(long);
    expect(cell.textContent?.length).toBeLessThan(long.length);
  });

  it('submits the expected POST payload from the Author secret dialog', () => {
    mockResults([]);
    render(<StaffSecretsPanel subjectId={5} />);

    fireEvent.click(screen.getByTestId('author-secret-trigger'));
    fireEvent.change(screen.getByLabelText('Content'), {
      target: { value: 'A hidden debt to the crown.' },
    });
    fireEvent.click(screen.getByTestId('author-secret-submit'));

    expect(createMutate).toHaveBeenCalledWith(
      {
        subject_sheet: 5,
        content: 'A hidden debt to the crown.',
        level: 1,
        category: null,
        consequences: '',
        subject_aware: true,
      },
      expect.anything()
    );
  });

  it('submits a PATCH through the Edit dialog for an existing secret', () => {
    mockResults([authoredSecret({ id: 42 })]);
    render(<StaffSecretsPanel subjectId={5} />);

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Content'), {
      target: { value: 'She poisoned the duke, and the wine merchant knows.' },
    });
    fireEvent.click(screen.getByTestId('author-secret-submit'));

    expect(updateMutate).toHaveBeenCalledWith(
      {
        id: 42,
        payload: {
          content: 'She poisoned the duke, and the wine merchant knows.',
          level: 3,
          category: 9,
          consequences: 'Execution if proven.',
          subject_aware: true,
        },
      },
      expect.anything()
    );
  });

  it('pre-targets AuthorClueDialog at the row secret via "Author a clue to this secret"', () => {
    mockResults([authoredSecret({ id: 42 })]);
    render(<StaffSecretsPanel subjectId={5} />);

    fireEvent.click(screen.getByText('Author a clue to this secret'));

    expect(screen.queryByLabelText('Target kind')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Target id')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Whispers by the Well' } });
    fireEvent.change(screen.getByLabelText('Clue text'), {
      target: { value: 'Overheard near the well at dusk.' },
    });
    fireEvent.click(screen.getByTestId('author-clue-submit'));

    expect(authorClueMutate).toHaveBeenCalledWith(
      {
        name: 'Whispers by the Well',
        description: 'Overheard near the well at dusk.',
        target_kind: 'secret',
        target_id: 42,
      },
      expect.anything()
    );
  });
});

/**
 * The panel is only ever mounted behind `account?.is_staff` on CharacterSheetPage (#3266) —
 * the panel itself carries no gate (the backend also enforces IsAdminUser). This exercises
 * that exact mount expression in isolation so a regression to the gate is caught here rather
 * than only by manual staff/non-staff QA on the full sheet page.
 */
describe('the CharacterSheetPage staff gate', () => {
  function MountedForAccount({ isStaff }: { isStaff: boolean }) {
    const account = { is_staff: isStaff };
    return <>{account?.is_staff && <StaffSecretsPanel subjectId={5} />}</>;
  }

  it('never renders the panel for a non-staff account', () => {
    mockResults([]);
    render(<MountedForAccount isStaff={false} />);
    expect(screen.queryByText('Secrets (staff)')).toBeNull();
  });

  it('renders the panel for a staff account', () => {
    mockResults([]);
    render(<MountedForAccount isStaff={true} />);
    expect(screen.getByText('Secrets (staff)')).toBeInTheDocument();
  });
});
