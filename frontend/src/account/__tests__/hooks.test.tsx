/**
 * useReauthGuard hook tests (#3591 fix round 1).
 *
 * Verifies the waiter-array fix: overlapping run() calls each register their own waiter
 * while the dialog is open, and a single dialogProps.onSuccess()/onCancel() settles every
 * waiter, retrying (or rejecting) each caller's own call.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../api', async () => {
  const actual = await vi.importActual<typeof import('../api')>('../api');
  return { ...actual };
});

import { ReauthenticationRequiredError } from '../api';
import { useReauthGuard } from '../hooks';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function flakyFn(result: string) {
  return vi
    .fn()
    .mockRejectedValueOnce(new ReauthenticationRequiredError(['reauthenticate']))
    .mockResolvedValueOnce(result);
}

describe('useReauthGuard', () => {
  it('run retries once after dialogProps.onSuccess()', async () => {
    const { result } = renderHook(() => useReauthGuard(), { wrapper: wrapper() });
    const fn = flakyFn('ok');

    let promise!: Promise<string>;
    await act(async () => {
      promise = result.current.run(fn);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() => expect(result.current.dialogProps.open).toBe(true));
    expect(result.current.dialogProps.flows).toEqual(['reauthenticate']);

    act(() => {
      result.current.dialogProps.onSuccess();
    });

    await expect(promise).resolves.toBe('ok');
    expect(fn).toHaveBeenCalledTimes(2);
    expect(result.current.dialogProps.open).toBe(false);
  });

  it('two overlapping run calls both resolve after one onSuccess()', async () => {
    const { result } = renderHook(() => useReauthGuard(), { wrapper: wrapper() });
    const fn1 = flakyFn('first');
    const fn2 = flakyFn('second');

    let promise1!: Promise<string>;
    let promise2!: Promise<string>;
    await act(async () => {
      promise1 = result.current.run(fn1);
      promise2 = result.current.run(fn2);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() => expect(result.current.dialogProps.open).toBe(true));

    act(() => {
      result.current.dialogProps.onSuccess();
    });

    await expect(promise1).resolves.toBe('first');
    await expect(promise2).resolves.toBe('second');
    expect(fn1).toHaveBeenCalledTimes(2);
    expect(fn2).toHaveBeenCalledTimes(2);
  });

  it('onCancel() rejects both overlapping waiters', async () => {
    const { result } = renderHook(() => useReauthGuard(), { wrapper: wrapper() });
    const fn1 = flakyFn('first');
    const fn2 = flakyFn('second');

    let promise1!: Promise<string>;
    let promise2!: Promise<string>;
    await act(async () => {
      promise1 = result.current.run(fn1);
      promise2 = result.current.run(fn2);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(() => expect(result.current.dialogProps.open).toBe(true));

    act(() => {
      result.current.dialogProps.onCancel();
    });

    await expect(promise1).rejects.toThrow('Cancelled.');
    await expect(promise2).rejects.toThrow('Cancelled.');
    expect(fn1).toHaveBeenCalledTimes(1);
    expect(fn2).toHaveBeenCalledTimes(1);
    expect(result.current.dialogProps.open).toBe(false);
  });
});
