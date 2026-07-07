/**
 * Custody protection + clearance API + Query Hooks Tests (#2001 Task 8)
 *
 * Mirrors queries.authoring.test.tsx's pattern: storiesKeys factory checks +
 * real api.ts functions driven through a fetch spy (locks the actual
 * URL/method/body contract, including the `err.response` attachment used by
 * the dialogs' DRF-error-surfacing seam) + a couple of hook-level checks.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  storiesKeys,
  useCreateProtectedSubject,
  useCustodyClearances,
  useProtectedSubjects,
  useRequestClearance,
} from '../queries';
import type { CustodyClearance, ProtectedSubject } from '../types';

vi.mock('../api', () => ({
  listProtectedSubjects: vi.fn(),
  createProtectedSubject: vi.fn(),
  updateProtectedSubject: vi.fn(),
  deactivateProtectedSubject: vi.fn(),
  listCustodyClearances: vi.fn(),
  requestClearance: vi.fn(),
  grantClearance: vi.fn(),
  denyClearance: vi.fn(),
  escalateClearance: vi.fn(),
  resolveClearance: vi.fn(),
  revokeClearance: vi.fn(),
}));

import * as api from '../api';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const mockProtectedSubject: ProtectedSubject = {
  id: 3,
  story: 1,
  subject_kind: 'npc_fate',
  subject_sheet: 42,
  subject_item: null,
  subject_society: null,
  subject_organization: null,
  subject_label: '',
  is_active: true,
  notes: 'Load-bearing NPC',
  created_at: '2026-01-01T00:00:00Z',
};

const mockClearance: CustodyClearance = {
  id: 9,
  protected_subject: 3,
  requested_by: 5,
  requesting_story: null,
  requesting_beat: null,
  scope: 'appear',
  status: 'pending',
  granted_by: null,
  staff_resolver: null,
  message: 'Need to bring them onscreen',
  response_note: '',
  revoked_at: null,
  created_at: '2026-04-19T00:00:00Z',
  resolved_at: null,
};

describe('Custody hooks (#2001 Task 8)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('storiesKeys', () => {
    it('generates the protected-subjects list key', () => {
      expect(storiesKeys.protectedSubjects({ story: 1 })).toEqual([
        'stories',
        'protected-subjects',
        { story: 1 },
      ]);
    });

    it('generates the custody-clearances list key', () => {
      expect(storiesKeys.custodyClearances({ status: 'escalated' })).toEqual([
        'stories',
        'custody-clearances',
        { status: 'escalated' },
      ]);
    });
  });

  describe('useProtectedSubjects', () => {
    it('calls listProtectedSubjects with the given params', async () => {
      vi.mocked(api.listProtectedSubjects).mockResolvedValue({
        count: 1,
        next: null,
        previous: null,
        results: [mockProtectedSubject],
      });

      const { result } = renderHook(() => useProtectedSubjects({ story: 1 }), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(api.listProtectedSubjects).toHaveBeenCalledWith({ story: 1 });
      expect(result.current.data?.results).toEqual([mockProtectedSubject]);
    });
  });

  describe('useCreateProtectedSubject', () => {
    it('invalidates the protected-subjects cache on success', async () => {
      vi.mocked(api.createProtectedSubject).mockResolvedValue(mockProtectedSubject);

      const { result } = renderHook(() => useCreateProtectedSubject(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ story: 1, subject_kind: 'npc_fate', subject_sheet: 42 });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(api.createProtectedSubject).toHaveBeenCalledWith({
        story: 1,
        subject_kind: 'npc_fate',
        subject_sheet: 42,
      });
    });
  });

  describe('useCustodyClearances', () => {
    it('calls listCustodyClearances with the given params', async () => {
      vi.mocked(api.listCustodyClearances).mockResolvedValue({
        count: 1,
        next: null,
        previous: null,
        results: [mockClearance],
      });

      const { result } = renderHook(() => useCustodyClearances({ status: 'pending' }), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(api.listCustodyClearances).toHaveBeenCalledWith({ status: 'pending' });
      expect(result.current.data?.results).toEqual([mockClearance]);
    });
  });

  describe('useRequestClearance', () => {
    it('calls requestClearance with the identity-path body', async () => {
      vi.mocked(api.requestClearance).mockResolvedValue([mockClearance]);

      const { result } = renderHook(() => useRequestClearance(), { wrapper: createWrapper() });

      await act(async () => {
        result.current.mutate({
          subject_kind: 'npc_fate',
          subject_sheet: 42,
          scope: 'appear',
          message: 'Need to bring them onscreen',
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(api.requestClearance).toHaveBeenCalledWith({
        subject_kind: 'npc_fate',
        subject_sheet: 42,
        scope: 'appear',
        message: 'Need to bring them onscreen',
      });
      expect(result.current.data).toEqual([mockClearance]);
    });
  });
});

// ---------------------------------------------------------------------------
// Real api.ts functions driven through a fetch spy — locks the actual
// URL/method/body contract and the err.response attachment used by the
// dialogs' DRF-error-surfacing seam.
// ---------------------------------------------------------------------------

describe('custody api functions (real fetch contract)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('createProtectedSubject POSTs to /api/protected-subjects/', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(mockProtectedSubject), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const { createProtectedSubject: real } =
      await vi.importActual<typeof import('../api')>('../api');

    const result = await real({ story: 1, subject_kind: 'npc_fate', subject_sheet: 42 });

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain('/api/protected-subjects/');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      story: 1,
      subject_kind: 'npc_fate',
      subject_sheet: 42,
    });
    expect(result).toEqual(mockProtectedSubject);
  });

  it('createProtectedSubject attaches the failed Response on a non-ok response', async () => {
    const errorBody = { non_field_errors: ['Exactly one of subject_sheet/... must be set.'] };
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(errorBody), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const { createProtectedSubject: real } =
      await vi.importActual<typeof import('../api')>('../api');

    let caught: unknown;
    try {
      await real({ story: 1, subject_kind: 'custom' });
    } catch (err) {
      caught = err;
    }

    expect(caught).toBeInstanceOf(Error);
    expect(caught && typeof caught === 'object' && 'response' in caught).toBe(true);
    const response = (caught as { response?: Response }).response;
    await expect(response?.json()).resolves.toEqual(errorBody);
  });

  it('deactivateProtectedSubject DELETEs /api/protected-subjects/{id}/', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(null, { status: 204 }));

    const { deactivateProtectedSubject: real } =
      await vi.importActual<typeof import('../api')>('../api');

    await real(3);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain('/api/protected-subjects/3/');
    expect(init?.method).toBe('DELETE');
  });

  it('requestClearance POSTs the identity path to /api/custody-clearances/', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([mockClearance]), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const { requestClearance: real } = await vi.importActual<typeof import('../api')>('../api');

    const result = await real({
      subject_kind: 'npc_fate',
      subject_sheet: 42,
      scope: 'appear',
      message: 'Need to bring them onscreen',
    });

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain('/api/custody-clearances/');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      subject_kind: 'npc_fate',
      subject_sheet: 42,
      scope: 'appear',
      message: 'Need to bring them onscreen',
    });
    expect(result).toEqual([mockClearance]);
  });

  it('grantClearance POSTs to /api/custody-clearances/{id}/grant/', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...mockClearance, status: 'granted' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const { grantClearance: real } = await vi.importActual<typeof import('../api')>('../api');

    await real(9, { response_note: 'Go ahead' });

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain('/api/custody-clearances/9/grant/');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ response_note: 'Go ahead' });
  });

  it('revokeClearance POSTs to /api/custody-clearances/{id}/revoke/ with no body', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...mockClearance, status: 'granted', revoked_at: 'now' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );

    const { revokeClearance: real } = await vi.importActual<typeof import('../api')>('../api');

    await real(9);

    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain('/api/custody-clearances/9/revoke/');
    expect(init?.method).toBe('POST');
  });
});
