/**
 * KinshipPanel (#2062, #3003) — the character sheet's Kinship tab. Mocks the
 * feature's own hooks wholesale (the `friends/__tests__/FriendsTab.test.tsx`
 * idiom).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { KinshipPanel } from '../components/KinshipPanel';
import type {
  FamilyTree,
  KinRelationship,
  KinspersonNode,
  ParentageEdge,
  UnionEdge,
} from '../types';

vi.mock('@/kinship/queries', () => ({
  useKinTree: vi.fn(),
  useKinRelationship: vi.fn(),
}));

import { useKinRelationship, useKinTree } from '@/kinship/queries';

const mockTreeQuery = vi.mocked(useKinTree);
const mockRelationshipQuery = vi.mocked(useKinRelationship);

/** Fills in the fields a test doesn't care about with harmless defaults. Note
 * `sheet_id` defaults to a value distinct from the node's own Kinsperson id
 * (`900 + id`) — the two are deliberately different id spaces (#3003). */
function node(
  overrides: Partial<KinspersonNode> & Pick<KinspersonNode, 'id' | 'name'>
): KinspersonNode {
  return {
    tier: 'name_only',
    family_id: null,
    is_deceased: false,
    is_appable: false,
    sheet_id: 900 + overrides.id,
    gender: '',
    age: null,
    description: '',
    ...overrides,
  };
}

function edge(
  overrides: Partial<ParentageEdge> & Pick<ParentageEdge, 'child_id' | 'parent_id'>
): ParentageEdge {
  return {
    kind: 'biological',
    is_true: true,
    via_secret: false,
    ...overrides,
  };
}

interface TreeFixture {
  family?: FamilyTree['family'];
  nodes: Array<Partial<KinspersonNode> & Pick<KinspersonNode, 'id' | 'name'>>;
  parentage?: Array<Partial<ParentageEdge> & Pick<ParentageEdge, 'child_id' | 'parent_id'>>;
  unions?: UnionEdge[];
}

function mockKinTree(fixture: TreeFixture): void {
  mockTreeQuery.mockReturnValue({
    data: {
      family: fixture.family ?? null,
      nodes: fixture.nodes.map(node),
      parentage: (fixture.parentage ?? []).map(edge),
      unions: fixture.unions ?? [],
    },
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useKinTree>);
}

function mockKinRelationship(payload: KinRelationship): void {
  mockRelationshipQuery.mockReturnValue({
    data: payload,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useKinRelationship>);
}

describe('KinshipPanel', () => {
  beforeEach(() => {
    // Explicit per-test reset (rather than relying on default vitest
    // isolation): `useKinRelationship`'s mocked return value must not leak
    // from a test that configures it (e.g. the "selected node" test) into
    // one that doesn't — give it a harmless default so a test that never
    // selects a node, or selects one with no relatable sheet, still gets a
    // safely destructurable result instead of a stale prior value.
    mockTreeQuery.mockReset();
    mockRelationshipQuery.mockReset();
    mockRelationshipQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useKinRelationship>);
  });

  it('renders kin nodes', () => {
    mockKinTree({
      family: {
        id: 1,
        name: 'Valardin',
        kind: { id: 1, name: 'Noble', styles_as_house: true },
        born_particle: '',
        taken_in_particle: '',
        inherited: { aspects: [], features: [], liege_name: '' },
      },
      nodes: [
        { id: 2, name: 'Aria' },
        { id: 3, name: 'Bel' },
      ],
      parentage: [],
      unions: [],
    });
    render(<KinshipPanel characterId={7} />);
    expect(screen.getByText('Aria')).toBeInTheDocument();
  });

  it('marks a secret-known edge distinctly', () => {
    mockKinTree({
      nodes: [
        { id: 2, name: 'Aria' },
        { id: 3, name: 'Bel' },
      ],
      parentage: [
        { child_id: 2, parent_id: 3, kind: 'biological', is_true: true, via_secret: true },
      ],
      unions: [],
    });
    const { container } = render(<KinshipPanel characterId={7} />);
    expect(container.querySelector('[data-via-secret="true"]')).toBeTruthy();
  });

  it('marks a believed-false edge distinctly', () => {
    mockKinTree({
      nodes: [
        { id: 2, name: 'Aria' },
        { id: 3, name: 'Bel' },
      ],
      parentage: [
        { child_id: 2, parent_id: 3, kind: 'biological', is_true: false, via_secret: false },
      ],
      unions: [],
    });
    const { container } = render(<KinshipPanel characterId={7} />);
    expect(container.querySelector('[data-believed-false="true"]')).toBeTruthy();
  });

  it('renders the familyless case', () => {
    mockKinTree({ family: null, nodes: [{ id: 2, name: 'Nobody' }], parentage: [], unions: [] });
    render(<KinshipPanel characterId={7} />);
    expect(screen.getByText('Nobody')).toBeInTheDocument();
  });

  it('shows the derived label when a node is selected', () => {
    mockKinTree({
      nodes: [
        { id: 2, name: 'Aria' },
        { id: 3, name: 'Bel' },
      ],
      parentage: [],
      unions: [],
    });
    mockKinRelationship({ label: 'cousin' });
    render(<KinshipPanel characterId={7} />);
    fireEvent.click(screen.getByText('Bel'));
    expect(screen.getByText(/cousin/i)).toBeInTheDocument();
  });

  it('is honest about a node with no linked character record', () => {
    mockKinTree({
      nodes: [{ id: 2, name: 'Aria', sheet_id: null }],
      parentage: [],
      unions: [],
    });
    render(<KinshipPanel characterId={7} />);
    fireEvent.click(screen.getByText('Aria'));
    expect(useKinRelationship).toHaveBeenCalled();
    expect(screen.getByText(/no linked character record/i)).toBeInTheDocument();
  });
});
