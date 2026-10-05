/**
 * The Gallery tab (#4151), mounted for real with only the network stubbed.
 *
 * What it pins is who sees what: the owner gets the drop zone, the hover tools and the
 * storage line; a stranger gets NSFW pictures veiled and no tools; a friend sees every
 * picture plain. And the one Delete says what it will do.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { GalleryPicture } from '@/roster/gallery';
import { GalleryPanel } from '../GalleryPanel';

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/evennia_replacements/api', () => ({ apiFetch }));

function picture(overrides: Partial<GalleryPicture>): GalleryPicture {
  return {
    id: 1,
    url: 'https://res.cloudinary.com/x/image/upload/a.jpg',
    look_url: null,
    title: '',
    caption: '',
    is_nsfw: false,
    width: 600,
    height: 1000,
    file_size_bytes: 2 * 1024 * 1024,
    mood: '',
    mood_id: null,
    crop: null,
    sort_order: 0,
    is_look: false,
    is_character_art: false,
    is_worn: false,
    is_hidden: false,
    can_delete: false,
    also_on: [],
    ...overrides,
  };
}

const LOOK = picture({
  id: 1,
  title: 'The counting-room coat',
  caption: 'Grey wool and the shop apron.',
  is_look: true,
  is_worn: true,
  crop: { x: 0, y: 0, width: 400 },
  look_url: 'https://res.cloudinary.com/x/image/upload/c_crop,x_0,y_0,w_400,h_500/a.jpg',
  mood: 'At rest',
  mood_id: 3,
});
const PLAIN = picture({ id: 2, title: 'The Lower Stair at dusk', sort_order: 1 });
const NSFW = picture({ id: 3, title: 'After the bathhouse', is_nsfw: true, sort_order: 2 });
const ART = picture({ id: 4, is_character_art: true, sort_order: 3 });

function respond(body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
}

function stubNetwork(pictures: GalleryPicture[], owner: boolean) {
  apiFetch.mockImplementation((url: string) => {
    if (url.startsWith('/api/roster/tenure-media/usage/')) {
      return respond({ used_bytes: 5 * 1024 * 1024, quota_bytes: 100 * 1024 * 1024 });
    }
    if (url.startsWith('/api/roster/tenure-media/?roster_entry=')) {
      return respond({
        next: null,
        results: pictures.map((p) => ({ ...p, can_delete: owner && !p.is_character_art })),
      });
    }
    if (url.startsWith('/api/character-sheets/mood-options/')) {
      return respond({ next: null, results: [{ id: 3, name: 'At rest' }] });
    }
    if (url === '/api/roster/tenure-media/2/') return respond({ outcome: 'deleted' });
    return respond({});
  });
}

function mount(props: { canManage: boolean; isOwner: boolean; viewerIsFriend: boolean }) {
  return renderWithProviders(
    <GalleryPanel entryId={7} sheetId={70} characterName="Ilsavet" ink="ember" {...props} />
  );
}

describe('GalleryPanel', () => {
  beforeEach(() => {
    apiFetch.mockReset();
  });

  it('gives the owner the drop zone, tools and their storage', async () => {
    stubNetwork([LOOK, PLAIN], true);
    mount({ canManage: true, isOwner: true, viewerIsFriend: true });
    expect(await screen.findByText('Drop pictures here, or click to choose')).toBeInTheDocument();
    expect(screen.getByText(/2 pictures · 5\.0 MB of 100\.0 MB/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Adjust crop' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Make profile picture' })).toBeInTheDocument();
  });

  it('shows the look at its crop and the plain picture whole', async () => {
    stubNetwork([LOOK, PLAIN], false);
    const { container } = mount({ canManage: false, isOwner: false, viewerIsFriend: false });
    await screen.findByRole('button', { name: 'Open The counting-room coat' });
    const srcs = Array.from(container.querySelectorAll('.gallery-pic img')).map((img) =>
      img.getAttribute('src')
    );
    expect(srcs).toContain(LOOK.look_url);
    expect(srcs).toContain(PLAIN.url);
  });

  it('shows a title and caption only where they were written', async () => {
    stubNetwork([LOOK, ART], false);
    const { container } = mount({ canManage: false, isOwner: false, viewerIsFriend: false });
    await screen.findByText('The counting-room coat');
    expect(screen.getByText('Grey wool and the shop apron.')).toBeInTheDocument();
    const artTile = container.querySelector('[data-picture="4"]');
    expect(artTile?.querySelector('.gallery-cap')).toBeNull();
  });

  it('gives a stranger no tools and veils NSFW until clicked', async () => {
    stubNetwork([NSFW], false);
    mount({ canManage: false, isOwner: false, viewerIsFriend: false });
    const reveal = await screen.findByRole('button', { name: 'Reveal NSFW picture' });
    expect(screen.queryByText('Drop pictures here, or click to choose')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Details' })).toBeNull();
    fireEvent.click(reveal);
    expect(
      await screen.findByRole('button', { name: 'Open After the bathhouse' })
    ).toBeInTheDocument();
  });

  it('shows a friend NSFW pictures plain', async () => {
    stubNetwork([NSFW], false);
    mount({ canManage: false, isOwner: false, viewerIsFriend: true });
    expect(
      await screen.findByRole('button', { name: 'Open After the bathhouse' })
    ).toBeInTheDocument();
    expect(screen.queryByText('Click to reveal')).toBeNull();
  });

  it('confirms a Delete in terms of the space it frees', async () => {
    stubNetwork([PLAIN], true);
    mount({ canManage: true, isOwner: true, viewerIsFriend: true });
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText('This frees 2.0 MB.')).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        '/api/roster/tenure-media/2/',
        expect.objectContaining({ method: 'DELETE' })
      )
    );
  });

  it('offers to hide character art, never to delete it', async () => {
    stubNetwork([ART], true);
    mount({ canManage: true, isOwner: true, viewerIsFriend: true });
    fireEvent.click(await screen.findByRole('button', { name: 'Hide' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(
      within(dialog).getByText('It stays on Ilsavet for whoever plays next.')
    ).toBeInTheDocument();
    expect(within(dialog).queryByRole('button', { name: 'Delete' })).toBeNull();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Hide' }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        '/api/roster/tenure-media/4/hide/',
        expect.objectContaining({ method: 'POST' })
      )
    );
  });
});
