import { beforeEach, describe, expect, it, vi } from 'vitest';
import { confirmPasswordReset, requestPasswordReset, validatePasswordResetKey } from './api';

const fetchMock = vi.fn();
vi.mock('@/lib/utils', () => ({ getCookie: () => 'test-csrf' }));

describe('allauth password recovery contract', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
  });

  it('sends the request email and validates the email-link key in a header', async () => {
    fetchMock.mockResolvedValue(new Response('{}', { status: 200 }));
    await requestPasswordReset('owner@example.com');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/browser/v1/auth/password/request');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ email: 'owner@example.com' });
    await validatePasswordResetKey('test-key');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/auth/browser/v1/auth/password/reset');
    expect(fetchMock.mock.calls[1][1].headers.get('X-Password-Reset-Key')).toBe('test-key');
  });

  it('accepts allauth logged-out 401 after a successful password reset', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 401,
          data: { flows: [{ id: 'login' }] },
          meta: { is_authenticated: false },
        }),
        { status: 401 }
      )
    );
    await expect(
      confirmPasswordReset({ key: 'test-key', password: 'new-password' })
    ).resolves.toBeUndefined();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      key: 'test-key',
      password: 'new-password',
    });
  });

  it('does not mistake a rejected request or bare 401 for a completed reset', async () => {
    fetchMock.mockResolvedValue(new Response('{}', { status: 401 }));
    await expect(confirmPasswordReset({ key: 'bad', password: 'new-password' })).rejects.toThrow(
      'Could not reset'
    );
    await expect(requestPasswordReset('owner@example.com')).rejects.toThrow('Could not request');
  });

  it('preserves allauth password and expired-key errors and handles non-JSON failures', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ errors: [{ message: 'This password is too common.' }] }), {
        status: 400,
      })
    );
    await expect(confirmPasswordReset({ key: 'test-key', password: 'password' })).rejects.toThrow(
      'This password is too common.'
    );
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ errors: [{ message: 'Invalid password reset key' }] }), {
        status: 400,
      })
    );
    await expect(validatePasswordResetKey('expired')).rejects.toThrow('Invalid password reset key');
    fetchMock.mockResolvedValueOnce(new Response('<html>Unavailable</html>', { status: 503 }));
    await expect(requestPasswordReset('owner@example.com')).rejects.toThrow(
      'Could not request a reset link'
    );
  });
});
