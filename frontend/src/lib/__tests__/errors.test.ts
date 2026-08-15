/** ApiError + throwApiError/readErrorDetail (2026-07 audit error-path fix). */
import { describe, expect, it } from 'vitest';

import {
  ApiError,
  extractErrorMessage,
  parseDispatchBody,
  readErrorDetail,
  throwApiError,
} from '../errors';

function jsonResponse(body: unknown, status = 400): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('throwApiError', () => {
  it('carries status and detail from a {detail} body', async () => {
    const err = await throwApiError(jsonResponse({ detail: 'Scene not found.' }, 404), 'fb').catch(
      (e: unknown) => e
    );
    expect(err).toBeInstanceOf(ApiError);
    const apiErr = err as ApiError;
    expect(apiErr.status).toBe(404);
    expect(apiErr.detail).toBe('Scene not found.');
    expect(apiErr.message).toBe('Scene not found.');
  });

  it('flattens DRF field errors into the message', async () => {
    const body = { name: ['This field may not be blank.'], tier: ['Must be positive.'] };
    const err = (await throwApiError(jsonResponse(body), 'fb').catch(
      (e: unknown) => e
    )) as ApiError;
    expect(err.fieldErrors).toEqual(body);
    expect(err.message).toBe('name: This field may not be blank.; tier: Must be positive.');
  });

  it('falls back on a non-JSON body but keeps the status', async () => {
    const res = new Response('<html>proxy error</html>', { status: 502 });
    const err = (await throwApiError(res, 'Failed to save.').catch((e: unknown) => e)) as ApiError;
    expect(err.status).toBe(502);
    expect(err.message).toBe('Failed to save.');
    expect(err.detail).toBeNull();
  });

  it('readErrorDetail is a status-carrying alias', async () => {
    const err = (await readErrorDetail(jsonResponse({ detail: 'Nope.' }, 403), 'fb').catch(
      (e: unknown) => e
    )) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(extractErrorMessage(err)).toBe('Nope.');
  });
});

/**
 * `parseDispatchBody` (#3155) — the shared parse hoisted out of the #2992
 * `dispatchTreasuryResult` fix so every dispatch caller that reduces a
 * `DispatchActionView` response to a message string applies the same
 * `success === false` check instead of re-copying the parse per module.
 */
describe('parseDispatchBody', () => {
  it('reads success and message off a business-rule rejection body (HTTP 200)', async () => {
    const res = jsonResponse({ success: false, message: 'Only members may do that.' }, 200);
    await expect(parseDispatchBody(res)).resolves.toEqual({
      success: false,
      message: 'Only members may do that.',
    });
  });

  it('reads success: true off a real success body', async () => {
    const res = jsonResponse({ success: true, message: 'Done.' }, 200);
    await expect(parseDispatchBody(res)).resolves.toEqual({ success: true, message: 'Done.' });
  });

  it('prefers detail over message when both are present', async () => {
    const res = jsonResponse({ success: false, detail: 'Detail wins.', message: 'Ignored.' });
    await expect(parseDispatchBody(res)).resolves.toEqual({
      success: false,
      message: 'Detail wins.',
    });
  });

  it('reads success: null and no message off a non-JSON body', async () => {
    const res = new Response('<html>proxy error</html>', { status: 502 });
    await expect(parseDispatchBody(res)).resolves.toEqual({ success: null, message: undefined });
  });
});
