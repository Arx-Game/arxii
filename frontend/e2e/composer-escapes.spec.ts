import { test, expect, type Page } from '@playwright/test';
import { frames, mockRestRoutes, reachReadySession, type Connection } from './support/gameHarness';

// #4346 (ruled 2026-10-13): `/`, `+` and `@` mark a command; `@` and someone
// present addresses them, and wins over a command of the same name; `@` and a
// word that names nobody here and no command of the character's is held in the
// composer, never posted. `@@` and `++` post one literal character. REST and the
// socket are fixtures through the shared harness; the composer, its reading of
// the line and the readers are the real built bundle.

/** A player's command names, as the server's `commands` frame carries them: no staff `desc`. */
const PLAYER_NAMES = ['friend', 'friends', 'look', 'pose', 'say', 'sheet', 'who'];

function commandsFrame(names: string[]): string {
  return JSON.stringify(['commands', [], { names }]);
}

/** Every text line this connection sent. */
function sentText(connection: Connection): string[] {
  return frames(connection)
    .filter(([type]) => type === 'text')
    .map(([, args]) => String(args[0]));
}

async function typeLine(page: Page, line: string): Promise<void> {
  const editor = page.getByRole('textbox');
  await editor.fill(line);
  await editor.press('Enter');
}

/** Records every body the composer posts to the pose endpoint, and accepts it. */
async function recordPoses(page: Page): Promise<Array<Record<string, unknown>>> {
  const posed: Array<Record<string, unknown>> = [];
  await page.route('**/api/interactions/submit-pose/', async (route) => {
    posed.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({ status: 201, contentType: 'application/json', body: '{"id": 501}' });
  });
  return posed;
}

test.describe('@ and + mark a command, and a person present wins (#4346)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  test('in a scene: commands go to the server, @Nyx addresses Nyx, the rest is held', async ({
    page,
  }) => {
    await mockRestRoutes(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const [connection] = await reachReadySession(page);
    connection.route.send(commandsFrame(PLAYER_NAMES));
    const posed = await recordPoses(page);

    // `+` is always a command; `@` and a command the character has is one too.
    await typeLine(page, '+friends');
    await expect.poll(() => sentText(connection)).toContain('+friends');
    await typeLine(page, '@sheet');
    await expect.poll(() => sentText(connection)).toContain('@sheet');
    expect(posed).toHaveLength(0);

    // `@` and someone here addresses them through the pose endpoint's target names.
    await typeLine(page, '@Nyx waves her over.');
    await expect.poll(() => posed.length).toBe(1);
    expect(posed[0]).toMatchObject({ content: 'waves her over.', target_names: ['Nyx'] });

    // `@@` poses one literal at sign and addresses nobody.
    await typeLine(page, '@@everyone gets a round.');
    await expect.poll(() => posed.length).toBe(2);
    expect(posed[1]).toMatchObject({ content: '@everyone gets a round.' });
    expect(posed[1]).not.toHaveProperty('target_names');

    // A player has no `desc`: the line is held, kept, and Send is off.
    const editor = page.getByRole('textbox');
    const held = page.getByTestId('line-held');
    await typeLine(page, '@desc here = A cold room');
    await expect(held).toContainText('Nobody called desc is here, and you have no desc command.');
    await expect(held).toContainText('Your draft is kept.');
    await expect(editor).toHaveValue('@desc here = A cold room');
    await expect(page.getByRole('button', { name: 'Send' })).toBeDisabled();
    expect(sentText(connection)).not.toContain('@desc here = A cold room');
    expect(posed).toHaveLength(2);
    await page.waitForTimeout(300);
    await page.screenshot({ path: '../docs/reviews/4346/held-command-1280.png', fullPage: true });

    // Someone who is not here is held the same way.
    await editor.fill('@Nyx,@Gone wave.');
    await expect(held).toContainText('Nobody called Gone is here.');
    await page.screenshot({ path: '../docs/reviews/4346/held-target-1280.png', fullPage: true });

    // Once the frame names `desc` (a staff character), the same line is the command.
    connection.route.send(commandsFrame([...PLAYER_NAMES, 'desc']));
    await editor.fill('@desc here = A cold room');
    await expect(held).toHaveCount(0);
    await editor.press('Enter');
    await expect.poll(() => sentText(connection)).toContain('@desc here = A cold room');
    expect(posed).toHaveLength(2);
    expect(errors).toEqual([]);
  });

  test('outside a scene: the pose command carries @Nyx and @@ for the server parser', async ({
    page,
  }) => {
    await mockRestRoutes(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const [connection] = await reachReadySession(page, { scene: false });
    connection.route.send(commandsFrame(PLAYER_NAMES));

    await typeLine(page, '@Nyx waves.');
    await expect.poll(() => sentText(connection)).toContain('pose @Nyx waves.');
    await typeLine(page, '@@everyone gets a round.');
    await expect.poll(() => sentText(connection)).toContain('pose @@everyone gets a round.');
    await typeLine(page, '+1 to that.');
    await expect.poll(() => sentText(connection)).toContain('pose +1 to that.');
    await typeLine(page, '++friend is a word.');
    await expect.poll(() => sentText(connection)).toContain('pose +friend is a word.');
    await typeLine(page, '+friends');
    await expect.poll(() => sentText(connection)).toContain('+friends');

    // Before #4346 this went out as `pose @desc limbo = ...`, and the server's
    // parser dropped "desc" and posed "limbo = A cold room". Now it is held.
    await page.setViewportSize({ width: 390, height: 844 });
    await typeLine(page, '@desc limbo = A cold room');
    await expect(page.getByTestId('line-held')).toContainText('Nobody called desc is here');
    expect(sentText(connection).some((line) => line.includes('limbo = A cold room'))).toBe(false);
    await page.waitForTimeout(300);
    await page.screenshot({ path: '../docs/reviews/4346/held-command-390.png', fullPage: true });
    expect(errors).toEqual([]);
  });
});
