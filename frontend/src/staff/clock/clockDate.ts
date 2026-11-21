/**
 * Game-date arithmetic for the staff Game clock page (#5248).
 *
 * The game's calendar has the real calendar's shape (twelve months, the same month
 * lengths and leap years) with its own month names and its own years, which may be far
 * below 100. A JavaScript `Date` maps years 0 to 99 onto the 1900s and applies the
 * browser's time zone, so nothing here goes through one: dates are plain fields, read
 * from and written to ISO text by hand.
 */

export interface GameDate {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

export const MIN_YEAR = 1;
export const MAX_YEAR = 9999;

function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

const MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

export function daysInMonth(year: number, month: number): number {
  if (month === 2 && isLeapYear(year)) return 29;
  return MONTH_LENGTHS[month - 1] ?? 31;
}

function pad(value: number, width: number): string {
  return String(value).padStart(width, '0');
}

/** `1020-01-01T00:00:00Z`: the form the clock API reads, always in UTC. */
export function toIso(date: GameDate): string {
  return (
    `${pad(date.year, 4)}-${pad(date.month, 2)}-${pad(date.day, 2)}` +
    `T${pad(date.hour, 2)}:${pad(date.minute, 2)}:00Z`
  );
}

/** The fields of a game date as the clock read gives them. */
export function gameDateOf(clock: {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}): GameDate {
  return {
    year: clock.year,
    month: clock.month,
    day: clock.day,
    hour: clock.hour,
    minute: clock.minute,
  };
}

export function isValidGameDate(date: GameDate): boolean {
  const whole = [date.year, date.month, date.day, date.hour, date.minute].every(Number.isInteger);
  return (
    whole &&
    date.year >= MIN_YEAR &&
    date.year <= MAX_YEAR &&
    date.month >= 1 &&
    date.month <= 12 &&
    date.day >= 1 &&
    date.day <= daysInMonth(date.year, date.month) &&
    date.hour >= 0 &&
    date.hour <= 23 &&
    date.minute >= 0 &&
    date.minute <= 59
  );
}

/** Days since a fixed day zero, for the proleptic Gregorian calendar the game uses. */
function dayNumber(year: number, month: number, day: number): number {
  const y = month <= 2 ? year - 1 : year;
  const era = Math.floor(y / 400);
  const yearOfEra = y - era * 400;
  const dayOfYear = Math.floor((153 * (month + (month > 2 ? -3 : 9)) + 2) / 5) + day - 1;
  const dayOfEra =
    yearOfEra * 365 + Math.floor(yearOfEra / 4) - Math.floor(yearOfEra / 100) + dayOfYear;
  return era * 146097 + dayOfEra;
}

/** Minutes from `from` to `to`; negative when `to` is earlier. */
export function minutesBetween(from: GameDate, to: GameDate): number {
  const days = dayNumber(to.year, to.month, to.day) - dayNumber(from.year, from.month, from.day);
  return days * 1440 + (to.hour - from.hour) * 60 + (to.minute - from.minute);
}

function plural(count: number, unit: string): string {
  return `${count} ${unit}${count === 1 ? '' : 's'}`;
}

/** Whole calendar years from the earlier date to the later one. */
function wholeYears(earlier: GameDate, later: GameDate): number {
  const laterRest = [later.month, later.day, later.hour, later.minute];
  const earlierRest = [earlier.month, earlier.day, earlier.hour, earlier.minute];
  let years = later.year - earlier.year;
  for (let index = 0; index < laterRest.length; index += 1) {
    if (laterRest[index] !== earlierRest[index]) {
      if (laterRest[index] < earlierRest[index]) years -= 1;
      break;
    }
  }
  return years;
}

const MINUTES_PER_HOUR = 60;
const MINUTES_PER_DAY = 1440;
const DAYS_PER_MONTH = 30;

/**
 * The length of a jump in its largest whole unit, with its direction: "20 years forward",
 * "3 months back", "5 hours forward". Null when the two dates are the same minute.
 */
export function describeJump(from: GameDate, to: GameDate): string | null {
  const minutes = minutesBetween(from, to);
  if (minutes === 0) return null;
  const direction = minutes > 0 ? 'forward' : 'back';
  const [earlier, later] = minutes > 0 ? [from, to] : [to, from];
  const size = Math.abs(minutes);
  const years = wholeYears(earlier, later);
  let length: string;
  if (years >= 1) {
    length = plural(years, 'year');
  } else if (size >= MINUTES_PER_DAY * DAYS_PER_MONTH) {
    length = plural(Math.floor(size / (MINUTES_PER_DAY * DAYS_PER_MONTH)), 'month');
  } else if (size >= MINUTES_PER_DAY) {
    length = plural(Math.floor(size / MINUTES_PER_DAY), 'day');
  } else if (size >= MINUTES_PER_HOUR) {
    length = plural(Math.floor(size / MINUTES_PER_HOUR), 'hour');
  } else {
    length = plural(size, 'minute');
  }
  return `${length} ${direction}`;
}

/** "3" for 3.0, "1.5" for 1.5: a ratio without a trailing ".0". */
export function formatRatio(ratio: number): string {
  return String(Number(ratio.toFixed(2)));
}

/** "3 game days pass for each real day"; the ratio is game seconds per real second. */
export function speedInWords(ratio: number): string {
  const days = formatRatio(ratio);
  return `${days} game ${days === '1' ? 'day passes' : 'days pass'} for each real day`;
}

/** "16:20". */
export function clockTime(hour: number, minute: number): string {
  return `${pad(hour, 2)}:${pad(minute, 2)}`;
}
