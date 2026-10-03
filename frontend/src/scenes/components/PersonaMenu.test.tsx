import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PersonaMenuData, PersonaMenuItemData } from '@/game/persona-menu/personaMenuApi';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockUsePersonaMenuQuery = vi.fn();
vi.mock('@/game/persona-menu/personaMenuApi', () => ({
  usePersonaMenuQuery: (...args: unknown[]) => mockUsePersonaMenuQuery(...args),
}));

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: null,
        active_persona_id: null,
      },
    ],
  })),
}));

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'TestChar' }, auth: {} })
  ),
}));

vi.mock('@/combat/queries', async () => {
  const actual = await vi.importActual<typeof import('@/combat/queries')>('@/combat/queries');
  return {
    ...actual,
    useDispatchPlayerAction: vi.fn(() => ({
      mutateAsync: vi.fn(() => Promise.resolve({ backend: 'registry', deferred: false })),
      isPending: false,
    })),
  };
});

vi.mock('@/social/queries', () => ({
  useCreateMute: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCreateBlock: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('../actionQueries', () => ({
  createActionRequest: vi.fn(() => Promise.resolve({ status: 'resolved' })),
}));

import { PersonaMenu } from './PersonaMenu';
import { useDispatchPlayerAction, combatKeys } from '@/combat/queries';
import { useCreateMute, useCreateBlock } from '@/social/queries';
import { createActionRequest } from '../actionQueries';
import { toast } from 'sonner';
import { PersonaCardContext } from '@/game/persona-menu/PersonaCardContext';

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

const SCENE_EMPTY = 'Nothing to do here right now.';

const GROUP_KEYS = ['perception', 'conflict', 'scene', 'social'] as const;

const ITEM_GROUPS: Record<string, (typeof GROUP_KEYS)[number]> = {
  look: 'perception',
  identify: 'perception',
  challenge: 'conflict',
  scene_succor: 'scene',
  scene_interpose: 'scene',
  send_away: 'scene',
  charm_asset: 'scene',
  treat: 'scene',
  give_mission: 'scene',
  mute: 'social',
  block: 'social',
};

const ITEM_LABELS: Record<string, string> = {
  look: 'Look',
  identify: 'Identify',
  challenge: 'Challenge to a duel',
  scene_succor: 'Succor',
  scene_interpose: 'Interpose',
  send_away: 'Send away',
  charm_asset: 'Take into service',
  treat: 'Treat',
  give_mission: 'Give mission',
  mute: 'Mute',
  block: 'Block',
};

/** A single scene_action fixture (server PlayerAction shape) shared by the
 * delivery-submenu / Attach-to-Pose / unmet-prerequisite tests below. */
const BASE_INTIMIDATE_ACTION = {
  backend: 'template',
  display_name: 'Intimidate',
  description: '',
  difficulty: null,
  prerequisite_met: true,
  prerequisite_reasons: [],
  check_type: { id: 1, name: 'Standard' },
  action_template: { id: 1, name: 'Intimidate', default_delivery: 'pose' },
  ref: {
    backend: 'template',
    challenge_instance_id: null,
    approach_id: null,
    technique_id: null,
    registry_key: null,
  },
  target_spec: null,
  enhancements: [],
  strain: null,
};

function item(key: string, overrides: Partial<PersonaMenuItemData> = {}): PersonaMenuItemData {
  return {
    key,
    label: ITEM_LABELS[key] ?? key,
    group: ITEM_GROUPS[key],
    available: true,
    reason: '',
    ...overrides,
  };
}

function groups(
  overrides: Partial<Record<(typeof GROUP_KEYS)[number], string>> = {}
): PersonaMenuData['groups'] {
  return GROUP_KEYS.map((key) => ({ key, empty_state: overrides[key] ?? '' }));
}

function menuFixture(overrides: Partial<PersonaMenuData> = {}): PersonaMenuData {
  return {
    persona_id: 10,
    is_self: false,
    scene_id: 1,
    viewer_persona_id: 5,
    notice: '',
    items: [item('look')],
    groups: groups(),
    scene_actions: [],
    ...overrides,
  };
}

function mockMenu(
  overrides: Partial<PersonaMenuData> = {},
  queryOverrides: Record<string, unknown> = {}
) {
  mockUsePersonaMenuQuery.mockReturnValue({
    data: menuFixture(overrides),
    isLoading: false,
    ...queryOverrides,
  });
}

function renderMenu(
  props: Partial<{
    personaId: number;
    personaName: string;
    thumbnailUrl: string | null;
    leftClick: boolean;
    onAttachAction: (a: unknown) => void;
  }> = {},
  cardContext: { openCharacterCard: (p: unknown) => void } | null = null,
  existingQueryClient?: QueryClient
) {
  const queryClient =
    existingQueryClient ??
    new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <PersonaCardContext.Provider value={cardContext}>
      <QueryClientProvider client={queryClient}>
        <PersonaMenu
          personaId={props.personaId ?? 10}
          personaName={props.personaName ?? 'Cassia Vell'}
          thumbnailUrl={props.thumbnailUrl}
          leftClick={props.leftClick}
          onAttachAction={props.onAttachAction as never}
        >
          <span>{props.personaName ?? 'Cassia Vell'}</span>
        </PersonaMenu>
      </QueryClientProvider>
    </PersonaCardContext.Provider>
  );
  return queryClient;
}

/**
 * Opens the scene_actions delivery submenu for a single "Intimidate" action
 * (#903). Radix submenu interaction is keyboard-driven in jsdom (hover
 * grace-area math needs real pointer coordinates): ArrowDown three times
 * reaches the SubTrigger (past Look, View sheet), ArrowRight opens it with
 * "Default" focused. `sceneActionOverrides` lets a caller mutate the single
 * scene_action fixture (e.g. `prerequisite_met: false`).
 */
async function openIntimidateSubmenu(sceneActionOverrides: Record<string, unknown> = {}) {
  const user = userEvent.setup();
  mockMenu({
    scene_id: 7,
    items: [item('look')],
    scene_actions: [
      { ...BASE_INTIMIDATE_ACTION, ...sceneActionOverrides },
    ] as unknown as PersonaMenuData['scene_actions'],
  });
  const queryClient = renderMenu({ personaId: 10 });
  fireEvent.contextMenu(screen.getByText('Cassia Vell'));
  await screen.findByRole('menu');
  await user.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}{ArrowRight}');
  await screen.findByText(/^Default/);
  return { user, queryClient };
}

describe('PersonaMenu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMenu();
  });

  it('opens on right-click with Look and View sheet first, then the server items', async () => {
    mockMenu({
      items: [
        item('look'),
        item('identify', {
          available: false,
          reason: 'Their face is their own; there is no mask to see through.',
        }),
        item('challenge'),
        item('mute'),
        item('block'),
      ],
      groups: groups({ scene: SCENE_EMPTY }),
    });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    const labels = within(menu)
      .getAllByRole('menuitem')
      .map((el) => el.textContent);
    expect(labels.slice(0, 2)).toEqual(['Look', 'View sheet']);
    expect(within(menu).getByRole('menuitem', { name: /Identify/ })).toHaveAttribute(
      'aria-disabled',
      'true'
    );
    expect(within(menu).getByText(/no mask to see through/)).toBeInTheDocument();
    expect(within(menu).getByText(SCENE_EMPTY)).toBeInTheDocument();
  });

  it("renders every group's empty_state as a trailing footer after ALL groups, not inline mid-menu", async () => {
    mockMenu({
      items: [item('look'), item('challenge')],
      groups: groups({ scene: SCENE_EMPTY, social: 'No one to socialize with.' }),
      notice: 'Closing notice line.',
    });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    const menuText = menu.textContent ?? '';
    const challengeIdx = menuText.indexOf('Challenge to a duel');
    const sceneEmptyIdx = menuText.indexOf(SCENE_EMPTY);
    const socialEmptyIdx = menuText.indexOf('No one to socialize with.');
    const noticeIdx = menuText.indexOf('Closing notice line.');
    // Both empty_state lines land after the last real item, in server group
    // order, and before the closing notice — never sandwiched between two
    // groups' own items the way an inline per-group render would place them.
    expect(challengeIdx).toBeGreaterThan(-1);
    expect(sceneEmptyIdx).toBeGreaterThan(challengeIdx);
    expect(socialEmptyIdx).toBeGreaterThan(sceneEmptyIdx);
    expect(noticeIdx).toBeGreaterThan(socialEmptyIdx);
  });

  it('renders with no scene: no sceneId prop exists and nothing reads the scene cache', async () => {
    mockMenu({ scene_id: null, items: [item('look')], groups: groups() });
    const queryClient = renderMenu();
    const spy = vi.spyOn(queryClient, 'getQueryData');
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    await screen.findByRole('menu');
    expect(spy).not.toHaveBeenCalledWith(expect.arrayContaining(['scene']));
  });

  it('opens from a left-click on the name only when leftClick is set', async () => {
    const user = userEvent.setup();
    renderMenu({ leftClick: true });
    await user.click(screen.getByRole('button', { name: 'Cassia Vell' }));
    expect(await screen.findByRole('menu')).toBeInTheDocument();
  });

  it('does not open on left-click when leftClick is not set', async () => {
    const user = userEvent.setup();
    renderMenu();
    expect(screen.queryByRole('button', { name: 'Cassia Vell' })).not.toBeInTheDocument();
    await user.click(screen.getByText('Cassia Vell'));
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('Look dispatches the look action with target_persona_id and shows the dialog', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        success: true,
        message: 'A tall woman.',
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    mockMenu({ items: [item('look')] });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Look' }));

    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'look' },
      kwargs: { target_persona_id: 10 },
    });
    await waitFor(() => {
      expect(screen.getByText('A tall woman.')).toBeInTheDocument();
    });
  });

  it("toasts the server's refusal and closes the dialog when Look fails", async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: false, message: null })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    mockMenu({ items: [item('look')] });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Look' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("You can't see them from here.");
    });
  });

  it('View sheet calls openCharacterCard from context', async () => {
    const user = userEvent.setup();
    const openCharacterCard = vi.fn();
    mockMenu();
    renderMenu({ personaId: 10, thumbnailUrl: 'https://example.com/a.png' }, { openCharacterCard });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'View sheet' }));

    expect(openCharacterCard).toHaveBeenCalledWith({
      id: 10,
      name: 'Cassia Vell',
      thumbnail_url: 'https://example.com/a.png',
    });
  });

  it('Succor and Interpose dispatch target_persona_id, not ally_name', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: true, message: 'ok' })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    mockMenu({ items: [item('look'), item('scene_succor'), item('scene_interpose')] });
    renderMenu({ personaId: 10 });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    let menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Succor' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'scene_succor' },
      kwargs: { target_persona_id: 10 },
    });

    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Interpose' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'scene_interpose' },
      kwargs: { target_persona_id: 10 },
    });
  });

  // #4091 task 12 wired send_away/charm_asset into the menu's items list but
  // left no handlerFor case, so clicking either did nothing (found while
  // adding their ITEM_ICONS entries, task 14's own brief; fixed in the same
  // PR per CLAUDE.md's Fold In, Don't File).
  it('Send away and Take into service dispatch target_persona_id (and role_context), and invalidate the persona menu + combat caches', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: true, message: 'ok' })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    mockMenu({ items: [item('look'), item('send_away'), item('charm_asset')] });
    const queryClient = renderMenu({ personaId: 10 });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    let menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Send away' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'send_away' },
      kwargs: { target_persona_id: 10 },
    });
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['persona-menu'] });
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: combatKeys.all });
    });

    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Take into service' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'charm_asset' },
      kwargs: { target_persona_id: 10, role_context: 'contact' },
    });
  });

  it('shows a failure toast instead of swallowing an HTTP-level send_away error', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn(() => Promise.reject(new Error('Failed to dispatch action')));
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    mockMenu({ items: [item('look'), item('send_away')] });
    renderMenu({ personaId: 10 });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Send away' }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to dispatch action');
    });
  });

  it('dispatches the challenge action with the target persona id and invalidates duel challenges', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn(() =>
      Promise.resolve({ backend: 'registry', deferred: false, success: true })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    mockMenu({ items: [item('look'), item('challenge')] });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: /Challenge/ }));

    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'challenge' },
      kwargs: { target: 10 },
    });
    expect(combatKeys.duelChallengesAll()).toEqual(['combat', 'duel-challenges']);
  });

  it('dispatches identify with the target kwarg and toasts the outcome message', async () => {
    const user = userEvent.setup();
    const mutateAsync = vi.fn(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        success: true,
        message: 'You recognize her.',
      })
    );
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutateAsync,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    mockMenu({ items: [item('look'), item('identify')] });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Identify' }));

    expect(mutateAsync).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'identify' },
      kwargs: { target: 10 },
    });
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('You recognize her.');
    });
  });

  it('mutes via createMute with the account-first default payload', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    vi.mocked(useCreateMute).mockReturnValue({ mutate, isPending: false } as unknown as ReturnType<
      typeof useCreateMute
    >);
    mockMenu({ items: [item('look'), item('mute')] });
    renderMenu({ personaId: 10 });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Mute' }));

    expect(mutate).toHaveBeenCalledWith({
      muted_persona: 10,
      mute_ic: true,
      mute_ooc: true,
      account_level: true,
    });
  });

  it('block submits with blocker_persona from the server viewer_persona_id', async () => {
    const user = userEvent.setup();
    const mutate = vi.fn((_data, opts?: { onSettled?: () => void }) => opts?.onSettled?.());
    vi.mocked(useCreateBlock).mockReturnValue({ mutate, isPending: false } as unknown as ReturnType<
      typeof useCreateBlock
    >);
    mockMenu({ items: [item('look'), item('block')], viewer_persona_id: 7 });
    renderMenu({ personaId: 10 });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Block' }));

    await user.type(screen.getByTestId('block-reason-input'), 'Harassment');
    await user.click(screen.getByTestId('confirm-block-button'));

    expect(mutate).toHaveBeenCalledWith(
      {
        blocker_persona: 7,
        blocked_persona: 10,
        reason: 'Harassment',
        account_level: true,
      },
      expect.anything()
    );
  });

  it('treat opens the Treat panel for the target', async () => {
    const user = userEvent.setup();
    mockMenu({ items: [item('look'), item('treat')] });
    renderMenu({ personaId: 10 });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Treat' }));

    expect(await screen.findByText(/Offer treatment to Cassia Vell/)).toBeInTheDocument();
  });

  it('give mission opens the GiveMissionDialog', async () => {
    const user = userEvent.setup();
    mockMenu({ items: [item('look'), item('give_mission')] });
    renderMenu({ personaId: 10 });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    await user.click(within(menu).getByRole('menuitem', { name: 'Give mission' }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
  });

  it('self menu shows the notice, the "how others see you" Look hint, and no action groups', async () => {
    mockMenu({
      is_self: true,
      notice: 'This is your own face.',
      items: [item('look')],
      groups: [{ key: 'perception', empty_state: '' }],
    });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByText('This is your own face.')).toBeInTheDocument();
    expect(within(menu).getByText('how others see you')).toBeInTheDocument();
    // Demo Screen 1b: the popup menu's own header reads "<name> (you)".
    expect(within(menu).getByText('Cassia Vell (you)')).toBeInTheDocument();
    const labels = within(menu)
      .getAllByRole('menuitem')
      .map((el) => el.textContent);
    expect(labels).toEqual(['Lookhow others see you', 'View sheet']);
  });

  it('does not show the "how others see you" hint or the "(you)" header suffix on a non-self menu', async () => {
    mockMenu({ is_self: false, items: [item('look')] });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).queryByText('how others see you')).not.toBeInTheDocument();
    expect(within(menu).queryByText('Cassia Vell (you)')).not.toBeInTheDocument();
    expect(within(menu).getByText('Cassia Vell')).toBeInTheDocument();
  });

  it('shows a muted loading line while the menu data is loading', async () => {
    mockMenu({}, { isLoading: true, data: undefined });
    renderMenu();
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByText('Loading…')).toBeInTheDocument();
  });

  it('scene_actions render as the existing delivery submenus and fire createActionRequest(scene_id, ...)', async () => {
    const user = userEvent.setup();
    mockMenu({
      scene_id: 7,
      items: [item('look')],
      scene_actions: [
        {
          backend: 'template',
          display_name: 'Intimidate',
          description: '',
          difficulty: null,
          prerequisite_met: true,
          prerequisite_reasons: [],
          check_type: { id: 1, name: 'Standard' },
          action_template: { id: 1, name: 'Intimidate', default_delivery: 'pose' },
          ref: {
            backend: 'template',
            challenge_instance_id: null,
            approach_id: null,
            technique_id: null,
            registry_key: null,
          },
          target_spec: null,
          enhancements: [],
          strain: null,
        },
      ] as unknown as PersonaMenuData['scene_actions'],
    });
    renderMenu({ personaId: 10 });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    await screen.findByRole('menu');
    await user.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}{ArrowRight}');
    await user.click(await screen.findByText(/^Default/));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '7',
        expect.objectContaining({ action_key: 'intimidate', target_persona_id: 10 })
      );
    });
  });

  it('renders "Attach to Pose" from scene_actions and calls onAttachAction', async () => {
    const user = userEvent.setup();
    const onAttachAction = vi.fn();
    mockMenu({
      scene_id: 7,
      items: [item('look')],
      scene_actions: [
        {
          backend: 'template',
          display_name: 'Intimidate',
          description: '',
          difficulty: null,
          prerequisite_met: true,
          prerequisite_reasons: [],
          check_type: { id: 1, name: 'Standard' },
          action_template: { id: 1, name: 'Intimidate', default_delivery: 'pose' },
          ref: {
            backend: 'template',
            challenge_instance_id: null,
            approach_id: null,
            technique_id: null,
            registry_key: null,
          },
          target_spec: null,
          enhancements: [],
          strain: null,
        },
      ] as unknown as PersonaMenuData['scene_actions'],
    });
    renderMenu({ personaId: 10, onAttachAction });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByText('Attach to Pose')).toBeInTheDocument();
    const attachItems = within(menu).getAllByText('Intimidate');
    await user.click(attachItems[attachItems.length - 1]);

    expect(onAttachAction).toHaveBeenCalledWith(
      expect.objectContaining({
        actionKey: 'intimidate',
        name: 'Intimidate',
        target: 'Cassia Vell',
        requiresTarget: true,
        targetPersonaId: 10,
      })
    );
  });

  // ---------------------------------------------------------------------------
  // Delivery submenu options (#903) — ported from the pre-#4030
  // PersonaContextMenu suite onto the server-composed scene_actions fixture.
  // ---------------------------------------------------------------------------

  it('fires the action with whisper delivery from the submenu (#903)', async () => {
    const { user } = await openIntimidateSubmenu();
    await user.click(screen.getByText('Subtly (target only)'));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '7',
        expect.objectContaining({
          action_key: 'intimidate',
          target_persona_id: 10,
          delivery: 'whisper',
        })
      );
    });
  });

  it('fires "Openly (whole room)" with pose delivery (#903)', async () => {
    const { user } = await openIntimidateSubmenu();
    await user.click(screen.getByText('Openly (whole room)'));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '7',
        expect.objectContaining({ action_key: 'intimidate', delivery: 'pose' })
      );
    });
  });

  it('fires "At your table" with table_talk delivery (#903)', async () => {
    const { user } = await openIntimidateSubmenu();
    await user.click(screen.getByText('At your table'));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '7',
        expect.objectContaining({ action_key: 'intimidate', delivery: 'table_talk' })
      );
    });
  });

  it('fires the default entry with no delivery so the backend resolves it (#903)', async () => {
    const { user } = await openIntimidateSubmenu();
    await user.click(screen.getByText(/^Default/));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '7',
        expect.objectContaining({ action_key: 'intimidate', delivery: undefined })
      );
    });
  });

  it('hides "Subtly (choose listeners…)" when no other personas are present (#907)', async () => {
    await openIntimidateSubmenu();
    expect(screen.queryByText('Subtly (choose listeners…)')).not.toBeInTheDocument();
  });

  it('shows "Subtly (choose listeners…)" when the scene has other personas, and opens the picker (#907)', async () => {
    // The scene cache is a plain synchronous queryClient.getQueryData() read
    // inside PersonaMenu's render body, not a subscribed useQuery — it must
    // be populated BEFORE the component first renders the submenu, since
    // setting it afterward on an unsubscribed key triggers no re-render.
    // gcTime stays at its default here (unlike every other test's client):
    // a manually `setQueryData`-seeded key with no `useQuery` observer and
    // `gcTime: 0` is garbage-collected on the very next tick, and this test's
    // several `await` steps between seeding and reading are enough ticks for
    // that GC to fire and empty the cache out from under it.
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.setQueryData(['scene', '7'], {
      id: 7,
      personas: [
        { id: 10, name: 'Cassia Vell' },
        { id: 22, name: 'Bystander' },
      ],
    });
    const user = userEvent.setup();
    mockMenu({
      scene_id: 7,
      items: [item('look')],
      scene_actions: [BASE_INTIMIDATE_ACTION] as unknown as PersonaMenuData['scene_actions'],
    });
    renderMenu({ personaId: 10 }, null, queryClient);
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    await screen.findByRole('menu');
    await user.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}{ArrowRight}');
    await screen.findByText(/^Default/);

    const chooseListeners = await screen.findByText('Subtly (choose listeners…)');
    await user.click(chooseListeners);

    expect(await screen.findByText('Whisper to…')).toBeInTheDocument();
    expect(screen.getByText('Bystander')).toBeInTheDocument();
  });

  it('shows an unmet-prerequisite scene action disabled with its reason, not omitted (#2158)', async () => {
    mockMenu({
      scene_id: 7,
      items: [item('look')],
      scene_actions: [
        {
          ...BASE_INTIMIDATE_ACTION,
          prerequisite_met: false,
          prerequisite_reasons: ['Must be in combat'],
        },
      ] as unknown as PersonaMenuData['scene_actions'],
    });
    renderMenu({ personaId: 10 });
    fireEvent.contextMenu(screen.getByText('Cassia Vell'));
    const menu = await screen.findByRole('menu');

    const actionItem = within(menu).getByText('Intimidate').closest('[role="menuitem"], button');
    expect(actionItem).toHaveAttribute('title', expect.stringContaining('Must be in combat'));
    expect(actionItem).toBeDisabled();
  });

  it('renders with a null PersonaCardContext (View sheet becomes a no-op)', () => {
    expect(() => renderMenu()).not.toThrow();
  });
});
