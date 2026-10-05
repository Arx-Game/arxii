import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4151: the real `/characters/:entry` sheet on the production
 * bundle, every `/api/**` call answered by fixtures shaped like the serializers and
 * every Cloudinary image answered by a painted SVG (a `c_crop` URL is answered with the
 * same picture cropped through its viewBox, so a look shows its real frame).
 *
 * Readings, after the approved demo (https://claude.ai/artifact/HCXPNZQ715Xgdzvdg8k2Fe):
 * the owner's plate and Gallery, hover words and tools, the cropper, details, the one
 * Delete and the Hide for character art, Add a look; a stranger's veil; a friend's plain
 * view; the lightbox; phone width.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4151');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const ENTRY_ID = 1;
const SHEET_ID = 20;
const CLOUD = 'https://res.cloudinary.com/arx/image/upload';

type Kind = 'figure' | 'face' | 'vista';
interface Art {
  id: number;
  kind: Kind;
  w: number;
  h: number;
  pal: [string, string, string, string];
}
const ART: Record<string, Art> = {
  coat: {
    id: 1,
    kind: 'figure',
    w: 600,
    h: 1050,
    pal: ['#3b2620', '#120c0a', '#4a4f57', '#c79a76'],
  },
  bargain: {
    id: 2,
    kind: 'face',
    w: 720,
    h: 720,
    pal: ['#5a3a24', '#26170f', '#2a1c18', '#c79a76'],
  },
  mourning: {
    id: 3,
    kind: 'figure',
    w: 600,
    h: 1050,
    pal: ['#26262c', '#0b0b0e', '#15151a', '#c79a76'],
  },
  furious: {
    id: 4,
    kind: 'face',
    w: 720,
    h: 720,
    pal: ['#6a1e18', '#220806', '#2a0e0c', '#c79a76'],
  },
  furious2: {
    id: 5,
    kind: 'face',
    w: 720,
    h: 720,
    pal: ['#2a1414', '#0c0404', '#1a0808', '#c79a76'],
  },
  stair: {
    id: 6,
    kind: 'vista',
    w: 1000,
    h: 620,
    pal: ['#e0a868', '#5a3a5a', '#3a2a3a', '#ffe0a0'],
  },
  lamps: {
    id: 7,
    kind: 'figure',
    w: 600,
    h: 1050,
    pal: ['#1e3a34', '#0a1614', '#2c5a50', '#c79a76'],
  },
  bath: {
    id: 8,
    kind: 'figure',
    w: 600,
    h: 1050,
    pal: ['#5a2a3a', '#1a0a10', '#7a3a4a', '#c79a76'],
  },
  commission: {
    id: 9,
    kind: 'figure',
    w: 600,
    h: 1050,
    pal: ['#2a2440', '#0c0a14', '#3a2a5a', '#e0c0a8'],
  },
};

/** A painted placeholder: a figure, a face, or a landscape. */
function paint(art: Art, viewBox?: string): string {
  const [a, b, cloth, skin] = art.pal;
  const { w, h } = art;
  let body = '';
  if (art.kind === 'figure') {
    const r = w * 0.085;
    body = `<path d="M${w / 2 - w * 0.13} ${h * 0.15 + r * 2.1} L${w / 2 + w * 0.13} ${h * 0.15 + r * 2.1} L${w / 2 + w * 0.3} ${h * 0.97} L${w / 2 - w * 0.3} ${h * 0.97}Z" fill="${cloth}"/><circle cx="${w / 2}" cy="${h * 0.15 + r * 0.3}" r="${r}" fill="${skin}"/><rect x="${w / 2 - r * 0.35}" y="${h * 0.15 + r}" width="${r * 0.7}" height="${r * 1.3}" fill="${skin}"/><path d="M${w / 2 - r * 1.05} ${h * 0.15 + r * 0.1} A${r * 1.05} ${r * 1.05} 0 0 1 ${w / 2 + r * 1.05} ${h * 0.15 + r * 0.1}Z" fill="#1a1416"/>`;
  } else if (art.kind === 'face') {
    const fr = w * 0.24;
    body = `<ellipse cx="${w / 2}" cy="${h * 1.02}" rx="${w * 0.46}" ry="${h * 0.3}" fill="${cloth}"/><rect x="${w / 2 - fr * 0.38}" y="${h * 0.42 + fr * 0.6}" width="${fr * 0.76}" height="${fr * 1.2}" fill="${skin}"/><ellipse cx="${w / 2}" cy="${h * 0.42}" rx="${fr * 0.86}" ry="${fr}" fill="${skin}"/><path d="M${w / 2 - fr * 0.95} ${h * 0.42 - fr * 0.42} A${fr * 0.95} ${fr * 0.66} 0 0 1 ${w / 2 + fr * 0.95} ${h * 0.42 - fr * 0.42}Z" fill="#1a1416"/><circle cx="${w / 2 - fr * 0.34}" cy="${h * 0.42}" r="${fr * 0.08}" fill="${cloth}"/><circle cx="${w / 2 + fr * 0.34}" cy="${h * 0.42}" r="${fr * 0.08}" fill="${cloth}"/>`;
  } else {
    body = `<circle cx="${w * 0.7}" cy="${h * 0.32}" r="${h * 0.12}" fill="${skin}" opacity="0.7"/><path d="M0 ${h * 0.62} Q${w * 0.3} ${h * 0.55} ${w * 0.6} ${h * 0.64} T${w} ${h * 0.6} L${w} ${h} L0 ${h}Z" fill="${cloth}"/><rect x="${w * 0.22}" y="${h * 0.34}" width="${w * 0.05}" height="${h * 0.4}" fill="${cloth}"/>`;
  }
  const vb = viewBox ?? `0 0 ${w} ${h}`;
  const [, , vw, vh] = vb.split(' ');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${vw}" height="${vh}" viewBox="${vb}" preserveAspectRatio="xMidYMid slice"><defs><linearGradient id="g" x1="0" y1="0" x2="0.3" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs><rect width="${w}" height="${h}" fill="url(#g)"/>${body}</svg>`;
}

const url = (name: string) => `${CLOUD}/v1/char_1/${name}.svg`;
const lookUrl = (name: string, x: number, y: number, width: number) =>
  `${CLOUD}/c_crop,x_${x},y_${y},w_${width},h_${Math.round((width * 5) / 4)}/v1/char_1/${name}.svg`;

interface Pic {
  name: string;
  title?: string;
  caption?: string;
  mood?: [number, string];
  crop?: [number, number, number];
  worn?: boolean;
  nsfw?: boolean;
  art?: boolean;
  hidden?: boolean;
  size?: number;
}
const PICS: Pic[] = [
  {
    name: 'coat',
    title: 'The counting-room coat',
    caption: 'Grey wool, the shop apron, the ring of keys.',
    mood: [1, 'At rest'],
    crop: [120, 30, 360],
    worn: true,
  },
  { name: 'bargain', title: 'A good bargain', mood: [2, 'Amused'], crop: [160, 40, 400] },
  {
    name: 'mourning',
    title: 'Mourning black',
    caption: 'Third week. She has not taken it off.',
    mood: [5, 'Grieving'],
    crop: [150, 40, 300],
  },
  { name: 'furious', mood: [4, 'Furious'], crop: [180, 60, 360] },
  { name: 'furious2', title: 'Cold, after', mood: [4, 'Furious'], crop: [150, 20, 420] },
  {
    name: 'stair',
    title: 'The Lower Stair at dusk',
    caption: 'Home, from the top step.',
    size: 2_516_582,
  },
  { name: 'lamps', title: 'Festival of Lamps', caption: 'Borrowed mask. Returned, eventually.' },
  {
    name: 'bath',
    title: 'After the bathhouse',
    caption: 'Commissioned. Not for the shop window.',
    nsfw: true,
  },
  { name: 'commission', art: true },
];

function gallery(viewer: 'owner' | 'stranger' | 'friend') {
  return PICS.filter((p) => viewer === 'owner' || !p.hidden).map((p, index) => {
    const art = ART[p.name];
    return {
      id: art.id,
      url: url(p.name),
      look_url: p.crop ? lookUrl(p.name, ...p.crop) : url(p.name),
      title: p.title ?? '',
      caption: p.caption ?? '',
      is_nsfw: Boolean(p.nsfw),
      width: art.w,
      height: art.h,
      file_size_bytes: p.size ?? 1_200_000,
      mood: p.mood?.[1] ?? '',
      mood_id: p.mood?.[0] ?? null,
      crop: p.crop ? { x: p.crop[0], y: p.crop[1], width: p.crop[2] } : null,
      sort_order: index,
      is_look: Boolean(p.crop),
      is_character_art: Boolean(p.art),
      is_worn: Boolean(p.worn),
      is_hidden: false,
      can_delete: viewer === 'owner' && !p.art,
      also_on: [],
    };
  });
}

function looks() {
  return PICS.filter((p) => p.crop)
    .map((p) => ({
      tenure_media_id: ART[p.name].id,
      url: lookUrl(p.name, ...(p.crop as [number, number, number])),
      title: p.title ?? '',
      look: p.mood?.[1] ?? '',
      is_current: Boolean(p.worn),
    }))
    .sort((x, y) => Number(y.is_current) - Number(x.is_current));
}

function accountPayload() {
  return {
    id: 1,
    username: 'walk-e2e',
    display_name: 'Walk E2E',
    email: '',
    email_verified: true,
    last_login: null,
    can_create_characters: true,
    is_staff: false,
    is_gm: false,
    available_characters: [],
    pending_applications: [],
    selected_entry_id: null,
    selected_entry: null,
  };
}

const MINE = {
  id: ENTRY_ID,
  name: 'Ilsavet du Verane',
  character_id: SHEET_ID,
  profile_picture_url: lookUrl('coat', 120, 30, 360),
  primary_persona_id: 9,
  active_persona_id: 9,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

const ENTRY = {
  id: ENTRY_ID,
  character: { id: SHEET_ID, name: 'Ilsavet du Verane' },
  profile_picture_url: lookUrl('coat', 120, 30, 360),
  tenures: [],
  can_apply: false,
  fullname: 'Ilsavet du Verane',
  quote: '',
  description: '',
  creation_provenance: 'player',
  creation_provenance_display: 'Player-created',
  created_for_table_name: null,
};

function sheetPayload(viewer: 'owner' | 'stranger' | 'friend') {
  const owner = viewer === 'owner';
  return {
    id: SHEET_ID,
    can_edit: owner,
    identity: {
      name: 'Ilsavet du Verane',
      fullname: 'Ilsavet du Verane',
      concept: "A pawnbroker's daughter who keeps other people's secrets like collateral.",
      quote: '',
      age: 27,
      birthday: null,
      chronological_age: null,
      biological_age: null,
      withered_years: null,
      gender: { id: 1, name: 'Woman' },
      pronouns: { subject: 'she', object: 'her', possessive: 'hers' },
      species: { id: 2, name: 'Human' },
      heritage: null,
      beginnings: [],
      family: null,
      tarot_card: null,
      origin: null,
      path: null,
      worship: null,
      worship_sincere: null,
      current_mood: null,
      vacancy: null,
    },
    appearance: {
      height_inches: null,
      height_band: 'Tall',
      build: null,
      description: '',
      form_traits: [],
    },
    stats: {},
    skills: [],
    path: null,
    distinctions: [],
    magic: null,
    story: { background: '', origin_story_state: 'NOT_STARTED', origin_slots: [] },
    actor_sheet: {
      never_do: '',
      protect: '',
      fear: '',
      enemy_public_line: '',
      enemy: null,
      introductions: [],
    },
    goals: [],
    beats: [],
    personas: [],
    theming: {},
    profile_picture: lookUrl('coat', 120, 30, 360),
    viewer_is_friend: viewer !== 'stranger',
    current_residence: null,
    looks: looks(),
    plate_ink: 'ember',
    worn: [],
    mentors: [],
    domains: [],
    keyring: [],
    standing: { memberships: [], reputations: [] },
    covenants: [],
    ties: [],
    ties_ap_this_week: owner ? 0 : null,
  };
}

const empty = { count: 0, next: null, previous: null, results: [] };

async function mockSheet(page: Page, viewer: 'owner' | 'stranger' | 'friend') {
  await page.route(`${CLOUD}/**`, async (route: Route) => {
    const href = route.request().url();
    const name = href.split('/').pop()?.replace('.svg', '') ?? '';
    const art = ART[name];
    if (!art) return route.fulfill({ status: 404 });
    const crop = href.match(/c_crop,x_(\d+),y_(\d+),w_(\d+),h_(\d+)/);
    const svg = paint(art, crop ? `${crop[1]} ${crop[2]} ${crop[3]} ${crop[4]}` : undefined);
    return route.fulfill({ contentType: 'image/svg+xml', body: svg });
  });
  await page.route('**/api/**', async (route: Route) => {
    const p = new URL(route.request().url()).pathname;
    if (p === '/api/user/') return route.fulfill({ json: accountPayload() });
    if (p === '/api/roster/entries/mine/')
      return route.fulfill({ json: viewer === 'owner' ? [MINE] : [] });
    if (p === `/api/roster/entries/${ENTRY_ID}/`) return route.fulfill({ json: ENTRY });
    if (p === `/api/character-sheets/${SHEET_ID}/`)
      return route.fulfill({ json: sheetPayload(viewer) });
    if (p === '/api/roster/tenure-media/usage/')
      return route.fulfill({ json: { used_bytes: 11_400_000, quota_bytes: 104_857_600 } });
    if (p === '/api/roster/tenure-media/')
      return route.fulfill({
        json: { count: PICS.length, next: null, previous: null, results: gallery(viewer) },
      });
    if (p === '/api/character-sheets/mood-options/') {
      const moods = ['At rest', 'Amused', 'Guarded', 'Furious', 'Grieving', 'Weary'];
      return route.fulfill({
        json: { ...empty, results: moods.map((name, i) => ({ id: i + 1, name })) },
      });
    }
    if (p === `/api/roster/kin/tree/${SHEET_ID}/`)
      return route.fulfill({ json: { family: null, nodes: [], parentage: [], unions: [] } });
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (p.startsWith('/api/vitals/'))
      return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    if (p === '/api/relationships/types/' || p === '/api/relationships/relationships/')
      return route.fulfill({ json: empty });
    if (
      p === '/api/personas/' ||
      p === '/api/journals/entries/' ||
      p === '/api/narrative/my-messages/'
    )
      return route.fulfill({ json: empty });
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

/** Dialogs open with a fade and zoom; screenshot them once it has finished. */
async function settled(page: Page) {
  await page.waitForFunction(() =>
    document.getAnimations().every((a) => a.playState !== 'running')
  );
}

async function openGallery(page: Page) {
  await page
    .getByRole('navigation', { name: 'Character sheet sections' })
    .getByRole('button', { name: 'Gallery' })
    .click();
  await expect(page.locator('.gallery-looks .gallery-pic')).toHaveCount(5);
}

test.describe('The Gallery (#4151) on the production bundle', () => {
  test('the owner: plate, looks strip with Add, and the Gallery', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, 'owner');
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    const strip = page.getByRole('group', { name: 'Looks and expressions' });
    await expect(strip.getByText('Furious 2')).toBeVisible();
    await expect(strip.getByRole('button', { name: 'Add a look' })).toBeVisible();
    await expect(page.getByText('Click a look to wear it.')).toHaveCount(0);
    await page.screenshot({ path: shot('01-owner-plate-1280.png') });
    await openGallery(page);
    await expect(page.getByText('9 pictures · 10.9 MB of 100.0 MB')).toBeVisible();
    await page.screenshot({ path: shot('02-owner-gallery-1280.png'), fullPage: true });
    await page.locator('.gallery-looks .gallery-pic').first().hover();
    await page.screenshot({ path: shot('03-owner-hover-look-1280.png'), fullPage: true });
    await page.locator('.gallery-viewer .gallery-pic').hover();
    await page.screenshot({ path: shot('04-owner-hover-picture-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('the owner: the cropper, details, Delete, Hide and Add a look', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, 'owner');
    await page.goto(`/characters/${ENTRY_ID}`);
    await openGallery(page);
    const first = page.locator('.gallery-looks .gallery-pic').first();
    await first.hover();
    await first.getByRole('button', { name: 'Adjust crop' }).click();
    await expect(page.locator('.gallery-cropper-box')).toBeVisible();
    await expect(page.locator('.gallery-cropper-handle')).toHaveCount(8);
    await settled(page);
    await page.screenshot({ path: shot('05-cropper-1280.png') });
    await page.keyboard.press('Escape');

    await first.hover();
    await first.getByRole('button', { name: 'Details' }).click();
    await expect(page.getByLabel('Title')).toHaveValue('The counting-room coat');
    await settled(page);
    await page.screenshot({ path: shot('06-details-1280.png') });
    await page.keyboard.press('Escape');

    const viewer = page.locator('.gallery-viewer .gallery-pic');
    await viewer.hover();
    await viewer.getByRole('button', { name: 'Delete' }).click();
    await expect(page.getByText('This frees 2.4 MB.')).toBeVisible();
    await settled(page);
    await page.screenshot({ path: shot('07-delete-confirm-1280.png') });
    await page.getByRole('button', { name: 'Cancel' }).click();

    // The character art is the last picture: step to it with the thumbnails.
    await page.locator('.gallery-thumb').last().click();
    await viewer.hover();
    await viewer.getByRole('button', { name: 'Hide' }).click();
    await expect(
      page.getByText('It stays on Ilsavet du Verane for whoever plays next.')
    ).toBeVisible();
    await settled(page);
    await page.screenshot({ path: shot('08-hide-confirm-1280.png') });
    await page.getByRole('button', { name: 'Cancel' }).click();

    await page.getByRole('button', { name: 'Add a look' }).click();
    await expect(page.getByRole('heading', { name: 'Add a look' })).toBeVisible();
    await settled(page);
    await page.screenshot({ path: shot('09-add-a-look-1280.png') });

    // Picking a picture opens the cropper for a new look, with "Show it on the sheet now".
    await page.locator('.gallery-pick button').first().click();
    await expect(page.getByLabel('Show it on the sheet now')).toBeChecked();
    await expect(page.getByRole('button', { name: 'Save profile picture' })).toBeVisible();
    await settled(page);
    await page.screenshot({ path: shot('09b-new-look-cropper-1280.png') });
  });

  test('a stranger: no tools, the NSFW picture veiled until clicked', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, 'stranger');
    await page.goto(`/characters/${ENTRY_ID}`);
    await openGallery(page);
    await expect(page.getByText('Drop pictures here, or click to choose')).toHaveCount(0);
    await page.locator('.gallery-thumb').nth(2).click();
    await expect(page.getByText('Click to reveal')).toBeVisible();
    await page.screenshot({ path: shot('10-stranger-veiled-1280.png'), fullPage: true });
    await page.getByRole('button', { name: 'Reveal NSFW picture' }).click();
    await expect(page.getByText('Click to reveal')).toHaveCount(0);
  });

  test('a friend: the NSFW picture plain', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, 'friend');
    await page.goto(`/characters/${ENTRY_ID}`);
    await openGallery(page);
    await page.locator('.gallery-thumb').nth(2).click();
    await expect(page.getByText('Click to reveal')).toHaveCount(0);
    await page.screenshot({ path: shot('11-friend-plain-1280.png'), fullPage: true });
  });

  test('the lightbox', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, 'stranger');
    await page.goto(`/characters/${ENTRY_ID}`);
    await openGallery(page);
    await page.getByRole('button', { name: 'Open The Lower Stair at dusk' }).click();
    await expect(
      page.locator('.gallery-lightbox-cap').getByText('Home, from the top step.')
    ).toBeVisible();
    await settled(page);
    await page.screenshot({ path: shot('12-lightbox-1280.png') });
  });

  test('at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockSheet(page, 'owner');
    await page.goto(`/characters/${ENTRY_ID}`);
    await openGallery(page);
    await page.screenshot({ path: shot('13-owner-gallery-390.png'), fullPage: true });
  });
});
