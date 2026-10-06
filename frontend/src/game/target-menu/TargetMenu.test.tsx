import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useEffect, useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { useDispatchPlayerAction } from '@/combat/queries';
import { store } from '@/store/store';
import { startSession, setActiveSession } from '@/store/gameSlice';
import { setAccount } from '@/store/authSlice';
import { fetchTargetMenu } from './targetMenuApi';
import { TargetMenu } from './TargetMenu';

vi.mock('@/combat/queries', () => ({ useDispatchPlayerAction: vi.fn() }));
vi.mock('./targetMenuApi', async () => {
  const actual = await vi.importActual<typeof import('./targetMenuApi')>('./targetMenuApi');
  return { ...actual, fetchTargetMenu: vi.fn() };
});

const mockDispatch = vi.mocked(useDispatchPlayerAction);
const mockFetch = vi.mocked(fetchTargetMenu);

const authoredRef = {
  backend: 'world_interaction',
  challenge_instance_id: null,
  approach_id: null,
  technique_id: null,
  registry_key: null,
  application_id: 99,
  target_object_id: 100,
};
const authoredAction = {
  backend: 'world_interaction',
  display_name: 'Ignite',
  description: 'An authored action.',
  difficulty: 'moderate',
  prerequisite_met: true,
  prerequisite_reasons: [],
  check_type: { id: 1, name: 'Mysticism' },
  action_template: null,
  ref: authoredRef,
  target_spec: null,
  enhancements: [],
  strain: null,
};

const menu = {
  actor_id: 7,
  target: { kind: 'objects' as const, target_id: 100 },
  label: 'wooden chest',
  groups: [
    { key: 'perception', label: 'Perception' },
    { key: 'items', label: 'Items' },
  ],
  entries: [
    {
      key: 'look',
      label: 'Look',
      group: 'perception',
      ref: { backend: 'registry', registry_key: 'look' },
      kwargs: { menu_target: { kind: 'objects', target_id: 100 } },
      available: true,
      reasons: [],
      inputs: [],
      candidates: [],
      action: null,
      risk: null,
    },
    {
      key: 'get',
      label: 'Get',
      group: 'items',
      ref: { backend: 'registry', registry_key: 'get' },
      kwargs: {},
      available: false,
      reasons: ['It is too heavy.'],
      inputs: [],
      candidates: [],
      action: null,
      risk: null,
    },
  ],
};

const choiceMenu = {
  ...menu,
  entries: [
    {
      ...menu.entries[0],
      key: 'give',
      label: 'Give',
      group: 'items',
      inputs: [
        {
          name: 'recipient_persona_id',
          kind: 'recipient',
          required: true,
          target_kind: null,
          default: null,
        },
      ],
      candidates: [
        {
          key: '22',
          label: 'Visible recipient',
          kwargs: { recipient_persona_id: 22 },
          available: true,
          reasons: [],
        },
      ],
      action: null,
    },
  ],
};

