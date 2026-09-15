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
import type { Interaction } from '@/scenes/types';

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
const sendConsoleMock = vi.fn();
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
  useGameSocket: () => ({
    send: sendMock,
    sendConsole: sendConsoleMock,
    executeAction: executeActionMock,
  }),
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
//
// #3810 -- `mockRoomCharacters` is mutable (mirrors `mockUseMyCompanions`
// below) so the tag-reachability tests can vary a character's `place_id`
// per test without touching every other test in this file that relies on
// Bob's resolvable dbref (#501) for the whisper-target-resolution tests
// above. Reset to the default in `beforeEach`.
let mockRoomCharacters: Array<{
  name: string;
  thumbnail_url: string | null;
  dbref: string;
  place_id?: number | null;
}> = [{ name: 'Bob', thumbnail_url: null, dbref: '#501' }];
// The room's live scene as the store holds it (#3867); tests set `viewer_entered`.
let mockScene: { id: number; viewer_entered: boolean } | null = null;
beforeEach(() => {
  mockScene = null;
});

vi.mock('@/store/hooks', () => ({
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({
      game: {
        active: 'Alice',
        sessions: {
          Alice: {
            room: { characters: mockRoomCharacters },
            scene: mockScene,
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
    sendConsoleMock.mockClear();
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
    mockRoomCharacters = [{ name: 'Bob', thumbnail_url: null, dbref: '#501' }];
    queryClient.clear();
    // useDraftStore (#3760 Task 10) persists to sessionStorage under a key
    // derived from account/persona/conversation — several tests in this file
    // share the same derived key (no draftScope passed), so a leftover draft
    // from one test would otherwise leak into the next test's hydration.
    sessionStorage.clear();
  });

  describe('the slash escape and the staff Commands mode (#3857)', () => {
    const pose: ComposerMode = { command: 'pose', targets: [], label: 'Pose \u2192 Room' };

    it('a line starting with / is sent as the command after the slash, never wrapped', () => {
      render(<CommandInput character="Alice" composerMode={pose} />);
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: '/look' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(sendMock).toHaveBeenCalledWith('Alice', 'look');
      expect(executeActionMock).not.toHaveBeenCalled();
    });

    it('a / line in say mode is still a command, not speech', () => {
      const say: ComposerMode = { command: 'say', targets: [], label: 'Say' };
      render(<CommandInput character="Alice" composerMode={say} />);
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: '/get lantern' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(sendMock).toHaveBeenCalledWith('Alice', 'get lantern');
      expect(executeActionMock).not.toHaveBeenCalled();
    });

    it('a / line in a scene goes over the socket as typed, never to the pose endpoint', () => {
      render(<CommandInput character="Alice" composerMode={pose} sceneId="5" personaId={9} />);
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: '/look' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(sendMock).toHaveBeenCalledWith('Alice', 'look');
      expect(submitPoseMock).not.toHaveBeenCalled();
      // A typed speech verb or `page` still passes through as typed; any
      // other verb is a pose, since the label is the truth.
      fireEvent.change(textarea, { target: { value: 'page Nyx=on my way' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(sendMock).toHaveBeenLastCalledWith('Alice', 'page Nyx=on my way');
      expect(submitPoseMock).not.toHaveBeenCalled();
      fireEvent.change(textarea, { target: { value: 'look' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(submitPoseMock).toHaveBeenCalledWith(
        expect.objectContaining({ scene_id: 5, content: 'look' })
      );
    });

    it('a // line in a scene poses a literal slash through the pose endpoint', () => {
      render(<CommandInput character="Alice" composerMode={pose} sceneId="5" personaId={9} />);
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: '//shrugs' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(submitPoseMock).toHaveBeenCalledWith(
        expect.objectContaining({ scene_id: 5, content: '/shrugs' })
      );
      expect(sendMock).not.toHaveBeenCalled();
    });

    it('a line starting with // poses a literal slash', () => {
      render(<CommandInput character="Alice" composerMode={pose} />);
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: '//shrugs' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(sendMock).toHaveBeenCalledWith('Alice', 'pose /shrugs');
    });

    it('offers Commands in the selector for staff only', async () => {
      const user = userEvent.setup();
      const { unmount } = render(<CommandInput character="Alice" composerMode={pose} isStaff />);
      await user.click(screen.getByRole('button', { name: /pose/i }));
      expect(screen.getByRole('menuitem', { name: 'Commands' })).toBeInTheDocument();
      await user.keyboard('{Escape}');
      unmount();

      render(<CommandInput character="Alice" composerMode={pose} />);
      await user.click(screen.getByRole('button', { name: /pose/i }));
      expect(screen.queryByRole('menuitem', { name: 'Commands' })).not.toBeInTheDocument();
    });

    it('in Commands mode every line goes through sendConsole as typed, with the formatting hidden', () => {
      const commands: ComposerMode = { command: 'commands', targets: [], label: 'Commands' };
      render(<CommandInput character="Alice" composerMode={commands} isStaff />);
      expect(screen.queryByRole('button', { name: 'Bold' })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^Console/ })).toBeInTheDocument();
      const textarea = screen.getByRole('textbox');
      expect(textarea).toHaveClass('font-mono');
      fireEvent.change(textarea, { target: { value: '@dig East = east;e, west;w' } });
      fireEvent.keyDown(textarea, { key: 'Enter' });
      expect(sendConsoleMock).toHaveBeenCalledWith('Alice', '@dig East = east;e, west;w');
      expect(sendMock).not.toHaveBeenCalled();
      expect(textarea).toHaveValue('');
    });

    it('picking a mode works before any mode was set', async () => {
      const user = userEvent.setup();
      const onModeChange = vi.fn();
      render(<CommandInput character="Alice" onModeChange={onModeChange} />);
      await user.click(screen.getByRole('button', { name: /pose/i }));
      await user.click(screen.getByRole('menuitem', { name: /say/i }));
      expect(onModeChange).toHaveBeenCalledWith({ command: 'say', targets: [], label: 'Say' });
    });
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
    // #3810 -- both targets must be physically in the room for the new
    // pre-emptive tag-reachability check to let this submit through; Carol
    // isn't in the default `mockRoomCharacters` roster, so she's added here.
    mockRoomCharacters = [
      { name: 'Bob', thumbnail_url: null, dbref: '#501' },
      { name: 'Carol', thumbnail_url: null, dbref: '#502' },
    ];
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

  // #3867 — the entrance is a state the room reports, never a toggle.
  it('shows no entrance state and no technique attachment once the viewer has entered', () => {
    mockScene = { id: 1, viewer_entered: true };
    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);
    expect(screen.queryByTestId('entrance-state')).toBeNull();
    expect(screen.queryByTestId('entrance-technique-attachment')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Make an entrance' })).toBeNull();
  });

  it('shows the entrance state with the technique attachment before the first pose', () => {
    mockScene = { id: 1, viewer_entered: false };
    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);
    expect(screen.getByTestId('entrance-state')).toHaveTextContent('Entrance');
    expect(screen.getByTestId('entrance-technique-attachment')).toBeInTheDocument();
  });

  it('sends the first pose as the entrance', () => {
    mockScene = { id: 1, viewer_entered: false };
    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'steps in from the rain.' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(submitPoseMock).toHaveBeenCalledWith(expect.objectContaining({ pose_kind: 'entry' }));
  });

  it('submitting an entrance pose with an attached technique dispatches createActionRequest with the submitPose response id (#2183)', async () => {
    submitPoseMock.mockImplementation(() => Promise.resolve({ id: 123 }));

    mockScene = { id: 1, viewer_entered: false };
    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);

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

    mockScene = { id: 1, viewer_entered: false };
    render(<CommandInput character="Alice" sceneId="1" personaId={9} />);

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

    // #3784 — a draft typed during "Entering world" used to vanish the moment
    // presence arrived: `GameWindow` scopes the room-anchor draft as
    // `room:${roomId ?? 'unknown'}` (#3760 Task 14), so the text persisted
    // under the placeholder while the composer re-keyed to the real room and
    // hydrated an empty row. Covered end to end by `e2e/game-entry.spec.ts`;
    // this is the component-level guard for the prop that fixes it.
    it('carries the draft into the real room when a provisional scope settles', () => {
      const { rerender } = render(
        <CommandInput
          character="Alice"
          draftScope="room:unknown"
          draftScopeSettling={{ provisional: true, conversation: 'room-anchor' }}
        />
      );
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A quiet beginning.' } });

      rerender(
        <CommandInput
          character="Alice"
          draftScope="room:2"
          draftScopeSettling={{ conversation: 'room-anchor' }}
        />
      );

      expect(textarea.value).toBe('A quiet beginning.');
      expect(storedDraft('room:2').content).toBe('A quiet beginning.');
      expect(
        sessionStorage.getItem(
          draftStorageKey({ accountId: 0, personaId: 0, conversationKey: 'room:unknown' })
        )
      ).toBeNull();
    });

    // A conversation tab opening before `room_state` arrives is a different
    // audience, not the same one being named — the room pose must not follow
    // it into the whisper composer.
    it('does not carry a provisional draft into a conversation tab that opens first', () => {
      seedDraft(
        { content: 'meant only for Bob', status: 'clean', clientRequestId: null },
        'whisper:9'
      );
      const { rerender } = render(
        <CommandInput
          character="Alice"
          draftScope="room:unknown"
          draftScopeSettling={{ provisional: true, conversation: 'room-anchor' }}
        />
      );
      const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'a pose for the whole room' } });

      rerender(
        <CommandInput
          character="Alice"
          draftScope="whisper:9"
          draftScopeSettling={{ conversation: 'whisper:9' }}
        />
      );

      expect(textarea.value).toBe('meant only for Bob');
      expect(storedDraft('whisper:9').content).toBe('meant only for Bob');
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

// #3787 Task 7 -- the reply chip's Narrator leak, wiring `reply_to` into
// `submitPose`, and the pre-emptive reachable-reply refusal (Screen 3).
function makeReplyTarget(overrides: Partial<Interaction> = {}): Interaction {
  return {
    id: 5,
    persona: { id: 1, name: 'Narrator' },
    content: "Kira's Frost Bolt strikes Corvin for 24 damage, leaving them Staggered.",
    mode: 'outcome',
    visibility: 'default',
    timestamp: '2026-01-01T00:00:05Z',
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
    ...overrides,
  };
}

describe('reply chip, reply_to wiring, and pre-emptive refusal (#3787)', () => {
  beforeEach(() => {
    submitPoseMock.mockClear();
    submitPoseMock.mockImplementation(() => Promise.resolve());
  });

  it('shows the excerpt alone for an outcome/action reply target -- never the Narrator bookkeeping author', () => {
    render(
      <CommandInput
        character="Alice"
        sceneId="5"
        personaId={9}
        replyTarget={makeReplyTarget({ mode: 'outcome' })}
      />
    );
    const context = screen.getByTestId('reply-context');
    expect(context).toHaveTextContent(
      "Kira's Frost Bolt strikes Corvin for 24 damage, leaving them Staggered."
    );
    expect(context).not.toHaveTextContent('Narrator');
  });

  it('still names the writer for an ordinary pose/say reply target', () => {
    render(
      <CommandInput
        character="Alice"
        sceneId="5"
        personaId={9}
        replyTarget={makeReplyTarget({ mode: 'pose', persona: { id: 2, name: 'Mirelle' } })}
      />
    );
    const context = screen.getByTestId('reply-context');
    expect(context).toHaveTextContent('Mirelle');
  });

  it('sends reply_to on the REST submit-pose call when replying, and clears the reply context on success', async () => {
    const onCancelReply = vi.fn();
    render(
      <CommandInput
        character="Alice"
        sceneId="5"
        personaId={9}
        replyTarget={makeReplyTarget({ mode: 'pose' })}
        onCancelReply={onCancelReply}
      />
    );
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'answers' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 5,
      content: 'answers',
      client_request_id: expect.any(String),
      reply_to: { id: 5, timestamp: '2026-01-01T00:00:05Z' },
    });
    await waitFor(() => expect(onCancelReply).toHaveBeenCalled());
  });

  it('omits reply_to entirely when there is no reply target (unchanged shape for an ordinary pose)', () => {
    render(<CommandInput character="Alice" sceneId="5" personaId={9} />);
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'looks around' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 5,
      content: 'looks around',
      client_request_id: expect.any(String),
    });
  });

  it('allows a reply to a room-held target while the viewer is at a Place (#3811 -- a Place declutters, it does not isolate)', () => {
    render(
      <CommandInput
        character="Alice"
        sceneId="5"
        personaId={9}
        replyTarget={makeReplyTarget({ mode: 'outcome', place: null })}
        isAtPlace
        currentPlaceId={7}
        currentPlaceName="the corner table"
      />
    );
    expect(screen.queryByTestId('reply-refusal')).not.toBeInTheDocument();

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'answers anyway' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });
    expect(submitPoseMock).toHaveBeenCalledWith({
      persona_id: 9,
      scene_id: 5,
      content: 'answers anyway',
      client_request_id: expect.any(String),
      reply_to: { id: 5, timestamp: '2026-01-01T00:00:05Z' },
    });
  });

  it('renders no refusal when the reply target is reachable', () => {
    render(
      <CommandInput
        character="Alice"
        sceneId="5"
        personaId={9}
        replyTarget={makeReplyTarget({ mode: 'outcome', place: null })}
        isAtPlace={false}
      />
    );
    expect(screen.queryByTestId('reply-refusal')).not.toBeInTheDocument();
  });
});

describe('tag reachability (#3810)', () => {
  it('shows the tag-refusal banner and disables Send when a mode switch carries a stale target', () => {
    // Vayne is physically in the room but not at the actor's own current
    // Place (place_id null vs. currentPlaceId 5) -- the same mismatch a
    // Tabletalk mode switch would carry forward from a stale whisper target.
    mockRoomCharacters = [{ name: 'Vayne', thumbnail_url: null, dbref: '#700', place_id: null }];
    const mode: ComposerMode = { command: 'tt', targets: ['Vayne'], label: 'Tabletalk' };
    render(<CommandInput character="Alice" composerMode={mode} isAtPlace currentPlaceId={5} />);

    const refusal = screen.getByTestId('tag-refusal');
    expect(refusal).toHaveTextContent('Vayne is across the room and will not see table talk.');
    expect(refusal).toHaveTextContent(
      'Address the room to reach them, or send a whisper. Your draft is kept.'
    );
    expect(refusal).toHaveAttribute('role', 'status');
    expect(refusal).toHaveAttribute('aria-live', 'polite');
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('does not show the tag-refusal banner when the target shares the current place', () => {
    mockRoomCharacters = [{ name: 'Vayne', thumbnail_url: null, dbref: '#700', place_id: 5 }];
    const mode: ComposerMode = { command: 'tt', targets: ['Vayne'], label: 'Tabletalk' };
    render(<CommandInput character="Alice" composerMode={mode} isAtPlace currentPlaceId={5} />);

    expect(screen.queryByTestId('tag-refusal')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });

  it('does not show the tag-refusal banner in whisper mode regardless of location', () => {
    mockRoomCharacters = [{ name: 'Vayne', thumbnail_url: null, dbref: '#700', place_id: null }];
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Vayne'],
      label: 'Whisper → Vayne',
    };
    render(<CommandInput character="Alice" composerMode={mode} isAtPlace currentPlaceId={5} />);

    expect(screen.queryByTestId('tag-refusal')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });

  // The three tests above all mount the component already in the refused or
  // reachable state via props -- they never prove the LIVE recompute this
  // feature's headline claim depends on. These two force a real rerender
  // after mount, without unmounting, so the useMemo actually has to fire on a
  // changed dependency rather than just render correctly given inputs it was
  // handed from the start.

  it('recomputes live on a mode switch that carries a stale target across, without unmounting', () => {
    // Vayne is physically in the room but not at the actor's current Place
    // (place_id null vs. currentPlaceId 5) -- the same mismatch a live
    // whisper-to-Tabletalk mode switch carries forward with no new
    // room_state push at all.
    mockRoomCharacters = [{ name: 'Vayne', thumbnail_url: null, dbref: '#700', place_id: null }];
    const whisperMode: ComposerMode = {
      command: 'whisper',
      targets: ['Vayne'],
      label: 'Whisper → Vayne',
    };
    const { rerender } = render(
      <CommandInput character="Alice" composerMode={whisperMode} isAtPlace currentPlaceId={5} />
    );

    expect(screen.queryByTestId('tag-refusal')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();

    const ttMode: ComposerMode = { command: 'tt', targets: ['Vayne'], label: 'Tabletalk' };
    rerender(<CommandInput character="Alice" composerMode={ttMode} isAtPlace currentPlaceId={5} />);

    expect(screen.getByTestId('tag-refusal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('recomputes live when a fresh room_state push moves an already-tagged target to a different place, with composerMode unchanged', () => {
    mockRoomCharacters = [{ name: 'Vayne', thumbnail_url: null, dbref: '#700', place_id: 5 }];
    const mode: ComposerMode = { command: 'tt', targets: ['Vayne'], label: 'Tabletalk' };
    const { rerender } = render(
      <CommandInput character="Alice" composerMode={mode} isAtPlace currentPlaceId={5} />
    );

    expect(screen.queryByTestId('tag-refusal')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();

    // A fresh room_state push moves Vayne to a different place -- composerMode
    // itself never changes, only the room roster the selector returns.
    mockRoomCharacters = [{ name: 'Vayne', thumbnail_url: null, dbref: '#700', place_id: 9 }];
    rerender(<CommandInput character="Alice" composerMode={mode} isAtPlace currentPlaceId={5} />);

    expect(screen.getByTestId('tag-refusal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('recomputes live when the actor moves to a different place, with the target and composerMode unchanged', () => {
    // Vayne stays put at place 5 the whole time. This is the symmetric case
    // to the test above: there it was the TARGET's place_id that moved out
    // from under a fixed currentPlaceId, here it is the actor's own
    // currentPlaceId that moves out from under a fixed target place_id. Both
    // go through the same `character.place_id !== venue.currentPlaceId`
    // check in tagReachability.ts, so both must recompute live the same way.
    mockRoomCharacters = [{ name: 'Vayne', thumbnail_url: null, dbref: '#700', place_id: 5 }];
    const mode: ComposerMode = { command: 'tt', targets: ['Vayne'], label: 'Tabletalk' };
    const { rerender } = render(
      <CommandInput character="Alice" composerMode={mode} isAtPlace currentPlaceId={5} />
    );

    expect(screen.queryByTestId('tag-refusal')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();

    // The actor moves to a different table. Vayne's own place_id never
    // changes, and neither does composerMode.
    rerender(<CommandInput character="Alice" composerMode={mode} isAtPlace currentPlaceId={9} />);

    expect(screen.getByTestId('tag-refusal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });
});
