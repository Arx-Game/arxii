/**
 * KinshipPanel (#2062, #3003) — the character sheet's Kinship tab. Mocks the
 * feature's own hooks wholesale (the `friends/__tests__/FriendsTab.test.tsx`
 * idiom).
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
 * `sheet_id` and `roster_entry_id` default to values distinct from the node's own
 * Kinsperson id (`900 + id`, `500 + id`) — three deliberately different id spaces
 * (#3003, #4210). */
function node(
  overrides: Partial<KinspersonNode> & Pick<KinspersonNode, 'id' | 'name'>
): KinspersonNode {
  return {
    tier: 'name_only',
    family_id: null,
    is_deceased: false,
    is_appable: false,
    sheet_id: 900 + overrides.id,
    roster_entry_id: 500 + overrides.id,
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

/** A family as the tree payload carries it; `description` and `kind` are what the
 * panel reads beyond the name. */
function family(overrides: Partial<NonNullable<FamilyTree['family']>> = {}) {
  return {
    id: 1,
    name: 'Valardin',
    kind: { id: 1, name: 'Noble', styles_as_house: true },
    influence: 0,
    description: '',
    born_particle: '',
    taken_in_particle: '',
    standing: null,
    inherited: { aspects: [], features: [], liege_name: '' },
    ...overrides,
  } as NonNullable<FamilyTree['family']>;
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

/** The panel links a sheeted kinsperson to their sheet, so it needs a router. */
function renderPanel(characterId = 7) {
  return render(
    <MemoryRouter>
      <KinshipPanel characterId={characterId} />
    </MemoryRouter>
  );
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
      family: family(),
      nodes: [
        { id: 2, name: 'Aria' },
        { id: 3, name: 'Bel' },
      ],
      parentage: [],
      unions: [],
    });
    renderPanel();
    expect(screen.getByText('Aria')).toBeInTheDocument();
  });

  it('reads a house-styled family as a House, with its description under the line', () => {
    mockKinTree({
      family: family({ description: 'Old blood of the eastern marches.' }),
      nodes: [{ id: 2, name: 'Aria' }],
    });
    renderPanel();
    expect(screen.getByText('House Valardin')).toBeInTheDocument();
    expect(screen.getByText('Old blood of the eastern marches.')).toBeInTheDocument();
  });

  it('reads a commoner family by its bare name', () => {
    mockKinTree({
      family: family({
        name: 'Tallow',
        kind: { id: 2, name: 'Commoner', styles_as_house: false },
      }),
      nodes: [{ id: 2, name: 'Aria' }],
    });
    renderPanel();
    expect(screen.getByText('Tallow')).toBeInTheDocument();
    expect(screen.queryByText('House Tallow')).not.toBeInTheDocument();
  });

  it('draws no description line for a family without one', () => {
    mockKinTree({ family: family({ description: '' }), nodes: [{ id: 2, name: 'Aria' }] });
    const { container } = renderPanel();
    expect(container.querySelector('.refsheet-prose')).toBeNull();
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
    const { container } = renderPanel();
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
    const { container } = renderPanel();
    expect(container.querySelector('[data-believed-false="true"]')).toBeTruthy();
  });

  it('renders the familyless case', () => {
    mockKinTree({ family: null, nodes: [{ id: 2, name: 'Nobody' }], parentage: [], unions: [] });
    renderPanel();
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
    renderPanel();
    fireEvent.click(screen.getByText('Bel'));
    expect(screen.getByText(/cousin/i)).toBeInTheDocument();
  });

  it("links a sheeted kinsperson to their sheet by the roster entry's id", () => {
    // The sheet route takes a RosterEntry pk; `sheet_id` (903 here) is a different
    // id space and must never be the href (#4210).
    mockKinTree({
      nodes: [
        { id: 2, name: 'Aria' },
        { id: 3, name: 'Bel' },
      ],
    });
    renderPanel();
    fireEvent.click(screen.getByText('Bel'));
    expect(screen.getByRole('link', { name: 'Bel' })).toHaveAttribute('href', '/characters/503');
  });

  it('is honest about a node with no linked character record', () => {
    mockKinTree({
      nodes: [{ id: 2, name: 'Aria', sheet_id: null, roster_entry_id: null }],
      parentage: [],
      unions: [],
    });
    renderPanel();
    fireEvent.click(screen.getByText('Aria'));
    expect(useKinRelationship).toHaveBeenCalled();
    expect(screen.getByText(/nobody on the roster answers to this person/i)).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
