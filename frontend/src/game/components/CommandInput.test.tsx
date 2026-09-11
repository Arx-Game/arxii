import { render as rtlRender, screen, fireEvent, waitFor, act } from '@testing-library/react';
import type { RenderOptions } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';
import { emitActionResult } from '@/hooks/actionResultBus';
import { draftStorageKey } from '@/game/useDraftStore';
import type { Draft } from '@/game/useDraftStore';

// Wrap every render call in a QueryClientProvider so useQuery hooks work in tests.
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function render(ui: ReactElement, options?: RenderOptions) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return rtlRender(ui, { wrapper: Wrapper, ...options });
}

const sendMock = vi.fn();
// #3760 Task 10 — say/whisper now dispatch via executeAction instead of send().
const executeActionMock = vi.fn();
// Loosely typed: submitPose resolves with the created interaction payload
// (#2183 reads `id` off it) or undefined in older tests.
const submitPoseMock = vi.fn((): Promise<unknown> => Promise.resolve());
const fetchSceneMock = vi.fn();
const toastErrorMock = vi.fn();
// #3760 Task 11 — the Task 6 writer-only lookup endpoint the "Check status"
// button queries.
const fetchPoseSubmissionMock = vi.fn();

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({ send: sendMock, executeAction: executeActionMock }),
}));

vi.mock('sonner', () => ({
  toast: { error: (...args: unknown[]) => toastErrorMock(...args), success: vi.fn() },
}));

vi.mock('@/scenes/queries', () => ({
  submitPose: (...args: unknown[]) => submitPoseMock(...(args as [])),
  fetchScene: (...args: unknown[]) => fetchSceneMock(...(args as [])),
  fetchPoseSubmission: (...args: unknown[]) => fetchPoseSubmissionMock(...(args as [])),
  sceneKeys: {
    detail: (id: string) => ['scene', String(id)] as const,
  },
}));

// Bob carries a resolvable dbref (#3760 Task 10 — whisper resolves its
// composerMode target NAME against this room-character list, via `dbref`,
// to the `target_id` the WS wire actually needs; `sceneDetail.participants`
// carries no dbref, only a Persona id, the wrong id space for a whisper
// target).
vi.mock('@/store/hooks', () => ({
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({
      game: {
        active: 'Alice',
        sessions: {
          Alice: {
            room: { characters: [{ name: 'Bob', thumbnail_url: null, dbref: '#501' }] },
          },
        },
      },
    }),
  useAppDispatch: () => vi.fn(),
}));

// Mock ColorPicker to avoid rendering issues
vi.mock('@/components/ColorPicker', () => ({
  ColorPicker: () => <div data-testid="color-picker" />,
}));

// Mock ActionAttachment to avoid nested query client issues
vi.mock('@/scenes/components/ActionAttachment', () => ({
  ActionAttachment: ({
    attachment,
    onDetach,
  }: {
    attachment: unknown;
    onAttach: unknown;
    onDetach: () => void;
  }) => (
    <div data-testid="action-attachment">
      {attachment ? (
        <button data-testid="detach-action" onClick={onDetach}>
          detach
        </button>
      ) : null}
    </div>
  ),
}));

// Mock EntranceTechniqueAttachment (#2183) — a thin stub that lets tests
// simulate picking a technique+target via `onChange`, without pulling in the
// real popover/TargetPicker/query machinery (covered by its own test file).
const createActionRequestMock = vi.fn(
  (..._args: [string, Record<string, unknown>]): Promise<unknown> =>
    Promise.resolve({ status: 'resolved' })
);

vi.mock('@/scenes/components/EntranceTechniqueAttachment', () => ({
  EntranceTechniqueAttachment: ({
    value,
    onChange,
  }: {
    value: { techniqueId: number; targetPersonaId?: number } | null;
    onChange: (value: { techniqueId: number; targetPersonaId?: number } | null) => void;
  }) => (
    <div data-testid="entrance-technique-attachment">
      <button
        type="button"
        data-testid="attach-entrance-technique"
        onClick={() => onChange({ techniqueId: 7, targetPersonaId: 3 })}
      >
        attach
      </button>
      {value && <span data-testid="entrance-technique-attached">{value.techniqueId}</span>}
    </div>
  ),
}));

