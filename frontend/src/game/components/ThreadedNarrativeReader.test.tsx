import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThreadedNarrativeReader } from './ThreadedNarrativeReader';
import type { Interaction } from '@/scenes/types';

vi.mock('@/scenes/components/SceneMessages', () => ({
  SceneMessages: ({ filteredInteractions }: { filteredInteractions: Interaction[] }) => (
    <div data-testid="scene-messages">
      {filteredInteractions.map((item) => (
        <p key={item.id}>{item.content}</p>
      ))}
    </div>
  ),
}));

const interaction = (id: number, content: string, thread_id: string): Interaction => ({
  id,
  thread_id,
  persona: { id: id + 10, name: `Writer ${id}` },
  content,
  mode: 'pose',
  visibility: 'default',
  timestamp: `2026-01-01T00:0${id}:00Z`,
  scene: 1,
  reactions: [],
  is_favorited: false,
  place: null,
  place_name: null,
  receiver_persona_ids: [],
  target_persona_ids: [],
  pose_kind: 'standard',
  endorsee_sheet_id: null,
  endorsable_resonances: [],
  pose_endorsers: [],
  my_pose_endorsement: null,
  entry_endorsers: [],
  entry_endorsed_by_me: false,
});

describe('ThreadedNarrativeReader', () => {
  beforeEach(() => {
    // Each test uses conversationKey="scene:1" — clear so per-conversation
    // collapse state saved by one test never leaks into the next.
    window.localStorage.clear();
  });

  it('keeps explicit threads collapsed and exposes keyboard accessible controls', async () => {
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'root', 'thread-a'),
          interaction(2, 'reply', 'thread-a'),
          interaction(3, 'other', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    // thread-b is more recent, so thread-a starts collapsed — expand it first.
    await user.click(screen.getByRole('button', { name: /writer 1.*2 poses/i }));
    expect(screen.getByText('root')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /writer 1.*2 poses/i }));
    expect(screen.queryByText('root')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /writer 1.*2 poses/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  it('collapses all but the most recently active thread by default', () => {
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'older root', 'thread-a'),
          interaction(2, 'newer root', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    // thread-b's timestamp (2026-01-01T00:02:00Z) is later than thread-a's
    // (2026-01-01T00:01:00Z) — it should start expanded, thread-a collapsed.
    expect(screen.getByText('newer root')).toBeInTheDocument();
    expect(screen.queryByText('older root')).not.toBeInTheDocument();
  });

  it("re-derives the default collapse state on a scene change instead of carrying over the previous scene's stale collapsed set", () => {
    // Mirrors GameWindow.tsx's actual mount: `key={sceneFeed.sceneId}` on the
    // same element as `conversationKey={sceneFeed.sceneId}`, so switching
    // scenes forces React to unmount/remount this component (fresh
    // `collapsed`/`storedAnchorState` initializers) rather than reusing one
    // instance across scenes. Without that `key`, the old scene's `collapsed`
    // Set (full of the OLD scene's thread keys) would survive into the new
    // scene, where none of those keys match the new scene's groups — so
    // every thread in the new scene would silently render expanded.
    const { rerender } = render(
      <ThreadedNarrativeReader
        key="scene:1"
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'scene1 older', 'thread-a'),
          interaction(2, 'scene1 newer', 'thread-b'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    expect(screen.getByText('scene1 newer')).toBeInTheDocument();
    expect(screen.queryByText('scene1 older')).not.toBeInTheDocument();

    rerender(
      <ThreadedNarrativeReader
        key="scene:2"
        sceneId="2"
        conversationKey="scene:2"
        interactions={[
          interaction(1, 'scene2 older', 'thread-x'),
          interaction(2, 'scene2 newer', 'thread-y'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    expect(screen.getByText('scene2 newer')).toBeInTheDocument();
    expect(screen.queryByText('scene2 older')).not.toBeInTheDocument();
  });

  it('chronological mode shows all poses as a flat, time-ordered list', async () => {
    const user = userEvent.setup();
    render(
      <ThreadedNarrativeReader
        sceneId="1"
        conversationKey="scene:1"
        interactions={[
          interaction(1, 'first', 'thread-a'),
          interaction(2, 'second', 'thread-b'),
          interaction(3, 'third', 'thread-a'),
        ]}
        fetchNextPage={vi.fn()}
      />
    );
    await user.click(screen.getByRole('button', { name: /chronological/i }));
    const texts = screen.getAllByText(/first|second|third/).map((el) => el.textContent);
    expect(texts).toEqual(['first', 'second', 'third']);
  });
});
