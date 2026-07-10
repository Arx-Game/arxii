/**
 * GroupStoryRequestPanel Tests (#2119)
 *
 * Covers:
 *   1. Hidden entirely for a non-recruiter viewer when there's no open request.
 *   2. "Request a GM" control shown for a can_request_gm viewer with no open request;
 *      submitting dispatches useRequestGMForCovenant.
 *   3. An open request renders its message; Withdraw shown only for can_request_gm.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import { GroupStoryRequestPanel } from '../GroupStoryRequestPanel';
import type { GroupStoryRequest, ViewerCapabilities } from '@/covenants/api';

vi.mock('@/covenants/queries', () => ({
  useCovenantGroupStoryRequest: vi.fn(),
  useRequestGMForCovenant: vi.fn(),
  useWithdrawGroupStoryRequest: vi.fn(),
}));

import {
  useCovenantGroupStoryRequest,
  useRequestGMForCovenant,
  useWithdrawGroupStoryRequest,
} from '@/covenants/queries';

const NO_CAPS: ViewerCapabilities = {
  can_invite: false,
  can_kick: false,
  can_manage_ranks: false,
  can_request_gm: false,
};

const RECRUITER_CAPS: ViewerCapabilities = { ...NO_CAPS, can_request_gm: true };

function mockNoOpenRequest(isLoading = false) {
  vi.mocked(useCovenantGroupStoryRequest).mockReturnValue({
    data: isLoading ? undefined : null,
    isLoading,
  } as never);
}

function mockOpenRequest(overrides: Partial<GroupStoryRequest> = {}) {
  const request: GroupStoryRequest = {
    id: 1,
    covenant: 7,
    requested_by_account: 1,
    message: 'Seeking a GM for grand adventures!',
    status: 'pending',
    claimed_by: null,
    created_story: null,
    created_at: '2026-07-08T00:00:00Z',
    responded_at: null,
    updated_at: '2026-07-08T00:00:00Z',
    ...overrides,
  };
  vi.mocked(useCovenantGroupStoryRequest).mockReturnValue({
    data: request,
    isLoading: false,
  } as never);
}

describe('GroupStoryRequestPanel', () => {
  const requestMutate = vi.fn();
  const withdrawMutate = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useRequestGMForCovenant).mockReturnValue({
      mutate: requestMutate,
      isPending: false,
    } as never);
    vi.mocked(useWithdrawGroupStoryRequest).mockReturnValue({
      mutate: withdrawMutate,
      isPending: false,
    } as never);
  });

  it('renders nothing for a non-recruiter viewer with no open request', () => {
    mockNoOpenRequest();

    const { container } = render(
      <GroupStoryRequestPanel covenantId={7} viewerCapabilities={NO_CAPS} actorCharacterId={42} />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the Request a GM control for a recruiter with no open request', () => {
    mockNoOpenRequest();

    render(
      <GroupStoryRequestPanel
        covenantId={7}
        viewerCapabilities={RECRUITER_CAPS}
        actorCharacterId={42}
      />
    );

    expect(screen.getByTestId('request-gm-button')).toBeInTheDocument();
  });

  it('dispatches the request on submit', () => {
    mockNoOpenRequest();

    render(
      <GroupStoryRequestPanel
        covenantId={7}
        viewerCapabilities={RECRUITER_CAPS}
        actorCharacterId={42}
      />
    );

    fireEvent.click(screen.getByTestId('request-gm-button'));
    fireEvent.change(screen.getByLabelText(/message to prospective gms/i), {
      target: { value: 'We need help!' },
    });
    fireEvent.click(screen.getByTestId('submit-gm-request-button'));

    expect(requestMutate).toHaveBeenCalledWith('We need help!', expect.anything());
  });

  it('shows the open request message and Withdraw control for a recruiter', () => {
    mockOpenRequest();

    render(
      <GroupStoryRequestPanel
        covenantId={7}
        viewerCapabilities={RECRUITER_CAPS}
        actorCharacterId={42}
      />
    );

    expect(screen.getByTestId('open-gm-request')).toHaveTextContent(
      'Seeking a GM for grand adventures!'
    );
    expect(screen.getByTestId('withdraw-gm-request-button')).toBeInTheDocument();
  });

  it('shows the open request without a Withdraw control for a non-recruiter viewer', () => {
    mockOpenRequest();

    render(
      <GroupStoryRequestPanel covenantId={7} viewerCapabilities={NO_CAPS} actorCharacterId={42} />
    );

    expect(screen.getByTestId('open-gm-request')).toBeInTheDocument();
    expect(screen.queryByTestId('withdraw-gm-request-button')).not.toBeInTheDocument();
  });

  it('withdraws on click', () => {
    mockOpenRequest({ id: 99 });

    render(
      <GroupStoryRequestPanel
        covenantId={7}
        viewerCapabilities={RECRUITER_CAPS}
        actorCharacterId={42}
      />
    );

    fireEvent.click(screen.getByTestId('withdraw-gm-request-button'));
    expect(withdrawMutate).toHaveBeenCalledWith(99);
  });
});