describe('TargetMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    store.dispatch(
      setAccount({
        id: 1,
        username: 'test',
        display_name: 'Test',
        last_login: null,
        email: '',
        email_verified: true,
        can_create_characters: false,
        character_slots: { total: 1, used: 0, activity_total: 0, activity_used: 0, holders: [] },
        is_staff: false,
        is_gm: false,
        available_characters: [
          {
            id: 7,
            name: 'Current',
            portrait_url: null,
            character_type: 'PC',
            roster_status: 'Active',
            personas: [],
            last_location: null,
            currently_puppeted_in_session: false,
          },
          {
            id: 8,
            name: 'Other',
            portrait_url: null,
            character_type: 'PC',
            roster_status: 'Active',
            personas: [],
            last_location: null,
            currently_puppeted_in_session: false,
          },
        ],
        pending_applications: [],
        selected_entry_id: 1,
        selected_entry: null,
      })
    );
    store.dispatch(startSession('Current'));
    store.dispatch(setActiveSession('Current'));
    mockFetch.mockResolvedValue(menu);
    mockDispatch.mockReturnValue({
      mutateAsync: vi
        .fn()
        .mockResolvedValue({ success: true, deferred: false, message: 'You look.' }),
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  });

  it('refuses a chooser submission after the active actor changes', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ success: true, deferred: false });
    mockDispatch.mockReturnValue({ mutateAsync, isPending: false } as unknown as ReturnType<
      typeof useDispatchPlayerAction
    >);
    mockFetch.mockResolvedValue(choiceMenu);
    renderWithProviders(
      <TargetMenu partition="account-1" actorId={7} target={menu.target}>
        <button>wooden chest</button>
      </TargetMenu>
    );

    fireEvent.contextMenu(screen.getByRole('button', { name: 'wooden chest' }), {
      button: 2,
      clientX: 20,
      clientY: 20,
    });
    await user.click(await screen.findByRole('menuitem', { name: 'Give…' }));
    expect(await screen.findByRole('dialog', { name: 'Give item' })).toBeInTheDocument();

    act(() => {
      store.dispatch(startSession('Other'));
      store.dispatch(setActiveSession('Other'));
    });
    await user.click(screen.getByRole('button', { name: 'Give' }));
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('shows authored outcome risk before dispatch and allows cancellation without a write', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ success: true, deferred: false });
    mockDispatch.mockReturnValue({ mutateAsync, isPending: false } as unknown as ReturnType<
      typeof useDispatchPlayerAction
    >);
    mockFetch.mockResolvedValue({
      ...menu,
      groups: [{ key: 'authored', label: 'Authored actions' }],
      entries: [
        {
          ...menu.entries[0],
          key: 'authored:1',
          label: 'Ignite',
          group: 'authored',
          ref: authoredRef,
          kwargs: {},
          action: authoredAction,
          risk: {
            known: true,
            character_loss_possible: true,
            outcomes: [{ stage: 'main', tier: 'DEADLY', character_loss: true }],
          },
        },
      ],
    });
    renderWithProviders(
      <TargetMenu partition="account-1" actorId={7} target={menu.target}>
        <button>wooden chest</button>
      </TargetMenu>
    );

    fireEvent.contextMenu(screen.getByRole('button', { name: 'wooden chest' }), {
      button: 2,
      clientX: 20,
      clientY: 20,
    });
    expect(await screen.findByRole('menuitem', { name: 'Ignite' })).toBeInTheDocument();
    expect(screen.queryByText('Authored actions')).not.toBeInTheDocument();
    expect(screen.queryByText('Perception')).not.toBeInTheDocument();
    expect(screen.queryByText('Item handling')).not.toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'Ignite' }));
    expect(await screen.findByText('Character loss is possible.')).toBeInTheDocument();
    expect(screen.getByText('main: deadly (character loss)')).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('requires risk review before selecting inputs for an authored action', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ success: true, deferred: false });
    mockDispatch.mockReturnValue({ mutateAsync, isPending: false } as unknown as ReturnType<
      typeof useDispatchPlayerAction
    >);
    const authoredEntry = {
      ...menu.entries[0],
      key: 'authored:use',
      label: 'Use the charm',
      group: 'authored',
      ref: authoredRef,
      kwargs: {},
      action: authoredAction,
      inputs: [
        { name: 'option_id', kind: 'option', required: true, target_kind: null, default: null },
      ],
      risk: {
        known: true,
        character_loss_possible: false,
        outcomes: [{ stage: 'main', tier: 'MINOR', character_loss: false }],
      },
    };
    mockFetch.mockResolvedValue({
      ...menu,
      groups: [{ key: 'authored', label: 'Authored actions' }],
      entries: [authoredEntry],
    });
    renderWithProviders(
      <TargetMenu partition="account-1" actorId={7} target={menu.target}>
        <button>wooden chest</button>
      </TargetMenu>
    );

    fireEvent.contextMenu(screen.getByRole('button', { name: 'wooden chest' }), {
      button: 2,
      clientX: 20,
      clientY: 20,
    });
    await user.click(await screen.findByRole('menuitem', { name: 'Use the charm…' }));
    expect(await screen.findByText('An authored action.')).toBeInTheDocument();
    expect(screen.getByText('Difficulty:')).toBeInTheDocument();
    expect(screen.getByText('moderate')).toBeInTheDocument();
    expect(await screen.findByText('No character-loss outcome is listed.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm action' })).toBeEnabled();
    expect(mutateAsync).not.toHaveBeenCalled();

    const choiceRefresh = {
      ...menu,
      entries: [
        {
          ...authoredEntry,
          candidates: [
            {
              key: '22',
              label: 'Known option',
              kwargs: { option_id: 22 },
              available: true,
              reasons: [],
            },
          ],
        },
      ],
    };
    mockFetch.mockResolvedValueOnce(choiceRefresh);
    await user.click(screen.getByRole('button', { name: 'Confirm action' }));
    expect(await screen.findByRole('dialog', { name: 'Use the charm' })).toBeInTheDocument();
    expect(await screen.findByRole('radio', { name: 'Known option' })).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('closes authored confirmation when the target identity changes', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ success: true, deferred: false });
    mockDispatch.mockReturnValue({ mutateAsync, isPending: false } as unknown as ReturnType<
      typeof useDispatchPlayerAction
    >);
    mockFetch.mockResolvedValue({
      ...menu,
      groups: [{ key: 'authored', label: 'Authored actions' }],
      entries: [
        {
          ...menu.entries[0],
          key: 'authored:1',
          label: 'Ignite',
          group: 'authored',
          ref: authoredRef,
          kwargs: {},
          action: authoredAction,
          risk: { known: false, character_loss_possible: null, outcomes: [] },
        },
      ],
    });
    function ChangingAuthoredTarget() {
      const [targetId, setTargetId] = useState(100);
      useEffect(() => {
        (window as Window & { changeAuthoredTarget?: () => void }).changeAuthoredTarget = () =>
          setTargetId(101);
        return () => {
          delete (window as Window & { changeAuthoredTarget?: () => void }).changeAuthoredTarget;
        };
      }, []);
      return (
        <TargetMenu
          partition="account-1"
          actorId={7}
          target={{ kind: 'objects', target_id: targetId }}
        >
          <button>wooden chest</button>
        </TargetMenu>
      );
    }
    renderWithProviders(<ChangingAuthoredTarget />);

    fireEvent.contextMenu(screen.getByRole('button', { name: 'wooden chest' }), {
      button: 2,
      clientX: 20,
      clientY: 20,
    });
    await user.click(await screen.findByRole('menuitem', { name: 'Ignite' }));
    expect(await screen.findByRole('dialog', { name: 'Ignite' })).toBeInTheDocument();
    act(() => (window as Window & { changeAuthoredTarget?: () => void }).changeAuthoredTarget?.());
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Ignite' })).not.toBeInTheDocument()
    );
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('refuses a chooser submission after the target identity changes', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ success: true, deferred: false });
    mockDispatch.mockReturnValue({ mutateAsync, isPending: false } as unknown as ReturnType<
      typeof useDispatchPlayerAction
    >);
    mockFetch.mockResolvedValue(choiceMenu);
    function ChangingTarget() {
      const [targetId, setTargetId] = useState(100);
      useEffect(() => {
        (window as Window & { changeTarget?: () => void }).changeTarget = () => setTargetId(101);
        return () => {
          delete (window as Window & { changeTarget?: () => void }).changeTarget;
        };
      }, []);
      return (
        <TargetMenu
          partition="account-1"
          actorId={7}
          target={{ kind: 'objects', target_id: targetId }}
        >
          <button>wooden chest</button>
        </TargetMenu>
      );
    }
    renderWithProviders(<ChangingTarget />);

    fireEvent.contextMenu(screen.getByRole('button', { name: 'wooden chest' }), {
      button: 2,
      clientX: 20,
      clientY: 20,
    });
    await user.click(await screen.findByRole('menuitem', { name: 'Give…' }));
    expect(await screen.findByRole('dialog', { name: 'Give item' })).toBeInTheDocument();
    act(() => (window as Window & { changeTarget?: () => void }).changeTarget?.());
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Give item' })).not.toBeInTheDocument()
    );
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('refuses an immediate action when the active actor changes while the menu is open', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn().mockResolvedValue({ success: true, deferred: false });
    mockDispatch.mockReturnValue({ mutateAsync, isPending: false } as unknown as ReturnType<
      typeof useDispatchPlayerAction
    >);
    mockFetch.mockResolvedValue(menu);
    renderWithProviders(
      <TargetMenu partition="account-1" actorId={7} target={menu.target}>
        <button>wooden chest</button>
      </TargetMenu>
    );

    fireEvent.contextMenu(screen.getByRole('button', { name: 'wooden chest' }), {
      button: 2,
      clientX: 20,
      clientY: 20,
    });
    await expect(screen.findByRole('menuitem', { name: 'Look' })).resolves.toBeVisible();
    act(() => {
      store.dispatch(startSession('Other'));
      store.dispatch(setActiveSession('Other'));
    });
    await user.click(screen.getByRole('menuitem', { name: 'Look' }));
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('fetches on right-click, shows backend groups and blockers, and leaves left-click to the child', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderWithProviders(
      <TargetMenu partition="account-1" actorId={7} target={menu.target}>
        <button onClick={onClick}>wooden chest</button>
      </TargetMenu>
    );

    fireEvent.contextMenu(screen.getByRole('button', { name: 'wooden chest' }), {
      button: 2,
      clientX: 20,
      clientY: 20,
    });
    expect(await screen.findByText('Look')).toBeInTheDocument();
    expect(screen.getByTestId('target-menu-label')).toHaveTextContent('wooden chest');
    expect(screen.getByText('It is too heavy.')).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(onClick).not.toHaveBeenCalled();

    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'wooden chest' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
