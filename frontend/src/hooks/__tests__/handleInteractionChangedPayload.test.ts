import { describe, it, expect, vi, beforeEach } from 'vitest';

const { refreshRowMock } = vi.hoisted(() => ({ refreshRowMock: vi.fn() }));

vi.mock('@/scenes/sceneFeedCache', () => ({ refreshSceneFeedRow: refreshRowMock }));
vi.mock('@/queryClient', () => ({ queryClient: { tag: 'client' } }));

import { handleInteractionChangedPayload } from '../handleInteractionChangedPayload';

describe('handleInteractionChangedPayload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    refreshRowMock.mockResolvedValue(undefined);
  });

  it('calls refreshSceneFeedRow with the frame ids', () => {
    handleInteractionChangedPayload({ interaction_id: 12, scene_id: 7 });
    expect(refreshRowMock).toHaveBeenCalledWith(
      { tag: 'client' },
      { interactionId: 12, sceneId: 7 }
    );
  });

  it('does nothing when the pose has no scene', () => {
    handleInteractionChangedPayload({ interaction_id: 12, scene_id: null });
    expect(refreshRowMock).not.toHaveBeenCalled();
  });

  it('reports a refresh failure instead of dropping it', async () => {
    const error = new Error('boom');
    refreshRowMock.mockRejectedValue(error);
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    handleInteractionChangedPayload({ interaction_id: 12, scene_id: 7 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(spy).toHaveBeenCalledWith(expect.any(String), error);
    spy.mockRestore();
  });
});
