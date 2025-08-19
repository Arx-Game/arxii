import { describe, it, expect, vi, beforeEach } from 'vitest';
import { postLogin } from './api';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock getCookie
vi.mock('@/lib/utils', () => ({
  getCookie: vi.fn().mockReturnValue('mock-csrf-token'),
}));

describe('postLogin', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('transforms email login to email field', async () => {
    // Mock successful login response
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ success: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ id: 1, username: 'testuser' }),
      });

    await postLogin({ login: 'test@example.com', password: 'secret' });

    // Check that the first call (login) used email field
    expect(mockFetch).toHaveBeenNthCalledWith(1, '/api/auth/browser/v1/auth/login', {
      credentials: 'include',
      method: 'POST',
      headers: expect.any(Headers),
      body: JSON.stringify({
        email: 'test@example.com',
        password: 'secret',
      }),
    });

    // Check that the second call fetched user data
    expect(mockFetch).toHaveBeenNthCalledWith(2, '/api/user/', {
      credentials: 'include',
      headers: expect.any(Headers),
    });
  });

  it('transforms username login to username field', async () => {
    // Mock successful login response
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ success: true }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ id: 1, username: 'testuser' }),
      });

    await postLogin({ login: 'testuser', password: 'secret' });

    // Check that the first call (login) used username field
    expect(mockFetch).toHaveBeenNthCalledWith(1, '/api/auth/browser/v1/auth/login', {
      credentials: 'include',
      method: 'POST',
      headers: expect.any(Headers),
      body: JSON.stringify({
        username: 'testuser',
        password: 'secret',
      }),
    });

    // Check that the second call fetched user data
    expect(mockFetch).toHaveBeenNthCalledWith(2, '/api/user/', {
      credentials: 'include',
      headers: expect.any(Headers),
    });
  });

  it('throws error when login fails', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: vi.fn().mockResolvedValue({ detail: 'Invalid credentials' }),
    });

    await expect(postLogin({ login: 'test@example.com', password: 'wrong' })).rejects.toThrow(
      'Invalid credentials'
    );

    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('throws error when user data fetch fails after successful login', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: vi.fn().mockResolvedValue({ success: true }),
      })
      .mockResolvedValueOnce({
        ok: false,
      });

    await expect(postLogin({ login: 'test@example.com', password: 'secret' })).rejects.toThrow(
      'Failed to load user data after login'
    );

    expect(mockFetch).toHaveBeenCalledTimes(2);
  });
});
