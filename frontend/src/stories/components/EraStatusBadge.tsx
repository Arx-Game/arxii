/**
 * EraStatusBadge — colored badge for era lifecycle status.
 *
 * CONCLUDED → gray
 * ACTIVE → green
 * UPCOMING → amber
 */

import type { EraStatus } from '../types';

interface EraStatusBadgeProps {
  status: EraStatus;
}

const ERA_STATUS_CONFIG: Record<EraStatus, { label: string; className: string }> = {
  concluded: {
    label: 'Concluded',
    className: 'bg-gray-100 text-gray-700 border-gray-300',
  },
  active: {
    label: 'Active',
    className: 'bg-green-100 text-green-800 border-green-300',
  },
  upcoming: {
    label: 'Upcoming',
    className: 'bg-amber-100 text-amber-800 border-amber-300',
  },
};

export function EraStatusBadge({ status }: EraStatusBadgeProps) {
  const config = ERA_STATUS_CONFIG[status] ?? ERA_STATUS_CONFIG.upcoming;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${config.className}`}
    >
      {config.label}
    </span>
  );
}
