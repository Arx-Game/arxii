/**
 * SecretsTab (#1334) — the secret tab renders known secrets, and any layer the viewer hasn't
 * unlocked (which the backend returns as "Unknown") shows as such. Mocks the query hook so the
 * tab sees its data synchronously.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SecretsTab } from '../components/SecretsTab';
import type { KnownSecret } from '../types';

vi.mock('@/secrets/queries', () => ({
  useKnownSecretsQuery: vi.fn(),
  useGrievanceOptionsQuery: vi.fn(() => ({
    data: [{ id: 1, label: 'Furious Revelation', points: 1000, track: 'Enemies' }],
  })),
  useSubmitGrievanceMutation: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
  })),
}));

import { useKnownSecretsQuery } from '@/secrets/queries';

const mockQuery = vi.mocked(useKnownSecretsQuery);

function mockResults(results: KnownSecret[]): void {
  mockQuery.mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useKnownSecretsQuery>);
}

function secret(overrides: Partial<KnownSecret>): KnownSecret {
  return {
    id: 1,
    level: 'Carefully Kept',
    content: 'A fact.',
    provenance: 'GM/Staff authored (canon)',
    found_at: '2026-06-22T00:00:00Z',
    subject: 'Lady Vyper',
    category: 'Scandal',
    consequences: 'Execution if proven.',
    author: 'GM/Staff',
    can_grieve: false,
    anchored_to: [],
    ...overrides,
  };
}

describe('SecretsTab', () => {
  it('shows a known secret with its fact and level', () => {
    mockResults([secret({ content: 'She poisoned the duke.', level: 'Dangerous Secret' })]);
    render(<SecretsTab subjectId={5} viewerId={7} />);
    expect(screen.getByText('She poisoned the duke.')).toBeInTheDocument();
    expect(screen.getByText('Dangerous Secret')).toBeInTheDocument();
  });

  it('renders locked layers as "Unknown"', () => {
    mockResults([secret({ category: 'Unknown', consequences: 'Unknown' })]);
    render(<SecretsTab subjectId={5} viewerId={7} />);
    // Both the category and consequences layers read "Unknown".
    expect(screen.getAllByText('Unknown')).toHaveLength(2);
  });

  it('shows the unlocked values when the viewer knows the layers', () => {
    mockResults([secret({ category: 'Scandal', consequences: 'Execution if proven.' })]);
    render(<SecretsTab subjectId={5} viewerId={7} />);
    expect(screen.getByText('Scandal')).toBeInTheDocument();
    expect(screen.getByText('Execution if proven.')).toBeInTheDocument();
  });

  it('shows an empty state when no secrets are known', () => {
    mockResults([]);
    render(<SecretsTab subjectId={5} viewerId={7} />);
    expect(screen.getByText(/know no secrets/i)).toBeInTheDocument();
  });

  it('prompts to pick a character when none is active', () => {
    mockResults([]);
    render(<SecretsTab subjectId={5} viewerId={null} />);
    expect(screen.getByText(/select a character/i)).toBeInTheDocument();
  });

  it('offers a grievance response on a secret the viewer is wronged by (#1429)', () => {
    mockResults([secret({ can_grieve: true })]);
    render(<SecretsTab subjectId={5} viewerId={7} />);
    expect(screen.getByText(/respond to this wrong/i)).toBeInTheDocument();
  });

  it('hides the grievance response when the viewer is not a wronged party', () => {
    mockResults([secret({ can_grieve: false })]);
    render(<SecretsTab subjectId={5} viewerId={7} />);
    expect(screen.queryByText(/respond to this wrong/i)).toBeNull();
  });

  it('shows the act a secret is the truth behind (#1573)', () => {
    mockResults([secret({ anchored_to: [{ kind: 'legend', label: 'the Duel at Dawn' }] })]);
    render(<SecretsTab subjectId={5} viewerId={7} />);
    expect(screen.getByText(/truth behind/i)).toBeInTheDocument();
    expect(screen.getByText(/Duel at Dawn/)).toBeInTheDocument();
  });
});
