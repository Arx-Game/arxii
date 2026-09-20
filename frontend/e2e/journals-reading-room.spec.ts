/**
 * World › Journals, the Reading Room (#3941): the real `JournalsPage` mounted at
 * its real route inside the real app shell, with every API call answered by
 * fixtures shaped like the approved demo's sample entries.
 *
 * Nothing here needs a backend: `/api/**` is intercepted, so this spec also
 * serves as the demo-fidelity evidence harness (set EVIDENCE_DIR to write the
 * screenshots the review report cites). The rows mirror the demo
 * (https://claude.ai/artifact/JW74XTJ7cPbqV51JHpPqDW): a rival's entry about the
 * viewer, the viewer's own black entry, an entry with two responses, a First
 * Journal by a writer open to retorts, a relationship entry, and a post mortem.
 *
 * Run with: cd frontend && pnpm playwright test e2e/journals-reading-room.spec.ts
 */

import { test, expect, type Page } from '@playwright/test';

const EVIDENCE_DIR = process.env.EVIDENCE_DIR ?? '';

/** The viewer in most runs: Ilsavet du Verane, sheet 20, primary persona 5. */
const ILSAVET = {
  id: 1,
  name: 'Ilsavet du Verane',
  character_id: 20,
  profile_picture_url: null,
  primary_persona_id: 5,
  active_persona_id: 5,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

/** The viewer in the "another player" runs: Tessaly Vane, sheet 25, persona 6. */
const TESSALY = {
  ...ILSAVET,
  id: 2,
  name: 'Tessaly Vane',
  character_id: 25,
  primary_persona_id: 6,
  active_persona_id: 6,
};

interface Row {
  id: number;
  author: number;
  author_name: string;
  title: string;
  body: string;
  kind: string;
  is_public: boolean;
  response_type: string | null;
  parent: number | null;
  created_at: string;
  edited_at: string | null;
  tags: { id: number; name: string }[];
  response_count: number;
  posthumous_override: string;
  revealed_at: string | null;
  is_posthumous: boolean;
  about: number | null;
  about_name: string | null;
  author_persona_id: number | null;
  ic_timestamp: string | null;
  can_retort: boolean;
  is_own: boolean;
}

function row(
  over: Partial<Row> & Pick<Row, 'id' | 'author' | 'author_name' | 'title' | 'body'>
): Row {
  return {
    kind: 'entry',
    is_public: true,
    response_type: null,
    parent: null,
    created_at: '2026-09-17T10:00:00Z',
    edited_at: null,
    tags: [],
    response_count: 0,
    posthumous_override: 'inherit',
    revealed_at: null,
    is_posthumous: false,
    about: null,
    about_name: null,
    author_persona_id: 9,
    ic_timestamp: '1012-09-19T10:00:00Z',
    can_retort: false,
    is_own: false,
    ...over,
  };
}

/** The stream as the viewer (Ilsavet) sees it: her own black entry included. */
function rows(viewerIsIlsavet: boolean): Row[] {
  const own = viewerIsIlsavet;
  const list: Row[] = [
    row({
      id: 2,
      author: 10,
      author_name: 'Corvin Ashe',
      title: 'Third correction',
      body: 'The Lady du Verane corrected me before the council for the third time this season. The first I deserved. The second was a matter of taste. The third was a performance, and I have decided to admire it, since I cannot yet answer it.\n\nLet it be recorded that I have started counting.',
      created_at: '2026-09-18T10:00:00Z',
      ic_timestamp: '1012-09-22T10:00:00Z',
      about: 20,
      about_name: 'Ilsavet du Verane',
      tags: [{ id: 1, name: 'council' }],
      response_count: 1,
      author_persona_id: 11,
      can_retort: viewerIsIlsavet,
    }),
    row({
      id: 3,
      author: 20,
      author_name: 'Ilsavet du Verane',
      title: 'On the matter of the harbor tolls',
      body: 'The council will vote on the tolls before the month is out, and I intend that it vote correctly. A toll is not a tax; a toll is a promise that the road will still be there in the morning. Those who cannot tell the two apart should not be seated where the difference is decided.\n\nI have written to the harbormaster. I expect no reply, which is itself a reply.',
      tags: [
        { id: 2, name: 'harbor' },
        { id: 1, name: 'council' },
      ],
      response_count: 2,
      author_persona_id: 5,
      is_own: own,
      can_retort: !own,
    }),
    row({
      id: 4,
      author: 30,
      author_name: 'Maelis Tarrow',
      title: 'First Journal',
      kind: 'first_journal',
      body: 'To the keepers of the Great Archive of Vellichor, from a woman who has never before been asked to write anything down that mattered.\n\nI came to the city with a letter, a knife, and my mother’s name. The letter was for a man who is dead. The knife is under the bed. The name I am still deciding what to do with.',
      created_at: '2026-09-15T10:00:00Z',
      ic_timestamp: '1012-09-13T10:00:00Z',
      author_persona_id: 12,
      can_retort: true,
    }),
    row({
      id: 6,
      author: 20,
      author_name: 'Ilsavet du Verane',
      title: 'Corvin, at the gate',
      body: 'He was waiting at the north gate as though he had happened to be there. He had not happened to be there. We spoke of horses for the length of the wall and of nothing else, which is the most either of us has admitted in a year.',
      created_at: '2026-09-09T10:00:00Z',
      ic_timestamp: '1012-09-01T10:00:00Z',
      about: 10,
      about_name: 'Corvin Ashe',
      author_persona_id: 5,
      is_own: own,
      can_retort: !own,
    }),
    row({
      id: 5,
      author: 40,
      author_name: 'Brother Odo',
      title: 'The bell that would not ring',
      body: 'I have told no one that the bell cracked in the spring. I muffle it with my own hands each dawn and let them believe it is the fog. If I am read after I am gone, know that it was not vanity. A cracked bell in a frightened city is a rumor with a rope on it.',
      created_at: '2026-09-02T10:00:00Z',
      ic_timestamp: '1012-09-04T10:00:00Z',
      is_public: false,
      revealed_at: '2026-09-16T10:00:00Z',
      is_posthumous: true,
      tags: [{ id: 3, name: 'chapel' }],
      author_persona_id: 13,
    }),
  ];
  if (viewerIsIlsavet) {
    list.splice(
      1,
      0,
      row({
        id: 1,
        author: 20,
        author_name: 'Ilsavet du Verane',
        title: 'What I did not say to Corvin',
        body: 'I let him finish. That is the whole of my restraint tonight, and it cost me more than the tolls will. He thinks the harbor is a ledger. It is a throat.\n\nIf I write the rest of this down I will have to admit I was afraid of him, so I will not.',
        created_at: '2026-09-18T09:00:00Z',
        ic_timestamp: '1012-09-22T09:00:00Z',
        is_public: false,
        posthumous_override: 'seal',
        about: 10,
        about_name: 'Corvin Ashe',
        author_persona_id: 5,
        is_own: true,
      })
    );
  }
  return list;
}

function responsesFor(id: number): Row[] {
  if (id !== 3) return [];
  return [
    row({
      id: 101,
      author: 10,
      author_name: 'Corvin Ashe',
      title: 'A toll is a tax with better manners',
      body: 'The road was there before the toll and will be there after. What the toll promises is that someone is paid to say so.',
      response_type: 'retort',
      parent: 3,
      author_persona_id: 11,
    }),
    row({
      id: 102,
      author: 40,
      author_name: 'Brother Odo',
      title: 'Well put',
      body: 'A promise that the road will still be there. I shall borrow that.',
      response_type: 'praise',
      parent: 3,
      author_persona_id: 13,
    }),
  ];
}

async function mockApi(page: Page, viewerIsIlsavet: boolean, staff = false): Promise<string[]> {
  const requests: string[] = [];
  const all = rows(viewerIsIlsavet);
  const viewer = viewerIsIlsavet ? ILSAVET : TESSALY;
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    requests.push(`${route.request().method()} ${path}${url.search}`);
    if (path === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'ilsavet',
          display_name: 'Ilsavet',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: false,
          is_staff: staff,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: viewer.id,
          selected_entry: viewer,
        },
      });
    } else if (path === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [viewer] });
    } else if (path === '/api/journals/entries/mine/') {
      const mine = all.filter((r) => r.author === 20);
      await route.fulfill({
        json: { count: mine.length, next: null, previous: null, results: mine },
      });
    } else if (path === '/api/journals/entries/disposition/') {
      await route.fulfill({
        json: {
          posthumous_journal_disposition: 'reveal',
          retort_consent: 'rivals',
          posts_this_week: 1,
          rewarded_posts_per_week: 3,
        },
      });
    } else if (path === '/api/journals/entries/') {
      let list = all;
      const author = url.searchParams.get('author');
      const about = url.searchParams.get('about');
      if (author) list = list.filter((r) => String(r.author) === author);
      if (about) list = list.filter((r) => String(r.about) === about);
      // `visited_at` null is a first-time reader: the panel still counts what is new,
      // and "Since your last visit" leaves the stream unnarrowed (see SearchPanel).
      await route.fulfill({
        json: {
          count: list.length,
          next: null,
          previous: null,
          results: list,
          since_visit_count: 4,
          visited_at: null,
        },
      });
    } else if (/^\/api\/journals\/entries\/\d+\/$/.test(path)) {
      const id = Number(path.split('/')[4]);
      const entry = all.find((r) => r.id === id);
      if (!entry) return route.fulfill({ status: 404, json: { detail: 'Not found.' } });
      await route.fulfill({ json: { ...entry, responses: responsesFor(id) } });
    } else if (path === '/api/progression/nominations/') {
      await route.fulfill({ json: [] });
    } else if (path.includes('search')) {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
  return requests;
}

