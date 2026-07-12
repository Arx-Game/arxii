import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import type { RenderOptions } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';

// Wrap every render call in a QueryClientProvider so useQuery hooks work in tests.
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function render(ui: ReactElement, options?: RenderOptions) {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return rtlRender(ui, { wrapper: Wrapper, ...options });
}

const sendMock = vi.fn();
// Loosely typed: submitPose resolves with the created interaction payload
// (#2183 reads `id` off it) or undefined in older tests.
const submitPoseMock = vi.fn((): Promise<unknown> => Promise.resolve());
const fetchSceneMock = vi.fn();
const toastErrorMock = vi.fn();

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({ send: sendMock }),
}));

vi.mock('sonner', () => ({
  toast: { error: (...args: unknown[]) => toastErrorMock(...args), success: vi.fn() },
}));

vi.mock('@/scenes/queries', () => ({
  submitPose: (...args: unknown[]) => submitPoseMock(...(args as [])),
  fetchScene: (...args: unknown[]) => fetchSceneMock(...(args as [])),
  sceneKeys: {
    detail: (id: string) => ['scene', String(id)] as const,
  },
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: (selector: (state: unknown) => unknown) =>
    selector({
      game: {
        active: 'Alice',
        sessions: {
          Alice: {
            room: { characters: [{ name: 'Bob', thumbnail_url: null }] },
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
    submitPoseMock.mockClear();
    submitPoseMock.mockImplementation(() => Promise.resolve());
    fetchSceneMock.mockClear();
    toastErrorMock.mockClear();
    createActionRequestMock.mockClear();
    createActionRequestMock.mockImplementation(() => Promise.resolve({ status: 'resolved' }));
    queryClient.clear();
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

  it('whisper mode uses target=text syntax', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Bob'],
      label: 'Whisper \u2192 Bob',
    };
    render(<CommandInput character="Alice" composerMode={mode} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'secret message' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'whisper Bob=secret message');
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

  it('whisper composer mode with sceneId still uses WebSocket send (non-pose commands keep WS)', () => {
    const mode: ComposerMode = {
      command: 'whisper',
      targets: ['Bob'],
      label: 'Whisper → Bob',
    };
    render(<CommandInput character="Alice" composerMode={mode} sceneId="5" personaId={9} />);
    const textarea = screen.getByRole('textbox');

    fireEvent.change(textarea, { target: { value: 'secret message' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    expect(sendMock).toHaveBeenCalledWith('Alice', 'whisper Bob=secret message');
    expect(submitPoseMock).not.toHaveBeenCalled();
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
