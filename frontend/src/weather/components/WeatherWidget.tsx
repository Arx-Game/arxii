/**
 * Ambient IC time + local weather readout (#1522).
 *
 * The web face of the `time`/`weather` command: a compact glance at what time it is and what the
 * weather is doing where the active character stands. Reads the current room from Redux and queries
 * `/api/weather/conditions/`. Renders nothing until there's something to show.
 */

import { useAppSelector } from '@/store/hooks';

import { useWeatherConditions } from '../queries';

function titleCase(value: string | null | undefined): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : '';
}

function timeOfDay(isoTime: string | null | undefined): string {
  if (!isoTime) return '';
  const date = new Date(isoTime);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function WeatherWidget() {
  const { sessions, active } = useAppSelector((state) => state.game);
  const roomId = active ? (sessions[active]?.room?.id ?? null) : null;
  const { data } = useWeatherConditions(roomId);

  if (!data) return null;

  const phase = titleCase(data.phase);
  const season = titleCase(data.season);
  const clock = timeOfDay(data.ic_time);
  const timeLabel = [phase, clock].filter(Boolean).join(' ');

  // Nothing resolved (no clock and no weather) → don't clutter the bar.
  if (!timeLabel && !data.weather_type) return null;

  const tooltip = [
    timeLabel && season ? `${timeLabel} in ${season}` : timeLabel,
    data.weather_type ?? '',
    data.emit_text ?? '',
  ]
    .filter(Boolean)
    .join(' — ');

  return (
    <div
      className="flex items-center gap-1 text-xs text-muted-foreground"
      title={tooltip || undefined}
      aria-label="Local time and weather"
    >
      {timeLabel && <span>{timeLabel}</span>}
      {data.weather_type && (
        <>
          {timeLabel && <span aria-hidden>·</span>}
          <span className="text-foreground">{data.weather_type}</span>
        </>
      )}
    </div>
  );
}
