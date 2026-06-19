import { describe, it, expect } from 'vitest';
import { extractErrorMessage, readErrorDetail } from './errors';

describe('extractErrorMessage', () => {
  it('returns the message of an Error', () => {
    expect(extractErrorMessage(new Error('boom'))).toBe('boom');
  });
  it('falls back for an Error with empty message', () => {
    expect(extractErrorMessage(new Error(''))).toBe('An unexpected error occurred.');
  });
  it('falls back for a non-Error value', () => {
    expect(extractErrorMessage('nope')).toBe('An unexpected error occurred.');
    expect(extractErrorMessage(undefined)).toBe('An unexpected error occurred.');
  });
  it('uses custom fallback for a non-Error value', () => {
    expect(extractErrorMessage('nope', 'Custom fallback')).toBe('Custom fallback');
    expect(extractErrorMessage(undefined, 'Custom fallback')).toBe('Custom fallback');
  });
  it('uses custom fallback for an Error with empty message', () => {
    expect(extractErrorMessage(new Error(''), 'Custom fallback')).toBe('Custom fallback');
  });
  it('ignores custom fallback when the Error has a message', () => {
    expect(extractErrorMessage(new Error('real message'), 'Custom fallback')).toBe('real message');
  });
});

describe('readErrorDetail', () => {
  it('throws an Error carrying the parsed {detail}', async () => {
    const res = new Response(JSON.stringify({ detail: 'Unaffordable pull' }), { status: 400 });
    await expect(readErrorDetail(res, 'fallback')).rejects.toThrow('Unaffordable pull');
  });
  it('throws the fallback when the body is not JSON', async () => {
    const res = new Response('<html>', { status: 500 });
    await expect(readErrorDetail(res, 'fallback')).rejects.toThrow('fallback');
  });
  it('throws the fallback when detail is blank', async () => {
    const res = new Response(JSON.stringify({ detail: '   ' }), { status: 400 });
    await expect(readErrorDetail(res, 'fallback')).rejects.toThrow('fallback');
  });
});
