/**
 * faceQueries tests (#4889): what a pick, an upload and a removal send for a mask and for an
 * alternate self, and that a refusal's own words reach the caller. `apiFetch` answers by exact
 * URL, so a request to any other path fails the test instead of being swallowed.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useFacePortraitMutation, type FaceTarget, type PortraitChange } from '../faceQueries';

const PERSONA_URL = '/api/personas/set-portrait/';
const FORM_URL = '/api/forms/alternate-selves/21/set-portrait/';

const mockApiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

function answerWith(response: unknown) {
  mockApiFetch.mockImplementation(async (url: string) => {
    if (url !== PERSONA_URL && url !== FORM_URL) throw new Error(`unexpected request to ${url}`);
    return response;
  });
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

async function send(target: FaceTarget, change: PortraitChange) {
  const { result } = renderHook(() => useFacePortraitMutation(7), { wrapper: createWrapper() });
  act(() => {
    result.current.mutate({ target, change });
  });
  await waitFor(() => expect(result.current.isSuccess || result.current.isError).toBe(true));
  return result.current;
}

const persona: FaceTarget = { kind: 'persona', personaId: 11 };
const alternate: FaceTarget = { kind: 'alternate', alternateSelfId: 21 };

describe('useFacePortraitMutation', () => {
  beforeEach(() => answerWith({ ok: true, status: 200, json: async () => ({}) }));
  afterEach(() => vi.clearAllMocks());

  it.each([
    [
      'a pick on a mask',
      persona,
      { kind: 'pick', mediaId: 5 },
      PERSONA_URL,
      { persona_id: 11, media_id: 5 },
    ],
    [
      'a removal on a mask',
      persona,
      { kind: 'clear' },
      PERSONA_URL,
      { persona_id: 11, clear: true },
    ],
    ['a pick on a form', alternate, { kind: 'pick', mediaId: 5 }, FORM_URL, { media_id: 5 }],
    ['a removal on a form', alternate, { kind: 'clear' }, FORM_URL, { clear: true }],
  ] as const)('sends %s as JSON to its own URL', async (_name, target, change, url, body) => {
    await send(target, change);

    expect(mockApiFetch).toHaveBeenCalledTimes(1);
    const [calledUrl, init] = mockApiFetch.mock.calls[0];
    expect(calledUrl).toBe(url);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual(body);
  });

  it.each([
    ['a mask', persona, PERSONA_URL, ['persona_id', 'image_file']],
    ['a form', alternate, FORM_URL, ['image_file']],
  ] as const)(
    'sends an upload on %s as FormData with no JSON content type',
    async (_n, target, url, keys) => {
      const file = new File(['x'], 'owl.png', { type: 'image/png' });

      await send(target, { kind: 'upload', file });

      const [calledUrl, init] = mockApiFetch.mock.calls[0];
      expect(calledUrl).toBe(url);
      expect(init.method).toBe('POST');
      expect(init.body).toBeInstanceOf(FormData);
      expect([...(init.body as FormData).keys()].sort()).toEqual([...keys].sort());
      expect((init.body as FormData).get('image_file')).toBe(file);
      expect(init.headers?.['Content-Type']).toBeUndefined();
    }
  );

  it("surfaces the refusal's own words when the reply is a 400 with a detail list", async () => {
    answerWith({
      ok: false,
      status: 400,
      json: async () => ({ detail: ['This upload would exceed your media quota.'] }),
    });

    const hook = await send(persona, { kind: 'clear' });

    expect(hook.isError).toBe(true);
    expect(hook.error?.message).toBe('This upload would exceed your media quota.');
  });
});