vi.mock('@/scenes/actionQueries', () => ({
  createActionRequest: (...args: unknown[]) =>
    createActionRequestMock(...(args as [string, Record<string, unknown>])),
}));

describe('CommandInput', () => {
  beforeEach(() => {
    sendMock.mockClear();
    executeActionMock.mockClear();
    submitPoseMock.mockClear();
    submitPoseMock.mockImplementation(() => Promise.resolve());
    fetchSceneMock.mockClear();
    toastErrorMock.mockClear();
    fetchPoseSubmissionMock.mockClear();
    fetchPoseSubmissionMock.mockResolvedValue(null);
    createActionRequestMock.mockClear();
    createActionRequestMock.mockImplementation(() => Promise.resolve({ status: 'resolved' }));
    queryClient.clear();
    // useDraftStore (#3760 Task 10) persists to sessionStorage under a key
    // derived from account/persona/conversation — several tests in this file
    // share the same derived key (no draftScope passed), so a leftover draft
    // from one test would otherwise leak into the next test's hydration.
    sessionStorage.clear();
  });

  it('keeps drafts editable while entry is unconfirmed and blocks button and keyboard sends', () => {
    const { rerender } = render(
      <CommandInput character="Alice" ready={false} submitOnEnter={false} />
    );
    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeEnabled();
    fireEvent.change(textarea, { target: { value: 'A draft while entering.' } });
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });
    expect(sendMock).not.toHaveBeenCalled();
    expect(submitPoseMock).not.toHaveBeenCalled();
    expect(textarea).toHaveValue('A draft while entering.');

    rerender(<CommandInput character="Alice" ready submitOnEnter={false} />);
    expect(textarea).toHaveValue('A draft while entering.');
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(sendMock).toHaveBeenCalledWith('Alice', 'A draft while entering.');
  });
  it('renders ghost text with mode label when composerMode is provided', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose \u2192 Room' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    expect(screen.getByText('Pose \u2192 Room')).toBeInTheDocument();
  });

  it('renders ModeSelector dropdown', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose \u2192 Room' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    expect(screen.getByRole('button', { name: /pose/i })).toBeInTheDocument();
  });

  it('submits raw text when no composerMode is set', () => {
    render(<CommandInput character="Alice" />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'hello world' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'hello world');
  });

  it('prepends default command when no explicit command typed', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose \u2192 Room' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'stretches languidly' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'pose stretches languidly');
  });

  it('uses explicit command when one is typed', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose \u2192 Room' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'say hello everyone' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'say hello everyone');
  });

  it('sends a typed page verbatim instead of wrapping it into pose/say IC text (#3069)', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose → Room' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'page Bob=meet me ooc for a sec' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'page Bob=meet me ooc for a sec');
  });

  it('whisper mode dispatches via executeAction with a resolved target_id and client_request_id (#3760)', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Bob'],
      label: 'Whisper \u2192 Bob',
    };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'secret message' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
    // Bob's dbref (#501, from the @/store/hooks mock) resolves to target_id
    // 501 -- the WS wire's `_resolve_registry_kwargs` only auto-resolves
    // `<field>_id` int kwargs, never a bare name.
    expect(executeActionMock).toHaveBeenCalledWith('Alice', 'whisper', {
      text: 'secret message',
      target_id: 501,
      client_request_id: expect.any(String),
    });
  });

  it('prepends targets with @ syntax for non-whisper commands', () => {
    const mode: ComposerMode = {
      command: 'pose',
      targets: ['Bob', 'Carol'],
      label: 'Pose \u2192 Bob, Carol',
    };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'waves hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'pose @Bob,@Carol waves hello');
  });

  it('appends @name to input when targetToAppend is set', () => {
    const onConsumed = vi.fn();
    const { rerender } = render(
      <CommandInput character="Alice" targetToAppend={null} onTargetConsumed={onConsumed} />
    );

    rerender(<CommandInput character="Alice" targetToAppend="Bob" onTargetConsumed={onConsumed} />);

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea.value).toBe('@Bob');
    expect(onConsumed).toHaveBeenCalled();
  });

  it('does not send when whisper mode has no target', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: [],
      label: 'Whisper',
    };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'secret message' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
  });

  it('does not submit empty text', () => {
    render(<CommandInput character="Alice" />);
    const textarea = screen.getByRole('textbox');

    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
  });

  it('calls onSubmitAction with attached action when submitting', () => {
    const onSubmitAction = vi.fn();
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose' };
    const action = {
      actionKey: 'intimidate',
      name: 'Intimidate',
      requiresTarget: true,
      target: 'Bob',
    };

    render(
      <CommandInput
        character="Alice"
        composerMode={mode}
        sceneId="1"
        actionAttachment={action}
        onActionAttach={vi.fn()}
        onActionDetach={vi.fn()}
        onSubmitAction={onSubmitAction}
      />
    );

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'glares menacingly' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'pose glares menacingly');
    expect(onSubmitAction).toHaveBeenCalledWith(action);
  });

  it('does not call onSubmitAction when no action is attached', () => {
    const onSubmitAction = vi.fn();
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose' };

    render(
      <CommandInput
        character="Alice"
        composerMode={mode}
        sceneId="1"
        actionAttachment={null}
        onActionAttach={vi.fn()}
        onActionDetach={vi.fn()}
        onSubmitAction={onSubmitAction}
      />
    );

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'waves hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalled();
    expect(onSubmitAction).not.toHaveBeenCalled();
  });

  it('renders action attachment slot when sceneId is provided', () => {
    render(<CommandInput character="Alice" sceneId="1" />);
    expect(screen.getByTestId('action-attachment')).toBeInTheDocument();
  });

  it('renders the locked mode label with no dropdown trigger when locked (#2165)', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Alise'],
      label: 'Whisper → Alise',
      locked: true,
    };
    render(<CommandInput character="Alice" composerMode={mode} />);

    expect(screen.getByTitle('Audience is locked to this conversation tab')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /whisper/i })).not.toBeInTheDocument();
  });

  it('pose with detachments uses REST submitPose and skips WebSocket send', async () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose' };
    render(
      <CommandInput
        character="Alice"
        composerMode={mode}
        sceneId="1"
        personaId={42}
        pendingActionIds={[10, 11]}
        detachedActionIds={[11]}
        onPoseSubmitted={vi.fn()}
      />
    );
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'lunges forward' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 42,
      scene_id: 1,
      content: 'lunges forward',
      action_link_ids: [10],
    });
  });

  it('pose without detachments still uses REST submitPose (scene poses always take REST)', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose' };
    render(
      <CommandInput
        character="Alice"
        composerMode={mode}
        sceneId="1"
        personaId={42}
        pendingActionIds={[10]}
        detachedActionIds={[]}
      />
    );
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'stands ready' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 42,
      scene_id: 1,
      content: 'stands ready',
    });
  });

  it('plain pose (no composerMode) with sceneId/personaId uses REST submitPose', () => {
    render(<CommandInput character="Alice" sceneId="5" personaId={9} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'looks around' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 5,
      content: 'looks around',
    });
  });

  it('pose with no sceneId uses WebSocket send', () => {
    const mode: ComposerMode = { command: 'pose', targets: [], label: 'Pose' };
    render(<CommandInput character="Alice" composerMode={mode} personaId={9} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'waves' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'pose waves');
    expect(submitPoseMock).not.toHaveBeenCalled();
  });

  it('whisper composer mode with sceneId still dispatches via executeAction, never REST submitPose (#3760)', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Bob'],
      label: 'Whisper → Bob',
    };
    render(<CommandInput character="Alice" composerMode={mode} sceneId="5" personaId={9} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'secret message' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
    expect(submitPoseMock).not.toHaveBeenCalled();
    expect(executeActionMock).toHaveBeenCalledWith('Alice', 'whisper', {
      text: 'secret message',
      target_id: 501,
      client_request_id: expect.any(String),
    });
  });

  it('directed pose composer mode sends target_names on the REST path (#2156)', () => {
    const mode: ComposerMode = { command: 'pose', targets: ['Bob'], label: 'Pose → Bob' };
    render(<CommandInput character="Alice" composerMode={mode} sceneId="5" personaId={9} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'confronts' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 5,
      content: 'confronts',
      target_names: ['Bob'],
    });
  });

  it('keeps the draft and surfaces an error toast when submitPose rejects (#2156)', async () => {
    submitPoseMock.mockImplementation(() => Promise.reject(new Error('Not co-located.')));
    const onPoseSubmitted = vi.fn();
    render(
      <CommandInput character="Alice" sceneId="5" personaId={9} onPoseSubmitted={onPoseSubmitted} />
    );
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

    fireEvent.change(textarea, { target: { value: 'looks around' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(submitPoseMock).toHaveBeenCalled();
    await waitFor(() => expect(toastErrorMock).toHaveBeenCalledWith('Not co-located.'));

    // The draft survives the rejection — never silently eaten.
    expect(textarea.value).toBe('looks around');
    expect(onPoseSubmitted).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------------------
  // Entrance technique attachment (#2183)
  // ---------------------------------------------------------------------------

  it('does not render the entrance technique attachment when the entrance toggle is off', () => {
    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);
    expect(screen.queryByTestId('entrance-technique-attachment')).toBeNull();
  });

  it('renders the entrance technique attachment once the entrance toggle is on', () => {
    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);
    fireEvent.click(screen.getByRole('button', { name: 'Make an entrance' }));
    expect(screen.getByTestId('entrance-technique-attachment')).toBeInTheDocument();
  });

  it('toggling the entrance button back off drops the entrance technique attachment', () => {
    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);
    const toggle = screen.getByRole('button', { name: 'Make an entrance' });
    fireEvent.click(toggle);
    fireEvent.click(screen.getByTestId('attach-entrance-technique'));
    expect(screen.getByTestId('entrance-technique-attached')).toHaveTextContent('7');

    fireEvent.click(toggle);
    expect(screen.queryByTestId('entrance-technique-attachment')).toBeNull();

    // Re-opening shows a clean slate — the attachment was dropped, not preserved.
    fireEvent.click(toggle);
    expect(screen.queryByTestId('entrance-technique-attached')).toBeNull();
  });

  it('submitting an entrance pose with an attached technique dispatches createActionRequest with the submitPose response id (#2183)', async () => {
    submitPoseMock.mockImplementation(() => Promise.resolve({ id: 123 }));

    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);

    fireEvent.click(screen.getByRole('button', { name: 'Make an entrance' }));
    fireEvent.click(screen.getByTestId('attach-entrance-technique'));

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'strides in dramatically' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 1,
      content: 'strides in dramatically',
      pose_kind: 'entry',
    });

    await waitFor(() => expect(createActionRequestMock).toHaveBeenCalled());
    expect(createActionRequestMock).toHaveBeenCalledWith('1', {
      action_key: 'entrance',
      technique_id: 7,
      target_persona_id: 3,
      entry_interaction_id: 123,
    });
  });

  it('plain entrance (no technique attached) sends no action request — regression', async () => {
    submitPoseMock.mockImplementation(() => Promise.resolve({ id: 456 }));

    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);

    fireEvent.click(screen.getByRole('button', { name: 'Make an entrance' }));
    // No technique attached this time.

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'simply walks in' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 1,
      content: 'simply walks in',
      pose_kind: 'entry',
    });

    await waitFor(() => expect(submitPoseMock).toHaveBeenCalled());
    expect(createActionRequestMock).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------------------
  // Speaking-as identity chip (#2166)
  // ---------------------------------------------------------------------------

  it('renders the speaking-as chip with name and avatar when provided', () => {
    render(
      <CommandInput
        character="Alice"
        speakingAs={{ name: 'Alice', thumbnailUrl: 'https://example.com/alice.png' }}
      />
    );

    const chip = screen.getByTestId('speaking-as-chip');
    expect(chip).toHaveTextContent('Alice');
    const img = chip.querySelector('img');
    expect(img).toHaveAttribute('src', 'https://example.com/alice.png');
  });

  it('renders the speaking-as chip with initial-letter avatar when thumbnailUrl is null', () => {
    render(<CommandInput character="Alice" speakingAs={{ name: 'Bianca', thumbnailUrl: null }} />);

    const chip = screen.getByTestId('speaking-as-chip');
    expect(chip).toHaveTextContent('Bianca');
    expect(chip.querySelector('img')).toBeNull();
  });

  it('does not render the speaking-as chip when the prop is omitted (legacy callers)', () => {
    render(<CommandInput character="Alice" />);
    expect(screen.queryByTestId('speaking-as-chip')).toBeNull();
  });

  it('a plain (non-entrance) pose sends no action request — byte-identical regression', async () => {
    submitPoseMock.mockImplementation(() => Promise.resolve({ id: 789 }));

    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'looks around calmly' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 1,
      content: 'looks around calmly',
    });

    await waitFor(() => expect(submitPoseMock).toHaveBeenCalled());
    expect(createActionRequestMock).not.toHaveBeenCalled();
  });

  // ---------------------------------------------------------------------------
  // say/whisper via executeAction, ack-gated clearing (#3760 Task 10)
  // ---------------------------------------------------------------------------

  it('sends say via executeAction with a registry key and client_request_id, not raw text', () => {
    const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
    expect(executeActionMock).toHaveBeenCalledWith('Alice', 'say', {
      text: 'hello',
      client_request_id: expect.any(String),
    });
  });

  it('tt (tabletalk) dispatches via executeAction with a place kwarg and client_request_id when currentPlaceId is known (#3760 fix)', () => {
    const mode: ComposerMode = { command: 'tt', targets: [], label: 'Tabletalk' };
    render(<CommandInput character="Alice" composerMode={mode} currentPlaceId={7} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'leans in' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).not.toHaveBeenCalled();
    expect(executeActionMock).toHaveBeenCalledWith('Alice', 'pose', {
      text: 'leans in',
      place: 7,
      client_request_id: expect.any(String),
    });
  });

  it('tt falls back to legacy send when currentPlaceId is not known', () => {
    // Not currently at a place, or the places query hasn't resolved yet —
    // never risk a room-wide broadcast for what the player intends as a
    // table-scoped tabletalk line.
    const mode: ComposerMode = { command: 'tt', targets: [], label: 'Tabletalk' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'leans in' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(executeActionMock).not.toHaveBeenCalled();
    expect(sendMock).toHaveBeenCalledWith('Alice', 'tt leans in');
  });

  it('whisper falls back to legacy send when the target cannot be resolved to a room character', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Nobody'],
      label: 'Whisper → Nobody',
    };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'secret message' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(executeActionMock).not.toHaveBeenCalled();
    expect(sendMock).toHaveBeenCalledWith('Alice', 'whisper Nobody=secret message');
  });

  it('keeps the draft until the ACTION_RESULT ack arrives, then clears it (ack-gated clearing)', () => {
    const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

    fireEvent.change(textarea, { target: { value: 'hello there' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(executeActionMock).toHaveBeenCalled();
    // Unlike the old unconditional clear-on-submit, the text survives until
    // the server confirms the send.
    expect(textarea.value).toBe('hello there');

    act(() => {
      emitActionResult({ success: true, message: null, data: null });
    });

    expect(textarea.value).toBe('');
  });

  it('keeps the draft and surfaces an error toast when the ACTION_RESULT reports failure', () => {
    const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

    fireEvent.change(textarea, { target: { value: 'hello there' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    act(() => {
      emitActionResult({ success: false, message: 'You have been muted.', data: null });
    });

    expect(toastErrorMock).toHaveBeenCalledWith('You have been muted.');
    // The rejected content is preserved so the player can revise and resend.
    expect(textarea.value).toBe('hello there');
  });

  // ---------------------------------------------------------------------------
  // Composer delivery states: pending/rejected/unknown/stranded/storage-unavailable
  // (#3760 Task 11)
  // ---------------------------------------------------------------------------

  /**
   * Seeds the v2 useDraftStore sessionStorage row a fresh `CommandInput`
   * mount (character="Alice", no personaId/draftScope props unless
   * overridden) will hydrate from — the only way to reach the `unknown`
   * status and the stranded-draft-on-mount path from outside the component,
   * since nothing in this task wires a live trigger for either (Task 12's
   * reconnect reconciliation owns that).
   */
  function seedDraft(overrides: Partial<Draft>, conversationKey = 'character:Alice') {
    const key = draftStorageKey({ accountId: 0, personaId: 0, conversationKey });
    const draft: Draft = {
      content: 'leans against the doorframe',
      languageId: null,
      recipients: [],
      replyTo: null,
      companion: false,
      attachment: null,
      clientRequestId: 'req-1',
      status: 'clean',
      rejectionReason: null,
      ...overrides,
    };
    sessionStorage.setItem(key, JSON.stringify(draft));
  }

  describe('composer delivery states (#3760 Task 11)', () => {
    it('shows the pending "Sending…" indicator and disables the textarea while a live send is in flight', () => {
      const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
      render(<CommandInput character="Alice" composerMode={mode} />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      fireEvent.change(textarea, { target: { value: 'hello' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });

      expect(screen.getByText('Sending…')).toBeInTheDocument();
      expect(textarea).toBeDisabled();
      // A genuine live send is not a stranded draft.
      expect(screen.queryByText(/Unsent draft from/)).not.toBeInTheDocument();
    });

    it('re-enables the textarea once the pending send resolves', () => {
      const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
      render(<CommandInput character="Alice" composerMode={mode} />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      fireEvent.change(textarea, { target: { value: 'hello' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(textarea).toBeDisabled();

      act(() => {
        emitActionResult({ success: true, message: null, data: null });
      });

      expect(textarea).toBeEnabled();
      expect(screen.queryByText('Sending…')).not.toBeInTheDocument();
    });

    it('shows the typed rejection reason inline and keeps the textarea editable', () => {
      const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
      render(<CommandInput character="Alice" composerMode={mode} />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      fireEvent.change(textarea, { target: { value: 'hello there' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });

      act(() => {
        emitActionResult({ success: false, message: 'You have been muted.', data: null });
      });

      expect(screen.getByText(/You have been muted\./)).toBeInTheDocument();
      expect(textarea).toBeEnabled();
    });

    it('shows Check status and Retry buttons when the hydrated draft status is unknown', () => {
      seedDraft({ status: 'unknown', clientRequestId: 'req-unknown' });

      render(<CommandInput character="Alice" />);

      expect(screen.getByRole('button', { name: 'Check status' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    });

    it('Check status looks up the submission and clears the draft once it is found to have landed', async () => {
      fetchPoseSubmissionMock.mockResolvedValue({ interaction_id: 42, replayed: true });
      seedDraft({ status: 'unknown', clientRequestId: 'req-landed', content: 'leans in' });

      render(<CommandInput character="Alice" />);
      fireEvent.click(screen.getByRole('button', { name: 'Check status' }));

      await waitFor(() => expect(fetchPoseSubmissionMock).toHaveBeenCalledWith('req-landed'));
      await waitFor(() =>
        expect(screen.queryByRole('button', { name: 'Check status' })).not.toBeInTheDocument()
      );
    });

    it('Check status surfaces a toast and leaves the draft resendable when nothing was found', async () => {
      fetchPoseSubmissionMock.mockResolvedValue(null);
      seedDraft({ status: 'unknown', clientRequestId: 'req-missing', content: 'leans in' });

      render(<CommandInput character="Alice" />);
      fireEvent.click(screen.getByRole('button', { name: 'Check status' }));

      await waitFor(() => expect(fetchPoseSubmissionMock).toHaveBeenCalledWith('req-missing'));
      await waitFor(() => expect(toastErrorMock).toHaveBeenCalled());
      expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    });

    it('Retry re-dispatches via executeAction reusing the same client_request_id', () => {
      const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
      // The composer's own (legacy v1) draft text is a separate sessionStorage
      // key from useDraftStore's (v2); seed both under `draftScope` so
      // `command` hydrates to the same text a real reload would have
      // produced, without an intervening `fireEvent.change` — editing
      // through `handleChange` resets `useDraftStore`'s status back to
      // `clean` (see `setContent`'s doc comment), which would defeat this
      // test's whole premise before Retry is ever clicked.
      sessionStorage.setItem('arx:play-draft:v1:test-scope', 'hello again');
      seedDraft(
        { status: 'unknown', clientRequestId: 'req-retry', content: 'hello again' },
        'test-scope'
      );

      render(<CommandInput character="Alice" composerMode={mode} draftScope="test-scope" />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      expect(textarea.value).toBe('hello again');

      fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

      expect(executeActionMock).toHaveBeenCalledWith('Alice', 'say', {
        text: 'hello again',
        client_request_id: 'req-retry',
      });
    });

    it('shows the stranded-draft banner for a pending draft hydrated from storage with no live send in flight', () => {
      const mode: ComposerMode = { command: 'pose', targets: [], label: 'The Gilded Hart' };
      seedDraft({ status: 'pending', clientRequestId: 'req-stranded' });

      render(<CommandInput character="Alice" composerMode={mode} />);

      expect(screen.getByText(/Unsent draft from The Gilded Hart/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Discard' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Resume & retry' })).toBeInTheDocument();
      // Stranded, not actively sending — no false "Sending…" spinner.
      expect(screen.queryByText('Sending…')).not.toBeInTheDocument();
    });

    it('Discard on the stranded banner clears the draft and dismisses the banner', () => {
      const mode: ComposerMode = { command: 'pose', targets: [], label: 'The Gilded Hart' };
      seedDraft({ status: 'pending', clientRequestId: 'req-stranded' });

      render(<CommandInput character="Alice" composerMode={mode} />);
      fireEvent.click(screen.getByRole('button', { name: 'Discard' }));

      expect(screen.queryByText(/Unsent draft from/)).not.toBeInTheDocument();
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      expect(textarea.value).toBe('');
    });

    it('shows the storage-unavailable notice when sessionStorage writes fail', () => {
      const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('QuotaExceededError');
      });
      try {
        render(<CommandInput character="Alice" />);
        const textarea = screen.getByRole('textbox');
        fireEvent.change(textarea, { target: { value: 'a private-browsing draft' } });

        expect(
          screen.getByText("Draft kept in this tab only — it won't survive a reload.")
        ).toBeInTheDocument();
      } finally {
        setItemSpy.mockRestore();
      }
    });

    it('does not show the storage-unavailable notice when sessionStorage writes succeed', () => {
      render(<CommandInput character="Alice" />);
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'an ordinary draft' } });

      expect(
        screen.queryByText("Draft kept in this tab only — it won't survive a reload.")
      ).not.toBeInTheDocument();
    });
  });
});

describe('mention autocomplete source', () => {
  beforeEach(() => {
    queryClient.clear();
  });

  it('uses scene participants when sceneId is provided', async () => {
    fetchSceneMock.mockResolvedValue({
      id: 42,
      name: 'Test Scene',
      participants: [{ id: 1, name: 'ScenePersona', roster_entry: null }],
      is_active: true,
      is_owner: false,
      description: '',
      date_started: '',
      location: null,
    });

    render(<CommandInput character="Alice" sceneId="42" />);

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    Object.defineProperty(textarea, 'selectionStart', { value: 1, writable: true });
    fireEvent.change(textarea, { target: { value: '@', selectionStart: 1 } });

    await screen.findByText('ScenePersona');
    expect(screen.queryByText('Bob')).not.toBeInTheDocument();
  });
});
