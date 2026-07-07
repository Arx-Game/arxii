/**
 * OrgPage tests (#1446)
 *
 * Covers:
 *   1. Member case — query resolves an organization, name renders.
 *   2. Non-member / error case — query errors (members-only 404), the
 *      not-yet-public placeholder renders instead of crashing.
 *
 * Renders OrgPageInner directly (avoids router param plumbing), mirroring
 * the CovenantDetailPage test convention.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OrgPageInner } from './OrgPage';
import type { Organization } from '@/orgs/api';

vi.mock('@/orgs/queries', () => ({
  useOrganizationQuery: vi.fn(),
  useHouseFeedQuery: vi.fn(() => ({ data: [] })),
}));

import { useOrganizationQuery } from '@/orgs/queries';

const mockedUseOrganizationQuery = vi.mocked(useOrganizationQuery);

const ORG: Organization = {
  id: 7,
  name: 'The Gilded Compass',
  society_name: 'Merchant Society',
  org_type_name: 'Guild',
  ranks: [],
  house: null,
};

describe('OrgPageInner', () => {
  it('renders the organization name for a member', () => {
    mockedUseOrganizationQuery.mockReturnValue({
      data: ORG,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useOrganizationQuery>);

    render(<OrgPageInner orgId={7} />);

    expect(screen.getByText('The Gilded Compass')).toBeInTheDocument();
  });

  it('renders the not-yet-public placeholder on query error (non-member / 404)', () => {
    mockedUseOrganizationQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useOrganizationQuery>);

    render(<OrgPageInner orgId={7} />);

    expect(screen.getByText(/not yet public/i)).toBeInTheDocument();
  });

  it('renders the not-yet-public placeholder on an empty (falsy) result', () => {
    mockedUseOrganizationQuery.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useOrganizationQuery>);

    render(<OrgPageInner orgId={7} />);

    expect(screen.getByText(/not yet public/i)).toBeInTheDocument();
  });

  it('renders stylings, aspects, and features for a house org (#2079)', () => {
    const housedOrg: Organization = {
      ...ORG,
      name: 'House Maldrave',
      words: 'The Debt Is Kept',
      colors: 'oxblood and slate',
      sigil_description: 'A black key crossed with a sword.',
      house: {
        family_name: 'Maldrave',
        liege_name: 'The Crown',
        vassal_names: [],
        titles: [],
        domains: [],
        aspects: [
          {
            definition: 'Patron Deity',
            option: 'The Chained Judge',
            description: 'Keeper of debts.',
          },
        ],
        features: [
          {
            name: 'Black Ledger',
            slug: 'black-ledger',
            description: 'The sealed record of schemes, enemies, and prey.',
          },
        ],
      },
    };
    mockedUseOrganizationQuery.mockReturnValue({
      data: housedOrg,
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useOrganizationQuery>);

    render(<OrgPageInner orgId={7} />);

    expect(screen.getByText(/The Debt Is Kept/)).toBeInTheDocument();
    expect(screen.getByText(/oxblood and slate/)).toBeInTheDocument();
    expect(screen.getByText(/Patron Deity: The Chained Judge/)).toBeInTheDocument();
    expect(screen.getByText('Black Ledger')).toBeInTheDocument();
    expect(screen.getByText(/Ways of the House/)).toBeInTheDocument();
  });
});
