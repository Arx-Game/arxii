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
}));

import { useOrganizationQuery } from '@/orgs/queries';

const mockedUseOrganizationQuery = vi.mocked(useOrganizationQuery);

const ORG: Organization = {
  id: 7,
  name: 'The Gilded Compass',
  society_name: 'Merchant Society',
  org_type_name: 'Guild',
  ranks: [],
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
});
