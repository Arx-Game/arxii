/**
 * Block/Mute REST calls (#1278). Mirrors the narrative story-mute pattern: thin apiFetch
 * wrappers over /api/blocks/ and /api/mutes/.
 */
import { apiFetch } from '@/evennia_replacements/api';

import type {
  Block,
  BlockCreateRequest,
  Mute,
  MuteCreateRequest,
  PaginatedBlockList,
  PaginatedMuteList,
} from './types';

export async function listBlocks(): Promise<PaginatedBlockList> {
  const res = await apiFetch('/api/blocks/');
  if (!res.ok) {
    throw new Error('Failed to load blocks');
  }
  return res.json() as Promise<PaginatedBlockList>;
}

export async function createBlock(data: BlockCreateRequest): Promise<Block> {
  const res = await apiFetch('/api/blocks/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = new Error('Failed to block') as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<Block>;
}

/** DELETE = cron-delayed unblock (the block stays active until the next sweep); returns 200. */
export async function unblock(id: number): Promise<void> {
  const res = await apiFetch(`/api/blocks/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to unblock');
  }
}

export async function shareBlock(id: number): Promise<Block> {
  const res = await apiFetch(`/api/blocks/${id}/share/`, { method: 'POST' });
  if (!res.ok) {
    throw new Error('Failed to share block');
  }
  return res.json() as Promise<Block>;
}

export async function listMutes(): Promise<PaginatedMuteList> {
  const res = await apiFetch('/api/mutes/');
  if (!res.ok) {
    throw new Error('Failed to load mutes');
  }
  return res.json() as Promise<PaginatedMuteList>;
}

export async function createMute(data: MuteCreateRequest): Promise<Mute> {
  const res = await apiFetch('/api/mutes/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    throw new Error('Failed to mute');
  }
  return res.json() as Promise<Mute>;
}

export async function unmute(id: number): Promise<void> {
  const res = await apiFetch(`/api/mutes/${id}/`, { method: 'DELETE' });
  if (!res.ok) {
    throw new Error('Failed to unmute');
  }
}
