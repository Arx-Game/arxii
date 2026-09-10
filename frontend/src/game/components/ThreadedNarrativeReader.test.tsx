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
});
