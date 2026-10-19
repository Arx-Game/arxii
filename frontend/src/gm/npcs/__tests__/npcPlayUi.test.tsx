import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GameTopBar } from '@/game/components/GameTopBar';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { resetGame, setActiveSession, startSession } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';
import type { Interaction } from '@/scenes/types';

import { NpcNotesCard } from '../NpcNotesCard';
import { NpcOfferCard } from '../NpcOfferCard';
import { NpcResponseCard } from '../NpcResponseCard';
import { poseCarryingAction } from '../pendingNpcResponse';

const postDispatchAction = vi.fn();
vi.mock('@/combat/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/combat/api')>()),
  postDispatchAction: (...args: unknown[]) => postDispatchAction(...args),
}));
vi.mock('@/home/hall/queries', () => ({ useClockQuery: () => ({ data: undefined }) }));

const vael = {
  id: 9,
  name: 'Captain Vael',
  character_id: 90,
  profile_picture_url: null,
  loan: { id: 7, scene_title: 'The Siege at Low Gate', offered_by_name: 'Warden Osk' },
  npc_notes: 'He is right about almost everything.\n\nHe does not know about Rook.',
  is_crowd_voice: false,
  primary_persona_id: 70,
  active_persona_id: 70,
  unread_narrative_count: 0,
  unread_direct: 0,
  has_ambient_unread: false,
  attention_as_of_id: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'NPC',
  is_story_npc: true,
  character_type: 'PC',
  activity_state: 'ACTIVE',
  activity_requirement: 'NONE',
  creation_provenance: 'player',
  thaw_available_at: null,
  session_count: 0,
  room_name: null,
} as unknown as MyRosterEntry;

afterEach(() => {
  store.dispatch(resetGame());
  vi.clearAllMocks();
});

describe('NPC play UI', () => {
  it('tags an NPC character NPC and a crowd voice CROWD', () => {
    store.dispatch(startSession('Captain Vael'));
    store.dispatch(setActiveSession('Captain Vael'));
    const crowd = { ...vael, id: 10, name: 'Gate guards', is_crowd_voice: true };
    renderWithProviders(<GameTopBar characters={[vael, crowd]} />);
    const tags = screen.getAllByTestId('npc-tag').map((tag) => tag.textContent);
    expect(tags).toEqual(['NPC', 'CROWD']);
  });

  it('gives a GM character on the NPC shelf no tag', () => {
    const gmCharacter = { ...vael, id: 11, name: 'Ravenna', loan: null, is_story_npc: false };
    renderWithProviders(<GameTopBar characters={[vael, gmCharacter]} />);
    expect(screen.getAllByTestId('npc-tag')).toHaveLength(1);
  });

  it('tags a crowd voice CROWD on the active tab', () => {
    const crowd = { ...vael, id: 10, name: 'Gate guards', is_crowd_voice: true };
    store.dispatch(startSession('Gate guards'));
    store.dispatch(setActiveSession('Gate guards'));
    renderWithProviders(<GameTopBar characters={[crowd]} />);
    expect(screen.getByTestId('npc-tag')).toHaveTextContent('CROWD');
  });

  it('tags NPC and CROWD in the list shown with no active character', () => {
    const crowd = { ...vael, id: 10, name: 'Gate guards', is_crowd_voice: true };
    renderWithProviders(<GameTopBar characters={[vael, crowd]} />);
    expect(screen.getAllByTestId('npc-tag').map((t) => t.textContent)).toEqual(['NPC', 'CROWD']);
  });

  it('calls onPoseAs from the response card', () => {
    const onPoseAs = vi.fn();
    const interaction = {
      id: 1,
      persona: { id: 5, name: 'Mirel' },
      content: 'Mirel attempts to persuade Vael: Solid success',
      mode: 'action',
      target_persona_ids: [70],
      action_links: [],
    } as unknown as Interaction;
    renderWithProviders(
      <NpcResponseCard interaction={interaction} npcName="Vael" onPoseAs={onPoseAs} />
    );
    expect(screen.getByText('Mirel attempts to persuade Vael: Solid success')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Pose as Vael' }));
    expect(onPoseAs).toHaveBeenCalledWith(interaction);
  });

  it('shows the attaching pose as a multi-paragraph excerpt under the outcome', () => {
    const action = {
      id: 7,
      persona: { id: 5, name: 'Mirel' },
      content: 'Mirel attempts to persuade Vael',
      mode: 'action',
      target_persona_ids: [70],
      action_links: [],
    } as unknown as Interaction;
    const pose = {
      id: 9,
      persona: { id: 5, name: 'Mirel' },
      content: 'Mirel leans in.\n\nShe lowers her voice.',
      mode: 'pose',
      target_persona_ids: [],
      action_links: [
        {
          id: 1,
          ordering: 0,
          action_interaction: { id: 7, content: '', mode: 'action', timestamp: '' },
        },
      ],
    } as unknown as Interaction;
    expect(poseCarryingAction([action, pose], action)).toBe(pose);
    renderWithProviders(
      <NpcResponseCard interaction={action} excerpt={pose} npcName="Vael" onPoseAs={vi.fn()} />
    );
    expect(screen.getByText('Mirel attempts to persuade Vael')).toBeInTheDocument();
    expect(screen.getByText('Mirel leans in.')).toBeInTheDocument();
    expect(screen.getByText('She lowers her voice.')).toBeInTheDocument();
  });

  it('shows no excerpt box when no pose carried the action', () => {
    const action = {
      id: 7,
      persona: { id: 5, name: 'Mirel' },
      content: 'Mirel attempts to persuade Vael',
      mode: 'action',
      target_persona_ids: [70],
      action_links: [],
    } as unknown as Interaction;
    expect(poseCarryingAction([action], action)).toBeNull();
    renderWithProviders(<NpcResponseCard interaction={action} npcName="Vael" onPoseAs={vi.fn()} />);
    expect(screen.queryByTestId('npc-response-excerpt')).not.toBeInTheDocument();
  });

  it('shows the notes as paragraphs', () => {
    renderWithProviders(<NpcNotesCard entry={vael} />);
    expect(screen.getByText('He does not know about Rook.')).toBeInTheDocument();
    expect(screen.getByText('Notes for whoever plays Captain Vael')).toBeInTheDocument();
  });

  it('posts answer_npc_loan with accept true', async () => {
    postDispatchAction.mockResolvedValue({ success: true });
    renderWithProviders(
      <NpcOfferCard
        characterId={42}
        loan={{
          loan_id: 7,
          roster_entry_id: 9,
          name: 'The Masked Envoy',
          thumbnail_url: null,
          scene_id: 1,
          scene_title: 'The Siege at Low Gate',
          offered_by_name: 'Warden Osk',
          notes_for_player: 'The Envoy offers terms once.',
        }}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    await waitFor(() =>
      expect(postDispatchAction).toHaveBeenCalledWith(
        42,
        expect.objectContaining({
          ref: expect.objectContaining({ registry_key: 'answer_npc_loan' }),
          kwargs: { loan_id: 7, accept: true },
        })
      )
    );
  });
});
