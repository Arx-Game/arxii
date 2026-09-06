/**
 * Tests for `uploadPlayerMedia`'s error path (final fix wave, #3164).
 *
 * `MediaViewSet.create` maps a rejected upload (oversized file, quota
 * exceeded) to a DRF field-error body (`{image_file: ["..."]}`), not a bare
 * `{detail}` string. `uploadPlayerMedia` previously threw a generic
 * `Error('Failed to upload media')` on any non-ok response and discarded the
 * body, so the player never saw the server's actual message (e.g. "This
 * upload would exceed your media quota."). It now uses `readErrorDetail`
 * like the rest of the codebase.
 */

import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { ApiError } from '@/lib/errors';
import { uploadPlayerMedia } from '../api';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('uploadPlayerMedia', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('resolves with the created media on success', async () => {
    const media = { id: 1, cloudinary_url: 'https://example.com/a.jpg' };
    vi.mocked(apiFetch).mockResolvedValue(jsonResponse(media, 201));

    const result = await uploadPlayerMedia(new FormData());

    expect(result).toEqual(media);
  });

  it('surfaces the quota-exceeded message from a rejected upload', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      jsonResponse({ image_file: ['This upload would exceed your media quota.'] }, 400)
    );

    const err = await uploadPlayerMedia(new FormData()).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toContain('This upload would exceed your media quota.');
  });

  it('falls back to a generic message on a non-JSON error body', async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      new Response('<html>proxy error</html>', { status: 502 })
    );

    const err = await uploadPlayerMedia(new FormData()).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe('Failed to upload media');
  });
});
