/**
 * Tests for the GM dramatic-moment tagging control on PoseUnit (#1139).
 *
 * Verifies:
 *  - canGm=false → no "Tag moment" button.
 *  - canGm=true  → "Tag moment" button present.
 *  - Clicking the button opens the DramaticMomentTagDialog.
 *  - Dramatic-moment tag badges render when interaction has tags.
 *  - The mutation is called with the correct body when the form is submitted.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { store } from '@/store/store';
import { PoseUnit } from '../PoseUnit';
import type { Interaction } from '../../types';

// ---------------------------------------------------------------------------
// Mock the queries module so no real network calls happen
// ---------------------------------------------------------------------------

const mockFetchDramaticMomentTypes = vi.fn().mockResolvedValue([
  { id: 1, label: 'Grand Entrance', resonance: 10 },
  { id: 2, label: 'Climactic Blow', resonance: 20 },
]);

const mockPostDramaticMomentTag = vi.fn().mockResolvedValue({ id: 99 });

// The scene detail says whether the viewer may name the resonance a tag pays (#5327): only the
// scene's GM and staff may.
const mockFetchScene = vi.fn();
const sceneFor = (viewerCanNameTagResonance: boolean) => ({
  id: 5,
  viewer_can_gm: true,
  viewer_can_name_tag_resonance: viewerCanNameTagResonance,
});

vi.mock('../../queries', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../queries')>();
  return {
    ...original,
    fetchDramaticMomentTypes: () => mockFetchDramaticMomentTypes(),
    postDramaticMomentTag: (body: unknown) => mockPostDramaticMomentTag(body),
    fetchScene: () => mockFetchScene(),
    // Keep postInteractionReaction working for ReactionsFooter
    postInteractionReaction: vi.fn().mockResolvedValue(null),
  };
});

// The tag dialog's resonance picker lists every resonance in the game (#5327).
vi.mock('@/magic/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/magic/api')>()),
  getResonanceCatalog: () =>
    Promise.resolve([
      { id: 10, name: 'Valor', affinity: 1, affinity_name: 'Celestial', description: '' },
      { id: 20, name: 'Fury', affinity: 2, affinity_name: 'Primal', description: '' },
      { id: 30, name: 'Grief', affinity: 2, affinity_name: 'Primal', description: '' },
    ]),
}));

// Stub PoseUnitDetailPanel — not under test here
vi.mock('../PoseUnitDetailPanel', () => ({
  PoseUnitDetailPanel: ({ actionInteractionIds }: { actionInteractionIds: number[] }) => (
    <div data-testid="pose-unit-detail-panel">{actionInteractionIds.join(',')}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeInteraction(overrides: Partial<Interaction> = {}): Interaction {
  return {
    id: 42,
    persona: { id: 10, name: 'Alice' },
    content: 'She steps forward boldly.',
    mode: 'pose',
    visibility: 'default',
    timestamp: '2026-01-01T00:00:00Z',
    scene: 5,
    reactions: [],
    is_favorited: false,
    place: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
    action_links: [],
    dramatic_moment_tags: [],
    pose_kind: 'standard',
    endorsee_sheet_id: null,
    endorsable_resonances: [],
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
    ...overrides,
  };
}

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </Provider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PoseUnit — GM dramatic-moment tag control', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchScene.mockResolvedValue(sceneFor(false));
  });

  it('does NOT render the tag button when canGm is false (default)', () => {
    const interaction = makeInteraction();

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={false} />
      </Wrapper>
    );

    expect(screen.queryByTestId('tag-moment-button')).toBeNull();
  });

  it('does NOT render the tag button when canGm is omitted', () => {
    const interaction = makeInteraction();

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" />
      </Wrapper>
    );

    expect(screen.queryByTestId('tag-moment-button')).toBeNull();
  });

  it('renders the tag button when canGm is true', () => {
    const interaction = makeInteraction();

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={true} />
      </Wrapper>
    );

    expect(screen.getByTestId('tag-moment-button')).toBeInTheDocument();
  });

  it('clicking the tag button opens the DramaticMomentTagDialog', async () => {
    const interaction = makeInteraction();

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={true} />
      </Wrapper>
    );

    // Dialog not open initially — the submit button inside it should not be present
    expect(screen.queryByTestId('tag-moment-submit')).toBeNull();

    fireEvent.click(screen.getByTestId('tag-moment-button'));

    // Dialog is now open — title is rendered
    await waitFor(() => {
      expect(screen.getByText('Tag Dramatic Moment')).toBeInTheDocument();
    });
  });

  it('renders dramatic-moment tag badges for tagged interactions', () => {
    const interaction = makeInteraction({
      dramatic_moment_tags: [
        { moment_type_label: 'Grand Entrance', character_sheet_id: 7 },
        { moment_type_label: 'Climactic Blow', character_sheet_id: 7 },
      ],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={false} />
      </Wrapper>
    );

    expect(screen.getByTestId('dramatic-moment-badges')).toBeInTheDocument();
    expect(screen.getByText(/Grand Entrance/)).toBeInTheDocument();
    expect(screen.getByText(/Climactic Blow/)).toBeInTheDocument();
  });

  it('renders no badge section when there are no dramatic-moment tags', () => {
    const interaction = makeInteraction({ dramatic_moment_tags: [] });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={false} />
      </Wrapper>
    );

    expect(screen.queryByTestId('dramatic-moment-badges')).toBeNull();
  });

  it('renders badges AND the tag button when canGm is true', () => {
    const interaction = makeInteraction({
      dramatic_moment_tags: [{ moment_type_label: 'Grand Entrance', character_sheet_id: 7 }],
    });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={true} />
      </Wrapper>
    );

    expect(screen.getByTestId('dramatic-moment-badges')).toBeInTheDocument();
    expect(screen.getByTestId('tag-moment-button')).toBeInTheDocument();
  });

  it('dialog loads moment type options from the query', async () => {
    const interaction = makeInteraction();

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={true} />
      </Wrapper>
    );

    fireEvent.click(screen.getByTestId('tag-moment-button'));

    await waitFor(() => {
      expect(mockFetchDramaticMomentTypes).toHaveBeenCalled();
    });
  });

  it('submitting the dialog calls postDramaticMomentTag with the correct body', async () => {
    // Radix Select sets pointer-events: none on <body> while closed;
    // disable the userEvent pointer-events guard so we can click the Select in jsdom.
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const interaction = makeInteraction({ id: 42 });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={true} />
      </Wrapper>
    );

    // Open the dialog
    await user.click(screen.getByTestId('tag-moment-button'));

    // Wait for the dialog to open and moment types to load
    await waitFor(() => {
      expect(screen.getByText('Tag Dramatic Moment')).toBeInTheDocument();
    });

    // Open the Select dropdown and pick "Grand Entrance" (id=1)
    await user.click(screen.getByTestId('moment-type-select'));
    await user.click(await screen.findByRole('option', { name: 'Grand Entrance' }));

    // Submit the form
    await user.click(screen.getByTestId('tag-moment-submit'));

    // Assert the mutation was called with the correct body shape
    await waitFor(() => {
      expect(mockPostDramaticMomentTag).toHaveBeenCalledWith({
        moment_type: 1,
        interaction: 42,
      });
    });
  });

  it("shows the moment type's own resonance, and sends the one the GM picks instead", async () => {
    mockFetchScene.mockResolvedValue(sceneFor(true));
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const interaction = makeInteraction({ id: 42 });

    render(
      <Wrapper>
        <PoseUnit interaction={interaction} sceneId="5" canGm={true} />
      </Wrapper>
    );

    await user.click(screen.getByTestId('tag-moment-button'));
    await user.click(await screen.findByTestId('moment-type-select'));
    await user.click(await screen.findByRole('option', { name: 'Grand Entrance' }));

    // Grand Entrance's own resonance (id 10, Valor) shows until the GM picks another.
    await waitFor(() => {
      expect(screen.getByTestId('moment-resonance-select')).toHaveTextContent('Valor');
    });

    await user.click(screen.getByTestId('moment-resonance-select'));
    await user.click(await screen.findByRole('option', { name: 'Grief' }));
    await user.click(screen.getByTestId('tag-moment-submit'));

    await waitFor(() => {
      expect(mockPostDramaticMomentTag).toHaveBeenCalledWith({
        moment_type: 1,
        interaction: 42,
        resonance: 30,
      });
    });
  });

  it('offers no resonance picker to an owner who is not the GM, and sends no resonance', async () => {
    mockFetchScene.mockResolvedValue(sceneFor(false));
    const user = userEvent.setup({ pointerEventsCheck: 0 });

    render(
      <Wrapper>
        <PoseUnit interaction={makeInteraction({ id: 42 })} sceneId="5" canGm={true} />
      </Wrapper>
    );

    await user.click(screen.getByTestId('tag-moment-button'));
    await user.click(await screen.findByTestId('moment-type-select'));
    await user.click(await screen.findByRole('option', { name: 'Grand Entrance' }));
    await waitFor(() => expect(mockFetchScene).toHaveBeenCalled());

    expect(screen.queryByTestId('moment-resonance-select')).toBeNull();

    await user.click(screen.getByTestId('tag-moment-submit'));
    await waitFor(() => {
      expect(mockPostDramaticMomentTag).toHaveBeenCalledWith({
        moment_type: 1,
        interaction: 42,
      });
    });
  });

  it("shows the server's sentence when a tag is refused, and leaves the dialog open", async () => {
    mockPostDramaticMomentTag.mockRejectedValueOnce(
      new Error('You cannot tag a moment for your own character.')
    );
    const user = userEvent.setup({ pointerEventsCheck: 0 });

    render(
      <Wrapper>
        <PoseUnit interaction={makeInteraction({ id: 42 })} sceneId="5" canGm={true} />
      </Wrapper>
    );

    await user.click(screen.getByTestId('tag-moment-button'));
    await user.click(await screen.findByTestId('moment-type-select'));
    await user.click(await screen.findByRole('option', { name: 'Grand Entrance' }));
    await user.click(screen.getByTestId('tag-moment-submit'));

    expect(
      await screen.findByText('You cannot tag a moment for your own character.')
    ).toBeInTheDocument();
    expect(screen.getByText('Tag Dramatic Moment')).toBeInTheDocument();
    expect(screen.queryByText('Failed to tag moment. Please try again.')).toBeNull();
  });
});
