import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Browser, type Page } from '@playwright/test';

/**
 * Review evidence for #4361 against a real server (rt_4361, seeded by
 * seed_4361.py): staff edit an organization's faction rules and one placement
 * in the admin, a GM edits the same placement in the beat dialog, then (after
 * the beat runs) the GM panel and a player's card show the result. Not a CI
 * spec: it needs that seeded server on :4001. PART selects the phase.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4361');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);
const PASSWORD = 'TestPass123!';
const IDS = JSON.parse(process.env.RT_IDS ?? '{}') as Record<string, number>;

async function signIn(browser: Browser, username: string): Promise<Page> {
  const context = await browser.newContext({ viewport: { width: 1500, height: 1100 } });
  const page = await context.newPage();
  await page.goto('/login');
  await page.getByPlaceholder('Username or Email').fill(username);
  await page.getByPlaceholder('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Log In', exact: true }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'));
  return page;
}

test.describe.configure({ mode: 'serial' });

test('part 1: staff and GM author the placement and the faction rules', async ({ browser }) => {
  test.skip(process.env.PART !== '1', 'part 1 only');
  test.setTimeout(240_000);
  const staff = await signIn(browser, 'staff4361');

  // The Organization change page links to its Faction Rules page.
  await staff.goto(`/admin/arxii/organization/${IDS.company}/change/`);
  await staff.getByRole('link', { name: 'Edit its faction rules' }).click();
  await expect(staff.locator('#faction-rules-root h1')).toContainText(
    'Faction rules: Saltreed Company'
  );
  await expect(staff.locator('.pred-builder').first()).toBeVisible();
  await staff.screenshot({ path: shot('01-faction-rules-page.png'), fullPage: true });

  // Test a character: Ottilie, a former member honored by the Harbor Guild.
  await staff.locator('#id_character').fill('Ottilie');
  await staff.getByRole('button', { name: 'Test' }).click();
  await expect(
    staff.getByText('association: formerly a member of Saltreed Company (test)')
  ).toBeVisible();
  await expect(
    staff.getByText(/Harbor Guild \(test\) holds you in high regard \(Honored\)/)
  ).toBeVisible();
  await staff
    .locator('#test-module')
    .screenshot({ path: shot('02-faction-rules-test-character.png') });

  // The beat's inline links each line to its Placement page.
  await staff.goto(`/admin/arxii/beat/${IDS.beat}/change/`);
  await staff.getByRole('link', { name: 'Edit placement' }).click();
  await expect(staff.locator('#placement-root h1')).toContainText('Placement: Sellsword (test) x6');
  await staff.screenshot({ path: shot('03-placement-before.png'), fullPage: true });
  await staff.getByLabel('Greedy (test) here').selectOption('3');
  await staff.getByLabel('Fearful (test) here').selectOption('remove');
  await staff.getByLabel('Switch off has_capability: Spellcraft').check();
  // A drive the template lacks, added for this placement only.
  await staff.getByRole('button', { name: '+ Add a drive for this placement' }).click();
  await staff
    .locator('#added-body select[name$="-property"]')
    .last()
    .selectOption({ label: 'Prudent (test)' });
  await staff.click('input[name="save_continue"]');
  await expect(staff.getByText('Placement saved.')).toBeVisible();
  await expect(staff.getByText('edited', { exact: true })).toBeVisible();
  await expect(staff.getByText('removed here')).toBeVisible();
  await staff.screenshot({ path: shot('04-placement-after-save.png'), fullPage: true });

  // The GM edits the same line in the story author's beat dialog.
  const gm = await signIn(browser, 'gm4361');
  await gm.goto(`/stories/author/${IDS.story}`);
  await gm.getByText('The Corle gate (test)').first().click();
  await gm.getByRole('button', { name: /Episode \(test\)/ }).click();
  await gm.getByRole('button', { name: 'Edit beat' }).first().click();
  const panel = gm.getByTestId('placement-panel-0');
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await expect(panel.getByLabel('Greedy (test) here')).toHaveValue('3');
  await expect(panel.getByLabel('Off: has_capability: Spellcraft')).toBeChecked();
  await panel.getByLabel('Off: is_member_of_org: Riverland Guilds (test)').check();
  await expect(gm.getByTestId('placement-summary-0')).toContainText('4 faction rules');
  await gm.screenshot({ path: shot('05-gm-beat-dialog-placement.png'), fullPage: true });
  await panel.screenshot({ path: shot('05b-gm-beat-dialog-placement-panel.png') });
  await gm.getByRole('button', { name: 'Save Beat' }).click();
  await expect(gm.getByRole('heading', { name: 'Edit Beat' })).toHaveCount(0, { timeout: 20_000 });
});

test('part 2: the spawned standoff carries the placement', async ({ browser }) => {
  test.skip(process.env.PART !== '2', 'part 2 only');
  test.setTimeout(240_000);
  const scene = `/scenes/${IDS.scene}`;

  const gm = await signIn(browser, 'gm4361');
  await gm.goto(scene);
  await gm.getByTestId('rail-tab-gm').click();
  const group = gm.getByTestId('gm-standoff-group').first();
  await expect(group).toBeVisible({ timeout: 20_000 });
  await expect(group).toContainText('Greedy (test), Defining');
  await expect(group).not.toContainText('Fearful (test)');
  await expect(group).toContainText('Saltreed Company (test)');
  await expect(group).not.toContainText('Spellcraft');
  await expect(group).not.toContainText('Riverland Guilds (test)');
  await expect(group).toContainText('Prudent (test), Minor edited here read');
  await gm
    .getByTestId('gm-standoff-panel')
    .screenshot({ path: shot('06-gm-panel-edits-and-sources.png') });

  const ottilie = await signIn(browser, 'ottilie4361');
  await ottilie.goto(scene);
  await expect(ottilie.getByText('PLACEHOLDER company angle (former member)')).toBeVisible({
    timeout: 20_000,
  });
  await ottilie.screenshot({
    path: shot('07-player-angle-from-organization-rule.png'),
    fullPage: true,
  });

  // A template edit after the spawn leaves the running standoff alone.
  const staff = await signIn(browser, 'staff4361');
  await staff.goto(`/admin/_standoff_profile/${IDS.template}/`);
  await expect(staff.getByText('Also applies (inherited)')).toBeVisible();
  await staff.screenshot({
    path: shot('09-profile-builder-affiliation-and-inherited.png'),
    fullPage: true,
  });
  await staff.locator('#id_cause').selectOption('none');
  await staff.locator('#id_cause_margin_percent').fill('50');
  await staff
    .locator('#drives-body tr')
    .filter({ has: staff.locator('option[selected]', { hasText: 'Loyal (test)' }) })
    .locator('input[type=checkbox]')
    .check();
  await staff.click('input[name="save_continue"]');
  await expect(staff.getByText('Saved and credited to you.')).toBeVisible();
  await gm.reload();
  await gm.getByTestId('rail-tab-gm').click();
  await expect(gm.getByTestId('gm-standoff-group').first()).toContainText('Orders', {
    timeout: 20_000,
  });
  await expect(gm.getByTestId('gm-standoff-group').first()).toContainText('Loyal (test), Minor');
  await expect(gm.getByTestId('gm-standoff-group').first()).toContainText(
    'Saltreed Company (test)'
  );
  await gm
    .getByTestId('gm-standoff-panel')
    .screenshot({ path: shot('08-gm-panel-after-template-edit.png') });
});

async function testCharacter(page: Page, name: string): Promise<string> {
  await page.locator('#id_character').fill(name);
  await page.getByRole('button', { name: 'Test' }).click();
  await expect(page.locator('#test-module table, #test-module p').first()).toBeVisible();
  return page.locator('#test-module').innerText();
}

test('part 3: the other leaves through the admin, and the mission studio', async ({ browser }) => {
  test.skip(process.env.PART !== '3', 'part 3 only');
  test.setTimeout(240_000);
  const staff = await signIn(browser, 'staff4361');
  const company = `/admin/_faction_rules/organization/${IDS.company}/`;

  // Save an "at most" reputation rule with the widget: despised by the harbor guild.
  await staff.goto(company);
  await staff.getByRole('button', { name: '+ Add another faction rule' }).click();
  const block = staff.locator('#rules-body .sp-rule').last();
  await block.getByRole('button', { name: '+ Leaf' }).click();
  await block.locator('select.pred-leaf-name').selectOption('max_org_reputation');
  await block.locator('.pred-param input.pred-input').fill('Harbor Guild (test)');
  await block.locator('.pred-param select.pred-input').selectOption('despised');
  await block.locator('input[name$="difficulty_shift_bands"]').fill('1');
  await block.locator('input[name$="drive_shift"]').fill('0');
  await block.locator('textarea[name$="angle_text"]').fill('PLACEHOLDER despised angle');
  await staff.click('input[name="save_continue"]');
  await expect(staff.getByText('Faction rules saved.')).toBeVisible();
  await expect(
    staff.getByText('max_org_reputation: Harbor Guild (test), despised').first()
  ).toBeVisible();
  await staff.screenshot({ path: shot('10-max-rule-saved.png'), fullPage: true });

  const shots: [string, string][] = [
    ['Aubrin', '11-test-aubrin-despised.png'],
    ['Ottilie', '12-test-ottilie-honored.png'],
    ['Bram', '13-test-bram-exile.png'],
    ['Lou', '14-test-lou-left-three-years-ago.png'],
    ['Wes', '15-test-wes-steady-work.png'],
  ];
  for (const [name, file] of shots) {
    await staff.goto(company);
    const text = await testCharacter(staff, name);
    console.log(`== ${name}:\n${text}`);
    await staff.locator('#test-module').screenshot({ path: shot(file) });
  }
  await staff.goto(`/admin/_faction_rules/organization/${IDS.house}/`);
  console.log(`== Kira:\n${await testCharacter(staff, 'Kira')}`);
  await staff.locator('#test-module').screenshot({ path: shot('16-test-kira-kin.png') });
  await staff.goto(`/admin/_faction_rules/organization/${IDS.covert}/`);
  console.log(`== Cyra:\n${await testCharacter(staff, 'Cyra')}`);
  await staff.locator('#test-module').screenshot({ path: shot('17-test-cyra-covert.png') });

  // The mission studio's option page carries the same placement panel.
  await staff.goto(`/staff/missions/${IDS.mission}/nodes/${IDS.node}/options/${IDS.option}`);
  const panel = staff.getByTestId('placement-panel-0');
  await expect(panel).toBeVisible({ timeout: 20_000 });
  await panel.getByLabel('Greedy (test) here').selectOption('1');
  await panel.getByLabel('Off: has_capability: Warding').check();
  await panel.screenshot({ path: shot('18-mission-studio-placement-panel.png') });
  await staff.getByRole('button', { name: 'Save', exact: true }).click();
  await staff.waitForTimeout(2000);
  await staff.reload();
  await expect(staff.getByTestId('placement-panel-0').getByLabel('Greedy (test) here')).toHaveValue(
    '1',
    {
      timeout: 20_000,
    }
  );
  await expect(
    staff.getByTestId('placement-panel-0').getByLabel('Off: has_capability: Warding')
  ).toBeChecked();
  await staff
    .getByTestId('placement-panel-0')
    .screenshot({ path: shot('19-mission-studio-after-reload.png') });
});
