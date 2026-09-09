import { test, expect, type WebSocketRoute } from '@playwright/test';

// A browser regression for the entry state from #3731. REST and socket data
// are fixtures; backend wire serialization is exercised by the Python tests.
test('a quiet-room entry preserves an editable draft until structured presence arrives', async ({
  page,
}) => {
  const character = {
    id: 1,
    name: 'Tehom',
    character_id: 18,
    profile_picture_url: null,
    primary_persona_id: 7,
    active_persona_id: 7,
    unread_narrative_count: 0,
    lifecycle_state: 'ALIVE',
    roster_type: 'Active',
    character_type: 'PC',
  };
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'test-player',
          display_name: 'Test player',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: false,
          is_staff: false,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: 1,
          selected_entry: character,
        },
      });
    } else if (path === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [character] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
  let socket: WebSocketRoute | undefined;
  const sent: string[] = [];
  await page.routeWebSocket('**', (route) => {
    socket = route;
    route.onMessage((message) => sent.push(String(message)));
  });
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/game');
  const editor = page.getByRole('textbox');
  await expect(editor).toBeEnabled();
  await expect(page.getByText('Entering world', { exact: true })).toBeVisible();
  await editor.fill('A quiet beginning.\n\nThe draft stays here.');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeDisabled();
  await editor.press('Control+Enter');
  expect(sent.map((frame) => JSON.parse(frame)[1][0])).toEqual(['@ic Tehom']);

  socket!.send(
    JSON.stringify([
      'room_state',
      [],
      {
        room: { dbref: '#2', name: 'Quiet courtyard', description: 'Rain rests on the stones.' },
        characters: [],
        objects: [],
        exits: [],
        scene: null,
      },
    ])
  );
  socket!.send(
    JSON.stringify([
      'puppet_changed',
      [],
      {
        session_id: 162,
        character_id: 18,
        character_name: 'Tehom',
      },
    ])
  );
  await expect(page.getByText('In world', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Quiet courtyard', exact: true })).toBeVisible();
  await expect(editor).toHaveValue('A quiet beginning.\n\nThe draft stays here.');
  await expect(page.getByRole('button', { name: 'Send', exact: true })).toBeEnabled();
  await expect(page.getByText(/puppet_changed/)).toHaveCount(0);
  expect(errors).toEqual([]);
  await page.screenshot({ path: 'test-results/game-entry.png', fullPage: true });
});
