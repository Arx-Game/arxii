import { describe, it, expect, vi, beforeEach } from 'vitest';

const { refreshRowMock } = vi.hoisted(() => ({ refreshRowMock: vi.fn() }));

vi.mock('@/scenes/sceneFeedCache', () => ({ refreshSceneFeedRow: refreshRowMock }));
vi.mock('@/queryClient', () => ({ queryClient: { tag: 'client' } }));

import { handleInteractionChangedPayload } from '../handleInteractionChangedPayload';

describe('handleInteractionChangedPayload', () => {
  beforeEach(() => vi.clearAllMocks());

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
});
