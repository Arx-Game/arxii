import React from 'react';
import { render as rtlRender, screen, fireEvent } from '@testing-library/react';
import type { RenderOptions } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CommandInput } from './CommandInput';
import type { ComposerMode } from './CommandInput';

// Wrap every render call in a QueryClientProvider so useQuery hooks work in tests.
const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

function render(ui: React.ReactElement, options?: RenderOptions) {
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return rtlRender(ui, { wrapper: Wrapper, ...options });
}

const sendMock = vi.fn();
const submitPoseMock = vi.fn(() => Promise.resolve());
const fetchSceneMock = vi.fn();

vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({ send: sendMock }),
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

describe('CommandInput', () => {
  beforeEach(() => {
    sendMock.mockClear();
    submitPoseMock.mockClear();
    fetchSceneMock.mockClear();
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

  it('pose without detachments uses WebSocket send and skips REST submitPose', () => {
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

    expect(sendMock).toHaveBeenCalledWith('Alice', 'pose stands ready');
    expect(submitPoseMock).not.toHaveBeenCalled();
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
