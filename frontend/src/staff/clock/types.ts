import type { components } from '@/generated/api';

export type { ClockState } from '@/home/hall/types';

/** `GET /api/clock/adjust-preview/`: what setting a date would do, before it is set. */
export type ClockJumpPreview = components['schemas']['ClockJumpPreview'];

/** One row of `GET /api/clock/history/`. */
export type ClockHistoryRow = components['schemas']['ClockHistory'];

export type AgeHandling = components['schemas']['AgeHandlingEnum'];