async function shot(page: Page, name: string): Promise<void> {
  if (!EVIDENCE_DIR) return;
  await page.screenshot({ path: `${EVIDENCE_DIR}/${name}.png`, fullPage: true });
}

test.describe('World › Journals, the Reading Room (#3941)', () => {
  test('the stream, as the docked character', async ({ page }) => {
    const requests = await mockApi(page, true);
    await page.goto('/journals');
    await expect(page.getByRole('heading', { name: 'Journals' })).toBeVisible();
    // Rows carry their prose without being opened, and the black entry is banded.
    await expect(page.getByText('Third correction')).toBeVisible();
    await expect(page.getByText(/The Lady du Verane corrected me/)).toBeVisible();
    await expect(page.getByText('Black journal')).toBeVisible();
    await expect(page.getByText(/Post mortem/)).toBeVisible();
    await expect(page.getByText('First Journal', { exact: true })).toHaveCount(2); // the band and the title
    // Collapsed: no actions, no tags.
    await expect(page.getByText('Praise')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Search' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Your journal' })).toBeVisible();
    // The first stream request marks the visit, and only the first.
    const listCalls = requests.filter((r) => r.startsWith('GET /api/journals/entries/?'));
    expect(listCalls[0]).toContain('mark_visit=1');
    await shot(page, '1-stream-self');

    // The date flips to the posting date without opening the row.
    // exact: the row head is itself a button whose name contains the date.
    await page.getByRole('button', { name: '22 September 1012', exact: true }).first().click();
    await expect(
      page.getByRole('button', { name: '18 Sep 2026', exact: true }).first()
    ).toBeVisible();
    await expect(page.getByText('Praise')).toHaveCount(0);
  });

  test('Search folds down with the index and opens a row', async ({ page }) => {
    await mockApi(page, true);
    await page.goto('/journals');
    await page.getByRole('button', { name: 'Search' }).click();
    await expect(page.getByText('Find a writer')).toBeVisible();
    await expect(page.getByText(/Since your last visit/)).toContainText('4');
    await expect(page.getByText('Post mortems')).toBeVisible();
    await expect(page.getByText('Black journals only')).toHaveCount(0);
    await expect(page.getByRole('table')).toBeVisible();
    await shot(page, '1b-search-open');
    await page.getByRole('cell', { name: 'On the matter of the harbor tolls' }).click();
    await expect(page.getByRole('table')).toHaveCount(0);
    await expect(page.getByText('harbor', { exact: true })).toBeVisible();
  });

  test('an opened entry, as another player', async ({ page }) => {
    await mockApi(page, false);
    await page.goto('/journals');
    await page.getByText('On the matter of the harbor tolls').click();
    await expect(page.getByText(/I have written to the harbormaster/)).toBeVisible();
    await expect(page.getByText('harbor', { exact: true })).toBeVisible();
    await expect(page.getByText('Praise').first()).toBeVisible();
    await expect(page.getByText('Retort').first()).toBeVisible();
    await expect(page.getByText('Condemn').first()).toBeVisible();
    await expect(page.getByText('A toll is a tax with better manners')).toBeVisible();
    await expect(page.getByText('Mute writer')).toBeVisible();
    await expect(page.getByText('Block writer')).toBeVisible();
    await shot(page, '3-opened-other');
    // A post mortem takes no actions.
    await page.getByText('The bell that would not ring').click();
    await expect(page.getByText(/cracked bell in a frightened city/)).toBeVisible();
    const postMortem = page.locator('article', { hasText: 'The bell that would not ring' });
    await expect(postMortem.getByText('Praise')).toHaveCount(0);
    await expect(postMortem.getByText('Mute writer')).toHaveCount(0);
  });

  test("a writer's journal", async ({ page }) => {
    await mockApi(page, true);
    await page.goto('/journals?writer=20');
    await expect(page.getByRole('heading', { name: 'Ilsavet du Verane' })).toBeVisible();
    await expect(page.getByRole('button', { name: /^All/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /^About Corvin Ashe/ }).first()).toBeVisible();
    // The reverse pill carries the reverse cut's total (one entry, "Third correction",
    // is about sheet 20), matching the demo's "Written about her · 1".
    await expect(page.getByRole('button', { name: 'Written about them · 1' })).toBeVisible();
    await expect(page.getByText('Third correction')).toHaveCount(0);
    // The plate stands alone as the header: no page-level "Journals" heading, and
    // none of the stream's Search/Write/Your journal row above it.
    await expect(page.getByRole('heading', { name: 'Journals' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Search' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Write', exact: true })).toHaveCount(0);
    await expect(page.getByRole('link', { name: 'Your journal' })).toHaveCount(0);
    await shot(page, '2-writer');
  });

  test('your journal', async ({ page }) => {
    await mockApi(page, true);
    await page.goto('/journals?mine=1');
    await expect(page.getByText('Your journal')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Reveal' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Remain sealed' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Rivals only' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Anyone' })).toBeVisible();
    await expect(page.getByText('What I did not say to Corvin')).toBeVisible();
    await shot(page, '4-mine');
  });

  test('the desk', async ({ page }) => {
    await mockApi(page, true);
    await page.goto('/journals');
    await page.getByRole('button', { name: 'Write', exact: true }).first().click();
    await expect(page.getByRole('button', { name: 'White journal · Public' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Black journal · Private' })).toBeVisible();
    await expect(page.getByText('After your death')).toHaveCount(0);
    await expect(page.getByText(/rewarded entries left this week/)).toBeVisible();
    await expect(page.getByText(/Read by anyone/)).toHaveCount(0);
    await page.getByRole('button', { name: 'Black journal · Private' }).click();
    await expect(page.getByText('After your death')).toBeVisible();
    await shot(page, '5-desk-black');
  });

  test('phone width', async ({ page }) => {
    await page.setViewportSize({ width: 400, height: 900 });
    await mockApi(page, true);
    await page.goto('/journals');
    await expect(page.getByText('Third correction')).toBeVisible();
    // The app shell's own mobile-menu button overflows the viewport by 10px on every
    // page (pre-existing, not this branch); the journals column itself must not.
    const columnWidth = await page.evaluate(() => {
      const root = document.querySelector('.journals');
      return root ? root.scrollWidth : -1;
    });
    expect(columnWidth).toBeGreaterThan(0);
    expect(columnWidth).toBeLessThanOrEqual(400);
    await shot(page, '6-phone');
  });
});
