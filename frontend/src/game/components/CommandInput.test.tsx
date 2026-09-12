import { render as rtlRender, screen, fireEvent, waitFor, act } from '@testing-library/react';
import type { RenderOptions } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';
import { emitActionResult } from '@/hooks/actionResultBus';
import { draftStorageKey } from '@/game/useDraftStore';
import type { Draft } from '@/game/useDraftStore';
import type { CompanionSummary } from '@/companions/types';

// Wrap every render call in a QueryClientProvider so useQuery hooks work in tests.
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function render(ui: ReactElement, options?: RenderOptions) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return rtlRender(ui, { wrapper: Wrapper, ...options });
}

// #3781 — `handleActionResult` now matches on `client_request_id` rather than
// assuming the next bus event is this dispatch's own, so a test simulating
// the ack must echo back the id the component actually dispatched.
function lastDispatchedRequestId(): string {
  const calls = executeActionMock.mock.calls;
  const kwargs = calls[calls.length - 1][2] as { client_request_id: string };
  return kwargs.client_request_id;
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

// #3294 companion-emote branch (Finding 5, #3760 final review) — CompanionSelector
// self-fetches via useMyCompanions and renders nothing when no companion is
// present, so it's unreachable through the real UI without controlling this
// query directly. Defaults to no companions (renders null, byte-identical to
// every other test in this file); the companion-emote describe block below
// overrides it to a single present companion.
const mockUseMyCompanions = vi.fn((): { data: CompanionSummary[] } => ({ data: [] }));
const companionEmoteMock = vi.fn(
  (_companionId: number, _text: string, _clientRequestId?: string): Promise<void> =>
    Promise.resolve()
);

vi.mock('@/companions/queries', () => ({
  useMyCompanions: () => mockUseMyCompanions(),
}));

vi.mock('@/companions/api', () => ({
  companionEmote: (...args: [number, string, string?]) => companionEmoteMock(...args),
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
    mockUseMyCompanions.mockClear();
    mockUseMyCompanions.mockReturnValue({ data: [] });
    companionEmoteMock.mockClear();
    companionEmoteMock.mockImplementation(() => Promise.resolve());
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
      client_request_id: expect.any(String),
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
      client_request_id: expect.any(String),
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
      client_request_id: expect.any(String),
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
      client_request_id: expect.any(String),
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
  // #3760 Task 16 fix — the REST submit-pose path (the "canonical route for
  // scene poses" per queries.ts) previously never sent `client_request_id`
  // at all, so every ordinary in-scene pose 400'd against the backend's
  // required field. These mirror the WS say/whisper/tt ack-gating tests
  // above, adapted for the promise-based REST flow.
  // ---------------------------------------------------------------------------

  it('a REST pose retry of unmodified content reuses the same client_request_id (#3760 fix)', () => {
    seedDraft(
      {
        status: 'rejected',
        rejectionReason: 'Not co-located.',
        clientRequestId: 'req-pose-rejected',
        content: 'looks around',
      },
      'pose-retry-scope',
      9
    );

    render(
      <CommandInput character="Alice" sceneId="5" personaId={9} draftScope="pose-retry-scope" />
    );
    // The textarea is enabled for a `rejected` draft — the ordinary Send
    // button, not a Task-11-specific Retry affordance.
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));

    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 5,
      content: 'looks around',
      client_request_id: 'req-pose-rejected',
    });
  });

  it('does not clear a newer edit made after a REST pose request was sent but before the response arrives', async () => {
    let resolveSubmit: (value: unknown) => void = () => {};
    submitPoseMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSubmit = resolve;
        })
    );
    const onPoseSubmitted = vi.fn();
    render(
      <CommandInput character="Alice" sceneId="5" personaId={9} onPoseSubmitted={onPoseSubmitted} />
    );
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

    fireEvent.change(textarea, { target: { value: 'looks around' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(submitPoseMock).toHaveBeenCalledWith(
      expect.objectContaining({ content: 'looks around' })
    );

    // A newer, unsent edit happens while the original request is still in
    // flight — it must survive the eventual ack for the OLDER content.
    fireEvent.change(textarea, { target: { value: 'looks around, then frowns' } });

    resolveSubmit({ id: 1 });
    await waitFor(() => expect(onPoseSubmitted).toHaveBeenCalled());

    expect(textarea.value).toBe('looks around, then frowns');
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
      client_request_id: expect.any(String),
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
      client_request_id: expect.any(String),
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
      client_request_id: expect.any(String),
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
      emitActionResult({
        success: true,
        message: null,
        data: null,
        client_request_id: lastDispatchedRequestId(),
      });
    });

    expect(textarea.value).toBe('');
  });

  it('ignores an ACTION_RESULT for a different dispatch, then resolves on the matching one (#3781)', () => {
    const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

    fireEvent.change(textarea, { target: { value: 'hello there' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    // A concurrent, unrelated action's result (e.g. an inventory action fired
    // from another panel) must not be mistaken for this send's ack, even
    // though it arrives first on the same bus.
    act(() => {
      emitActionResult({
        success: true,
        message: null,
        data: null,
        client_request_id: 'unrelated-dispatch',
      });
    });
    expect(textarea.value).toBe('hello there');

    act(() => {
      emitActionResult({
        success: true,
        message: null,
        data: null,
        client_request_id: lastDispatchedRequestId(),
      });
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
      emitActionResult({
        success: false,
        message: 'You have been muted.',
        data: null,
        client_request_id: lastDispatchedRequestId(),
      });
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
   * reconnect reconciliation owns that). `personaId` defaults to 0 (matching
   * every pre-#3760-Task-16 call site, none of which pass a `personaId` prop
   * to `CommandInput`); the REST-pose tests (#3760 Task 16) pass the same
   * `personaId` they render `CommandInput` with, since that value is part of
   * the draft storage key.
   */
  function seedDraft(
    overrides: Partial<Draft>,
    conversationKey = 'character:Alice',
    personaId = 0
  ) {
    const key = draftStorageKey({ accountId: 0, personaId, conversationKey });
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
      mode: null,
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
        emitActionResult({
          success: true,
          message: null,
          data: null,
          client_request_id: lastDispatchedRequestId(),
        });
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
        emitActionResult({
          success: false,
          message: 'You have been muted.',
          data: null,
          client_request_id: lastDispatchedRequestId(),
        });
      });

      expect(screen.getByText(/You have been muted\./)).toBeInTheDocument();
      expect(textarea).toBeEnabled();
    });

    // #3760 Task 11 review fix — "Check status"/Retry (the live-unknown
    // banner, demo Screen 3b) and the stranded banner (demo Screen 4) are
    // ALTERNATIVES that never render together (see `composerBanner` in
    // CommandInput.tsx). A draft hydrated from storage as `unknown` is BY
    // DEFINITION stranded (nothing dispatched this session can match its
    // `clientRequestId`), so it always resolves to the stranded banner here —
    // there is currently no way to reach the live-unknown banner from
    // CommandInput's own props/events, since nothing in this task (or yet in
    // the codebase) calls `markUnknown()` while a send is still genuinely in
    // flight in the SAME tab; that trigger is Task 12's reconnect
    // reconciliation. The "Check status"/Retry code path is intentionally
    // implemented ahead of that wiring (per the plan's task split) and is
    // exercised at the `useDraftStore` unit level (`markUnknown` tests) —
    // Task 12 should add its own CommandInput-level coverage once it can
    // actually reach this banner.
    it('a hydrated unknown-status draft resolves to the stranded banner, not the live Check status/Retry pair', () => {
      seedDraft({ status: 'unknown', clientRequestId: 'req-unknown' });

      render(<CommandInput character="Alice" />);

      expect(screen.getByText(/Unsent draft from/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Discard' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Resume & retry' })).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Check status' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
    });

    it('shows the stranded-draft banner for a pending draft hydrated from storage with no live send in flight', () => {
      const mode: ComposerMode = { command: 'pose', targets: [], label: 'The Gilded Hart' };
      seedDraft({ status: 'pending', clientRequestId: 'req-stranded' });

      render(<CommandInput character="Alice" composerMode={mode} />);

      expect(screen.getByText(/Unsent draft from The Gilded Hart/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Discard' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Resume & retry' })).toBeInTheDocument();
      // Mutually exclusive with every other banner (#3760 Task 11 review fix).
      expect(screen.queryByText('Sending…')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Check status' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
    });

    // #3760 demo-fidelity review — the default room-pose state (no
    // composerMode label set, the state demo Screen 1 itself shows) must
    // never leak the raw `draftScope` cache key into this banner's copy.
    it('falls back to roomName, never the raw draftScope cache key, when no composerMode label is set', () => {
      seedDraft(
        { status: 'pending', clientRequestId: 'req-stranded' },
        'account:1:Alice:room:2',
        0
      );

      render(
        <CommandInput
          character="Alice"
          draftScope="account:1:Alice:room:2"
          roomName="The Gilded Hart"
        />
      );

      expect(screen.getByText(/Unsent draft from The Gilded Hart/)).toBeInTheDocument();
      expect(screen.queryByText(/account:1:Alice:room:2/)).not.toBeInTheDocument();
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

    // -------------------------------------------------------------------------
    // Critical fix (#3760 Task 11 review): an unmodified retry/resend of an
    // already-composed whisper must redispatch AS A WHISPER, never as
    // whatever mode the composer currently shows — see `resolvedSpeechMode`'s
    // doc comment in CommandInput.tsx and `beginSend`'s in useDraftStore.ts.
    // -------------------------------------------------------------------------

    it('"Resume & retry" redispatches under the ORIGINALLY stored whisper mode even though the live composerMode has since changed to pose', () => {
      // Bob is resolvable via the `@/store/hooks` mock's roomCharacters (dbref
      // #501) — see the top of this file.
      seedDraft(
        {
          status: 'pending',
          clientRequestId: 'req-whisper-stranded',
          content: 'secret message',
          mode: { command: 'whisper', targets: ['Bob'] },
        },
        'test-scope'
      );
      // The LIVE composer mode is now 'pose' — e.g. the tab reopened on the
      // room feed, or the player switched modes without touching the text.
      const liveMode: ComposerMode = { command: 'pose', targets: [], label: 'Pose' };

      render(<CommandInput character="Alice" composerMode={liveMode} draftScope="test-scope" />);
      fireEvent.click(screen.getByRole('button', { name: 'Resume & retry' }));

      expect(executeActionMock).toHaveBeenCalledWith('Alice', 'whisper', {
        text: 'secret message',
        target_id: 501,
        client_request_id: 'req-whisper-stranded',
      });
      expect(sendMock).not.toHaveBeenCalled();
      expect(submitPoseMock).not.toHaveBeenCalled();
    });

    it('an ordinary Send on an untouched rejected whisper draft redispatches as whisper, not the live pose mode (the Send-button leak)', () => {
      seedDraft(
        {
          status: 'rejected',
          rejectionReason: 'Bob stepped away.',
          clientRequestId: 'req-whisper-rejected',
          content: 'secret message',
          mode: { command: 'whisper', targets: ['Bob'] },
        },
        'test-scope'
      );
      const liveMode: ComposerMode = { command: 'pose', targets: [], label: 'Pose' };

      render(<CommandInput character="Alice" composerMode={liveMode} draftScope="test-scope" />);
      // The textarea is enabled for a `rejected` draft — this is the ordinary
      // Send button, not a Task-11-specific Retry affordance.
      fireEvent.click(screen.getByRole('button', { name: 'Send' }));

      expect(executeActionMock).toHaveBeenCalledWith('Alice', 'whisper', {
        text: 'secret message',
        target_id: 501,
        client_request_id: 'req-whisper-rejected',
      });
      expect(sendMock).not.toHaveBeenCalled();
      expect(submitPoseMock).not.toHaveBeenCalled();
    });

    it('a legacy WS fallback dispatch (unresolvable whisper target) clears the v2 draft so no stranded banner reappears (Finding 3760 final review)', () => {
      // Bob (dbref #501) is the only resolvable name in this file's
      // `@/store/hooks` mock — "Departed" is deliberately NOT in
      // roomCharacters, so the whisper branch's target lookup fails and
      // handleSubmit falls through to the legacy `send()` path instead of
      // `executeAction`, exactly the condition Finding 4 describes.
      seedDraft(
        {
          status: 'pending',
          clientRequestId: 'req-legacy-fallback',
          content: 'a secret for someone gone',
          mode: { command: 'whisper', targets: ['Departed'] },
        },
        'test-scope'
      );

      render(<CommandInput character="Alice" draftScope="test-scope" />);
      expect(screen.getByText(/Unsent draft from/)).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Resume & retry' }));

      expect(sendMock).toHaveBeenCalledWith('Alice', 'whisper Departed=a secret for someone gone');
      expect(executeActionMock).not.toHaveBeenCalled();
      // The v2 draft must be reset to clean, not left `pending` -- otherwise
      // the stranded banner re-renders on the next tick over the now-empty
      // textarea, dismissible only via Discard.
      expect(screen.queryByText(/Unsent draft from/)).not.toBeInTheDocument();
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      expect(textarea.value).toBe('');
    });

    it('editing the text after a stranded whisper draft picks up the CURRENT live mode instead (an edit is a genuinely new attempt)', () => {
      seedDraft(
        {
          status: 'rejected',
          rejectionReason: 'Bob stepped away.',
          clientRequestId: 'req-whisper-rejected',
          content: 'secret message',
          mode: { command: 'whisper', targets: ['Bob'] },
        },
        'test-scope'
      );
      const liveMode: ComposerMode = { command: 'say', targets: [], label: 'Say' };

      render(<CommandInput character="Alice" composerMode={liveMode} draftScope="test-scope" />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      // A genuine edit — the whole point of `setContent` clearing `mode`.
      fireEvent.change(textarea, { target: { value: 'secret message, revised' } });
      fireEvent.click(screen.getByRole('button', { name: 'Send' }));

      expect(executeActionMock).toHaveBeenCalledWith('Alice', 'say', {
        text: 'secret message, revised',
        client_request_id: expect.any(String),
      });
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

    // #3760 Task 12 — a reconnect mid-send is the first place `markUnknown()`
    // gets called in production (see the long comment above the effect in
    // CommandInput.tsx, and the "hydrated unknown-status draft" test above,
    // which documents why this exact scenario was previously unreachable).
    // `ready` flipping false then true again (never the initial mount) is
    // what `useGameSocket`'s reconnect-open handler (#3760 Task 12) produces
    // once it has reauthorized and reconciled every stored draft.
    describe('reconnect mid-send (#3760 Task 12)', () => {
      it('marks a live in-flight send unknown on reconnect and auto-resolves it via the lookup endpoint once it landed', async () => {
        const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
        fetchPoseSubmissionMock.mockResolvedValueOnce({ interaction_id: 7, replayed: false });

        const { rerender } = render(<CommandInput character="Alice" composerMode={mode} ready />);
        const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

        fireEvent.change(textarea, { target: { value: 'hello' } });
        fireEvent.keyDown(textarea, { key: 'Enter' });
        expect(screen.getByText('Sending…')).toBeInTheDocument();
        expect(fetchPoseSubmissionMock).not.toHaveBeenCalled();

        // The connection drops (ready -> false) and later reconnects
        // (useGameSocket's open handler flips ready back to true only after
        // it has reauthorized and reconciled every stored draft).
        rerender(<CommandInput character="Alice" composerMode={mode} ready={false} />);
        rerender(<CommandInput character="Alice" composerMode={mode} ready />);

        // The automatic lookup this reconnect triggers found the record: the
        // send had landed, so it resolves exactly like an ordinary ack —
        // never left showing "Sending…" forever for a reply that can no
        // longer arrive on the new connection.
        await waitFor(() => expect(fetchPoseSubmissionMock).toHaveBeenCalledTimes(1));
        expect(fetchPoseSubmissionMock).toHaveBeenCalledWith(expect.any(String));
        await waitFor(() => expect(screen.queryByText('Sending…')).not.toBeInTheDocument());
        expect(screen.queryByText(/Unsent draft from/)).not.toBeInTheDocument();
        expect(textarea.value).toBe('');
      });

      it('leaves the draft resolvable via the live-unknown banner when the reconnect lookup finds no record', async () => {
        const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
        fetchPoseSubmissionMock.mockResolvedValueOnce(null);

        const { rerender } = render(<CommandInput character="Alice" composerMode={mode} ready />);
        const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

        fireEvent.change(textarea, { target: { value: 'hello' } });
        fireEvent.keyDown(textarea, { key: 'Enter' });
        expect(screen.getByText('Sending…')).toBeInTheDocument();

        rerender(<CommandInput character="Alice" composerMode={mode} ready={false} />);
        rerender(<CommandInput character="Alice" composerMode={mode} ready />);

        await waitFor(() => expect(fetchPoseSubmissionMock).toHaveBeenCalledTimes(1));
        // No record found: the send's fate is genuinely unresolved. The text
        // is never lost — still editable/resendable, not silently dropped.
        expect(textarea.value).toBe('hello');
        expect(screen.queryByText('Sending…')).not.toBeInTheDocument();
      });

      // Demo-fidelity review Finding 1 (#3760) — the reconnect effect used to
      // null `pendingSpeechRef.current` BEFORE calling `markUnknown()`, so the
      // very next render's `isStrandedDraft` check saw a null ref against a
      // non-clean `draft.status` and read this as a reopened-tab stranded
      // draft (Screen 4: Discard/"Resume & retry"), never the live-unknown
      // banner (Screen 3b: Check status/Retry) the demo actually specifies for
      // a reconnect-driven transition. This drives the REAL flow (a real send
      // through `pendingSpeechRef`, a real `ready` false->true reconnect) and
      // inspects the banner BEFORE the lookup settles — the transient state a
      // player actually sees — rather than mocking `draft.status: 'unknown'`
      // directly, which is how the earlier "hydrated unknown-status draft"
      // test above sidesteps this exact bug (see its own comment).
      it('shows the LIVE unknown banner (Check status/Retry), not the stranded banner, right after a reconnect marks an in-flight send unknown', () => {
        const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
        // Never resolves within this test's assertion window — inspecting the
        // banner in the transient state between the reconnect completing and
        // the auto-triggered "Check status" lookup settling.
        fetchPoseSubmissionMock.mockImplementation(() => new Promise(() => {}));

        const { rerender } = render(<CommandInput character="Alice" composerMode={mode} ready />);
        const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

        fireEvent.change(textarea, { target: { value: 'hello' } });
        fireEvent.keyDown(textarea, { key: 'Enter' });
        expect(screen.getByText('Sending…')).toBeInTheDocument();

        rerender(<CommandInput character="Alice" composerMode={mode} ready={false} />);
        rerender(<CommandInput character="Alice" composerMode={mode} ready />);

        expect(screen.getByTestId('send-unknown-banner')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Check status' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
        expect(screen.queryByTestId('stranded-draft-banner')).not.toBeInTheDocument();
        expect(screen.queryByText(/Unsent draft from/)).not.toBeInTheDocument();
      });

      it('does not touch the draft on a plain ready toggle with nothing in flight', () => {
        const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
        const { rerender } = render(<CommandInput character="Alice" composerMode={mode} ready />);

        rerender(<CommandInput character="Alice" composerMode={mode} ready={false} />);
        rerender(<CommandInput character="Alice" composerMode={mode} ready />);

        expect(fetchPoseSubmissionMock).not.toHaveBeenCalled();
      });

      // #3760 Task 12 review fix — `useGameSocket`'s own storage-level
      // `reconcileStoredDrafts` scan (the session-wide reconciliation that
      // gates `ready` itself) can resolve this EXACT draft as landed before
      // this effect ever runs, by writing straight to sessionStorage. Proves
      // the fix in CommandInput.tsx's effect: it must notice that and
      // acknowledge, never clobber the already-correct resolution back to
      // `unknown`.
      it('does not clobber a draft the session-level reconciliation scan already resolved as landed', () => {
        const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
        const { rerender } = render(<CommandInput character="Alice" composerMode={mode} ready />);
        const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

        fireEvent.change(textarea, { target: { value: 'hello' } });
        fireEvent.keyDown(textarea, { key: 'Enter' });
        expect(screen.getByText('Sending…')).toBeInTheDocument();

        rerender(<CommandInput character="Alice" composerMode={mode} ready={false} />);

        // Simulate `useGameSocket`'s open handler resolving this exact draft
        // via its own sessionStorage-level scan WHILE `ready` is still
        // false — writing straight to storage the same way
        // `reconcileStoredDrafts` does, bypassing this hook's in-memory
        // state entirely.
        const storageKey = draftStorageKey({
          accountId: 0,
          personaId: 0,
          conversationKey: 'character:Alice',
        });
        const rawBefore = sessionStorage.getItem(storageKey);
        expect(rawBefore).not.toBeNull();
        const draftBefore = JSON.parse(rawBefore as string) as Draft;
        expect(draftBefore.status).toBe('pending');
        sessionStorage.setItem(
          storageKey,
          JSON.stringify({ ...draftBefore, status: 'clean', clientRequestId: null })
        );

        // The reconnect completes (ready -> true): this must acknowledge
        // (sync to `clean`), not mark unknown and fire a redundant lookup.
        rerender(<CommandInput character="Alice" composerMode={mode} ready />);

        expect(fetchPoseSubmissionMock).not.toHaveBeenCalled();
        expect(screen.queryByText('Sending…')).not.toBeInTheDocument();
        expect(screen.queryByText(/Unsent draft from/)).not.toBeInTheDocument();
      });
    });
  });

  // ---------------------------------------------------------------------------
  // One draft store (#3784) — the composer used to keep a second, v1-keyed
  // sessionStorage string that was what actually hydrated the textarea, and
  // hand-sync it with `useDraftStore` in five places. These cover the
  // behaviours that survived only because both copies happened to agree.
  // ---------------------------------------------------------------------------

  describe('single draft store (#3784)', () => {
    function storedDraft(conversationKey: string, personaId = 0): Draft {
      const raw = sessionStorage.getItem(
        draftStorageKey({ accountId: 0, personaId, conversationKey })
      );
      expect(raw).not.toBeNull();
      return JSON.parse(raw as string) as Draft;
    }

    it('hydrates the textarea from the stored draft content on mount', () => {
      seedDraft({ content: 'half a thought', status: 'clean', clientRequestId: null }, 'room:1');

      render(<CommandInput character="Alice" draftScope="room:1" />);

      expect(screen.getByRole('textbox')).toHaveValue('half a thought');
    });

    it('writes typed text straight to the draft row, with no second key alongside it', () => {
      // Fake timers on purpose: the retired v1 copy was written on a 500ms
      // debounce, so a real-timer assertion here would pass either way and
      // guard nothing. Letting that timer come due is what makes "exactly one
      // persisted key" a claim about the code rather than about test timing.
      vi.useFakeTimers();
      try {
        render(<CommandInput character="Alice" draftScope="room:1" />);
        fireEvent.change(screen.getByRole('textbox'), { target: { value: 'a line in progress' } });
        act(() => {
          vi.advanceTimersByTime(1000);
        });

        expect(storedDraft('room:1').content).toBe('a line in progress');
        expect(Object.keys(sessionStorage)).toEqual([
          draftStorageKey({ accountId: 0, personaId: 0, conversationKey: 'room:1' }),
        ]);
      } finally {
        vi.useRealTimers();
      }
    });

    it('swaps drafts when draftScope changes and carries no text between rooms', () => {
      seedDraft(
        { content: 'left in the taproom', status: 'clean', clientRequestId: null },
        'room:1'
      );
      const { rerender } = render(<CommandInput character="Alice" draftScope="room:1" />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      expect(textarea.value).toBe('left in the taproom');

      // Walking through an exit: a different conversation, its own empty draft.
      rerender(<CommandInput character="Alice" draftScope="room:2" />);
      expect(textarea.value).toBe('');
      fireEvent.change(textarea, { target: { value: 'composed upstairs' } });

      // ...and back. Each room kept its own unsent text.
      rerender(<CommandInput character="Alice" draftScope="room:1" />);
      expect(textarea.value).toBe('left in the taproom');
      expect(storedDraft('room:2').content).toBe('composed upstairs');
    });

    it('appends a @target onto the existing draft and persists the result', () => {
      const onTargetConsumed = vi.fn();
      const { rerender } = render(
        <CommandInput character="Alice" draftScope="room:1" onTargetConsumed={onTargetConsumed} />
      );
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'nods at' } });

      rerender(
        <CommandInput
          character="Alice"
          draftScope="room:1"
          targetToAppend="Bob"
          onTargetConsumed={onTargetConsumed}
        />
      );

      expect(textarea.value).toBe('nods at @Bob');
      expect(storedDraft('room:1').content).toBe('nods at @Bob');
      expect(onTargetConsumed).toHaveBeenCalled();
    });

    it('a rejected send keeps its text on screen AND in storage, ready to retry', () => {
      const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
      render(<CommandInput character="Alice" composerMode={mode} draftScope="room:1" />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      fireEvent.change(textarea, { target: { value: 'hello there' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      act(() => {
        emitActionResult({
          success: false,
          message: 'You have been muted.',
          data: null,
          client_request_id: lastDispatchedRequestId(),
        });
      });

      expect(textarea.value).toBe('hello there');
      const stored = storedDraft('room:1');
      expect(stored.content).toBe('hello there');
      expect(stored.status).toBe('rejected');
    });

    it('an ack clears content and status together — the pair that used to be able to drift', () => {
      const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
      render(<CommandInput character="Alice" composerMode={mode} draftScope="room:1" />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      fireEvent.change(textarea, { target: { value: 'hello there' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      act(() => {
        emitActionResult({
          success: true,
          message: null,
          data: null,
          client_request_id: lastDispatchedRequestId(),
        });
      });

      expect(textarea.value).toBe('');
      const stored = storedDraft('room:1');
      expect(stored.content).toBe('');
      expect(stored.status).toBe('clean');
      expect(stored.clientRequestId).toBeNull();
    });

    it('recalls a sent command with ArrowUp once the composer is empty again', () => {
      const mode: ComposerMode = { command: 'say', targets: [], label: 'Say' };
      render(<CommandInput character="Alice" composerMode={mode} draftScope="room:1" />);
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;

      fireEvent.change(textarea, { target: { value: 'hello there' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      act(() => {
        emitActionResult({
          success: true,
          message: null,
          data: null,
          client_request_id: lastDispatchedRequestId(),
        });
      });
      expect(textarea.value).toBe('');

      fireEvent.keyDown(textarea, { key: 'ArrowUp' });

      expect(textarea.value).toBe('hello there');
      expect(storedDraft('room:1').content).toBe('hello there');
    });
  });
});

// #3294 companion-emote branch, Finding 5 (#3760 final review): the
// REST-pose branch and the WS ack handler both guard their clear-on-success
// with `if (commandRef.current === trimmed)` to protect a newer edit typed
// while the request is in flight -- the companion-emote branch cleared
// unconditionally instead.
describe('companion emote branch (#3294, Finding 5)', () => {
  const fenwick: CompanionSummary = {
    id: 42,
    name: 'Fenwick',
    archetype: { id: 1, name: 'Fox' } as CompanionSummary['archetype'],
    bonded_at: '2026-01-01T00:00:00Z',
    released_at: null,
    objectdb_id: null,
    is_present: true,
  };

  beforeEach(() => {
    mockUseMyCompanions.mockReturnValue({ data: [fenwick] });
  });

  async function selectCompanion() {
    const user = userEvent.setup();
    await user.click(screen.getByTestId('companion-selector-trigger'));
    await user.click(screen.getByText('Fenwick'));
  }

  it('dispatches companionEmote and clears the draft on success', async () => {
    render(<CommandInput character="Alice" />);
    await selectCompanion();

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'grooms itself.' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    await waitFor(() =>
      expect(companionEmoteMock).toHaveBeenCalledWith(42, 'grooms itself.', expect.any(String))
    );
    await waitFor(() => expect(textarea.value).toBe(''));
  });

  it('does not clear a newer edit made after a companion emote request was sent but before the response arrives', async () => {
    let resolveEmote: () => void = () => {};
    companionEmoteMock.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveEmote = resolve;
        })
    );

    render(<CommandInput character="Alice" />);
    await selectCompanion();

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'grooms itself.' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(companionEmoteMock).toHaveBeenCalledWith(42, 'grooms itself.', expect.any(String));

    // A newer, unsent edit happens while the original request is still in
    // flight — it must survive the eventual success response for the OLDER
    // content, the same guarantee the REST-pose branch already has.
    fireEvent.change(textarea, { target: { value: 'grooms itself, then yawns.' } });

    resolveEmote();
    await waitFor(() => expect(companionEmoteMock).toHaveBeenCalledTimes(1));

    expect(textarea.value).toBe('grooms itself, then yawns.');
  });

  it('threads a client_request_id and reuses it on retry of unmodified content (#3782)', async () => {
    companionEmoteMock.mockImplementationOnce(() => Promise.reject(new Error('Fenwick left.')));

    render(<CommandInput character="Alice" />);
    await selectCompanion();

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'grooms itself.' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    await waitFor(() =>
      expect(companionEmoteMock).toHaveBeenCalledWith(42, 'grooms itself.', expect.any(String))
    );
    const [, , firstRequestId] = companionEmoteMock.mock.calls[0];
    expect(typeof firstRequestId).toBe('string');
    // Rejected, not acknowledged -- the text must survive for a retry.
    await waitFor(() => expect(textarea.value).toBe('grooms itself.'));

    // A retry (server rejected, or a dropped connection) of the SAME
    // unmodified content must reuse the same id, not mint a fresh one --
    // that's what makes the server's idempotency check
    // (`idempotent_record_interaction`) actually dedupe the retry.
    fireEvent.keyDown(textarea, { key: 'Enter' });

    await waitFor(() => expect(companionEmoteMock).toHaveBeenCalledTimes(2));
    const [, , secondRequestId] = companionEmoteMock.mock.calls[1];
    expect(secondRequestId).toBe(firstRequestId);
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
