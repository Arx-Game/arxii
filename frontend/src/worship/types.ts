/**
 * Worship API shapes (#3779): a character's prayers and the visions sent to them.
 * Mirrors `world.worship.serializers` through the generated schema.
 */

import type { components } from '@/generated/api';

export type Prayer = components['schemas']['Prayer'];
export type Vision = components['schemas']['Vision'];
export type VisionCreate = components['schemas']['VisionCreateRequest'];
