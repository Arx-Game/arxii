import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch, postLogin } from './api';

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

// Mock getCookie
vi.mock('@/lib/utils', () => ({
  getCookie: vi.fn().mockReturnValue('mock-csrf-token'),
}));

describe('apiFetch content-type handling (2026-07 audit)', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockFetch.mockResolvedValue({ ok: true });
  });

  it('labels JSON bodies application/json', async () => {
    await apiFetch('/api/x/', { method: 'POST', body: JSON.stringify({ a: 1 }) });
    const headers = mockFetch.mock.calls[0][1].headers as Headers;
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('never sets Content-Type on a FormData body (fetch supplies the multipart boundary)', async () => {
    const form = new FormData();
    form.append('image_file', new Blob(['x']), 'x.png');
    await apiFetch('/api/roster/media/', { method: 'POST', body: form });
    const headers = mockFetch.mock.calls[0][1].headers as Headers;
    expect(headers.get('Content-Type')).toBeNull();
  });
});

describe('apiFetch keeps every request on this site (CodeQL alert #96)', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockFetch.mockResolvedValue({ ok: true });
  });

  it('sends a relative path to this origin, query included', async () => {
    await apiFetch('/api/x/?page=2');
    expect(mockFetch.mock.calls[0][0]).toBe(`${window.location.origin}/api/x/?page=2`);
  });

  it('follows an absolute link on this origin, as a paginated next link is', async () => {
    await apiFetch(`${window.location.origin}/api/items/?page=3`);
    expect(mockFetch.mock.calls[0][0]).toBe(`${window.location.origin}/api/items/?page=3`);
  });

  it('refuses a URL on another origin with a rejection and sends nothing', async () => {
    await expect(apiFetch('https://evil.example/api/x/')).rejects.toThrow(/off this site/);
    await expect(apiFetch('//evil.example/api/x/')).rejects.toThrow(/off this site/);
    await expect(apiFetch('/\\evil.example/api/x/')).rejects.toThrow(/off this site/);
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

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
    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      `${window.location.origin}/api/auth/browser/v1/auth/login`,
      {
        credentials: 'include',
        method: 'POST',
        headers: expect.any(Headers),
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'secret',
        }),
      }
    );

    // Check that the second call fetched user data
    expect(mockFetch).toHaveBeenNthCalledWith(2, `${window.location.origin}/api/user/`, {
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
    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      `${window.location.origin}/api/auth/browser/v1/auth/login`,
      {
        credentials: 'include',
        method: 'POST',
        headers: expect.any(Headers),
        body: JSON.stringify({
          username: 'testuser',
          password: 'secret',
        }),
      }
    );

    // Check that the second call fetched user data
    expect(mockFetch).toHaveBeenNthCalledWith(2, `${window.location.origin}/api/user/`, {
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
