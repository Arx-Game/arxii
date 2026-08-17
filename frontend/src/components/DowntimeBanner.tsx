/**
 * DowntimeBanner — site-wide notice for the next planned downtime (#3194).
 * Mounted globally in Layout, anonymous-safe (the endpoint is public), and
 * polled so a window scheduled while the page sits open still shows up —
 * a connected player never reloads. Covers both staff-declared maintenance
 * windows and the host's own scheduled security reboot, which the backend
 * derives from systemd rather than requiring anyone to type it.
 */

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';

interface PlannedDowntime {
  source: 'staff' | 'system';
  starts_at: string;
  expected_duration_minutes: number;
  message: string;
}

const POLL_MS = 5 * 60 * 1000;
/** Only warn when the window is near enough to matter to the current session. */
const LEAD_MS = 24 * 60 * 60 * 1000;

async function fetchNextDowntime(): Promise<PlannedDowntime | null> {
  const res = await apiFetch('/api/downtime/next/');
  if (!res.ok) {
    // The banner is best-effort chrome; a failed poll must never break the page.
    return null;
  }
  const data = await res.json().catch(() => null);
  return data?.downtime ?? null;
}

function describe(downtime: PlannedDowntime): string {
  const starts = new Date(downtime.starts_at);
  const now = Date.now();
  const when = starts.toLocaleString(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  });
  const duration = `~${downtime.expected_duration_minutes} min`;
  if (starts.getTime() <= now) {
    return `Maintenance in progress (${duration}): ${downtime.message}`;
  }
  return `Scheduled downtime ${when} (${duration}): ${downtime.message}`;
}

export function DowntimeBanner() {
  const { data } = useQuery({
    queryKey: ['downtime', 'next'],
    queryFn: fetchNextDowntime,
    refetchInterval: POLL_MS,
    staleTime: POLL_MS,
  });

  if (!data) {
    return <div data-testid="downtime-banner-empty" hidden />;
  }

  const startsMs = new Date(data.starts_at).getTime();
  if (startsMs - Date.now() > LEAD_MS) {
    return <div data-testid="downtime-banner-empty" hidden />;
  }

  return (
    <div
      data-testid="downtime-banner"
      role="alert"
      className="border-b border-sky-500/40 bg-sky-950/30 px-4 py-2 text-center text-sm text-sky-200"
    >
      {describe(data)}
    </div>
  );
}
