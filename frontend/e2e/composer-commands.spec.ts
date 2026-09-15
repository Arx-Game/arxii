import { test, expect, type Page } from '@playwright/test';
import { frames, mockRestRoutes, reachReadySession, type Connection } from './support/gameHarness';

// #3857: the composer's label is the truth (a plain line is a pose), a line
// starting with `/` is a command, and staff get a Commands mode whose lines go
// as typed and whose answers land in the console sheet, never in the column.
// One journey per demo screen (issue #3857, demo v1). REST and the socket are
// fixtures through the shared harness; the composer, the selector, the sheet
// and the readers are the real ones.

function text(line: string, kwargs: Record<string, unknown> = {}): string {
  return JSON.stringify(['text', [line], kwargs]);
}

/** Every text frame this connection sent, as `[line, kwargs]`. */
function sentLines(connection: Connection): Array<[string, Record<string, unknown>]> {
  return frames(connection)
    .filter(([type]) => type === 'text')
    .map(([, args, kwargs]) => [String(args[0]), kwargs]);
}

async function typeLine(page: Page, line: string): Promise<void> {
  const editor = page.getByRole('textbox');
  await editor.fill(line);
  await editor.press('Enter');
}

test.describe('the composer poses by default, and staff have a console (#3857)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  test('screens 1 and 2: a plain line is a pose, a slash line is a command', async ({ page }) => {
    await mockRestRoutes(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const [connection] = await reachReadySession(page);

    // Screen 1: the selector reads Pose on a fresh connection, and a plain
    // line goes to the server as a pose, not verbatim.
    await expect(page.getByRole('button', { name: /^Pose$/ })).toBeVisible();
    // In a scene a pose takes the REST path; the fixture answers it and keeps
    // the body, so the assertion is on what the composer sent.
    const posed: string[] = [];
    await page.route('**/api/interactions/submit-pose/', async (route) => {
      posed.push(String(route.request().postDataJSON()?.content));
      await route.fulfill({ status: 201, contentType: 'application/json', body: '{"id": 501}' });
    });
    await typeLine(page, 'glances up at the rain.');
    await expect.poll(() => posed).toContain('glances up at the rain.');
    expect(sentLines(connection).map(([line]) => line)).not.toContain('glances up at the rain.');
    // A non-staff account has no Commands entry in the selector.
    await page.getByRole('button', { name: /^Pose$/ }).click();
    await expect(page.getByRole('menuitem', { name: 'Pose' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Commands' })).toHaveCount(0);
    await page.keyboard.press('Escape');

    // Screen 2: `/look` reaches the server as `look`, the reply is a look note;
    // `//` poses a literal slash.
    await typeLine(page, '/look');
    await expect.poll(() => sentLines(connection).map(([line]) => line)).toContain('look');
    connection.route.send(text('Quiet courtyard<br>Rain rests on the stones.', { type: 'look' }));
    await expect(page.locator('[data-testid="feed-note"][data-kind="look"]')).toHaveCount(1);
    await typeLine(page, '//shrugs');
    await expect.poll(() => posed).toContain('/shrugs');
    await page.getByRole('textbox').fill('/look');
    await page.waitForTimeout(300);
    await page.screenshot({ path: '../docs/reviews/3857/composer-slash-1280.png', fullPage: true });
    expect(errors).toEqual([]);
  });

  test('screens 3 to 5: staff pick Commands, the answers land in the console', async ({ page }) => {
    await mockRestRoutes(page, { staff: true });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const [connection] = await reachReadySession(page);

    // Screen 3: the selector lists Commands after a rule, for staff.
    await page.getByRole('button', { name: /^Pose$/ }).click();
    await expect(page.getByRole('menuitem', { name: 'Commands' })).toBeVisible();
    await page.screenshot({
      path: '../docs/reviews/3857/composer-staff-menu-1280.png',
      fullPage: true,
    });

    // Screen 4: in Commands mode the formatting steps aside and the line goes as typed.
    await page.getByRole('menuitem', { name: 'Commands' }).click();
    await expect(page.getByRole('button', { name: /^Commands$/ })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Bold' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: /^Console/ })).toBeVisible();
    await typeLine(page, '@dig The Eastern Colonnade = east;e, west;w');
    const sent = sentLines(connection);
    expect(sent).toContainEqual(['@dig The Eastern Colonnade = east;e, west;w', { console: true }]);

    // The server tags its answer; it opens the console and never touches the column.
    connection.route.send(
      text('Created room The Eastern Colonnade(#412) of type typeclasses.rooms.Room.', {
        console: true,
      })
    );
    connection.route.send(
      text('Created Exit from Quiet courtyard to The Eastern Colonnade: east(#413) (e).', {
        console: true,
      })
    );
    const sheet = page.getByRole('dialog', { name: 'Console' });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByTestId('staff-console-lines')).toContainText(
      '\u203a @dig The Eastern Colonnade = east;e, west;w'
    );
    await expect(sheet.getByTestId('staff-console-lines')).toContainText('Created room');
    await expect(page.locator('[data-testid="feed-note"]')).toHaveCount(0);
    await page.waitForTimeout(400);
    await page.screenshot({
      path: '../docs/reviews/3857/composer-console-1280.png',
      fullPage: true,
    });

    // Screen 5: a mistyped staff command answers in the console too, typed error or not.
    await page.getByRole('button', { name: 'Close' }).click();
    await expect(sheet).toHaveCount(0);
    await typeLine(page, '@teleprot #412');
    connection.route.send(
      text('Command \'@teleprot\' is not available. Maybe you meant "@teleport"?', {
        type: 'error',
        console: true,
      })
    );
    await expect(page.getByRole('dialog', { name: 'Console' })).toBeVisible();
    await expect(page.getByRole('dialog', { name: 'Console' })).toContainText('@teleprot');
    await expect(page.locator('[data-testid="feed-note"][data-kind="error"]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Clear' }).click();
    await expect(page.getByText('Nothing yet. Pick Commands and type one.')).toBeVisible();
    expect(errors).toEqual([]);
  });
});
