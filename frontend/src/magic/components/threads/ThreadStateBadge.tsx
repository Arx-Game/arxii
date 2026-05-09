type ThreadState = 'ready' | 'near_xp_lock' | 'blocked' | 'normal';

interface ThreadStateBadgeProps {
  state: ThreadState;
}

const STATE_CONFIG: Record<
  ThreadState,
  { dotClass: string; label: string; containerClass: string }
> = {
  ready: {
    dotClass: 'bg-green-500',
    label: 'Ready',
    containerClass: 'text-green-700 dark:text-green-400',
  },
  near_xp_lock: {
    dotClass: 'bg-yellow-400',
    label: 'Near XP Lock',
    containerClass: 'text-yellow-700 dark:text-yellow-400',
  },
  blocked: {
    dotClass: 'bg-red-500',
    label: 'Blocked',
    containerClass: 'text-red-700 dark:text-red-400',
  },
  normal: {
    dotClass: 'bg-muted-foreground',
    label: 'Normal',
    containerClass: 'text-muted-foreground',
  },
};

/**
 * Small colored dot + label indicating thread prospect state.
 * Pure presentational — no data fetching.
 */
export function ThreadStateBadge({ state }: ThreadStateBadgeProps) {
  const config = STATE_CONFIG[state];

  return (
    <span
      className={`inline-flex items-center gap-1 text-xs font-medium ${config.containerClass}`}
      data-testid={`thread-state-badge-${state}`}
    >
      <span className={`inline-block h-2 w-2 rounded-full ${config.dotClass}`} aria-hidden="true" />
      {config.label}
    </span>
  );
}
