import {
  daysInMonth,
  describeJump,
  isValidGameDate,
  minutesBetween,
  speedInWords,
  toIso,
} from '../clockDate';

const at = (year: number, month = 1, day = 1, hour = 0, minute = 0) => ({
  year,
  month,
  day,
  hour,
  minute,
});

const YEARS = { min: 100, max: 9000 };

describe('clockDate', () => {
  it('writes a four-digit year and UTC, for a year far below 1000 too', () => {
    expect(toIso(at(1020, 1, 1))).toBe('1020-01-01T00:00:00Z');
    expect(toIso(at(50, 3, 9, 16, 20))).toBe('0050-03-09T16:20:00Z');
  });

  it('knows the month lengths and the leap years of the calendar the game uses', () => {
    expect(daysInMonth(1000, 2)).toBe(28);
    expect(daysInMonth(1004, 2)).toBe(29);
    expect(daysInMonth(1100, 2)).toBe(28);
    expect(daysInMonth(1200, 2)).toBe(29);
    expect(daysInMonth(1000, 4)).toBe(30);
  });

  it('refuses a date that does not exist', () => {
    expect(isValidGameDate(at(1000, 2, 30), YEARS)).toBe(false);
    expect(isValidGameDate(at(1000, 13, 1), YEARS)).toBe(false);
    expect(isValidGameDate(at(99, 1, 1), YEARS)).toBe(false);
    expect(isValidGameDate(at(9001, 1, 1), YEARS)).toBe(false);
    expect(isValidGameDate(at(Number.NaN, 1, 1), YEARS)).toBe(false);
    expect(isValidGameDate(at(1000, 1, 1, 24), YEARS)).toBe(false);
    expect(isValidGameDate(at(1004, 2, 29), YEARS)).toBe(true);
  });

  it('counts the minutes between two dates across years', () => {
    expect(minutesBetween(at(1000, 1, 1), at(1000, 1, 2))).toBe(1440);
    expect(minutesBetween(at(1000, 1, 1), at(1001, 1, 1))).toBe(365 * 1440);
    expect(minutesBetween(at(1004, 1, 1), at(1005, 1, 1))).toBe(366 * 1440);
    expect(minutesBetween(at(1000, 1, 2), at(1000, 1, 1))).toBe(-1440);
  });

  it('names a jump by its largest whole unit and its direction', () => {
    expect(describeJump(at(1000, 3, 9), at(1020, 3, 9))).toBe('20 years forward');
    expect(describeJump(at(1000, 3, 9), at(1020, 1, 1))).toBe('19 years forward');
    expect(describeJump(at(1020, 5, 4), at(1000, 5, 4))).toBe('20 years back');
    expect(describeJump(at(1000, 1, 1), at(1000, 4, 1))).toBe('3 months forward');
    expect(describeJump(at(1000, 1, 1), at(1000, 1, 6))).toBe('5 days forward');
    expect(describeJump(at(1000, 1, 1, 6), at(1000, 1, 1, 5))).toBe('1 hour back');
    expect(describeJump(at(1000, 1, 1), at(1001, 1, 1))).toBe('1 year forward');
    expect(describeJump(at(1000, 1, 1), at(1000, 1, 1))).toBeNull();
  });

  it('says the speed in days', () => {
    expect(speedInWords(3)).toBe('3 game days pass for each real day');
    expect(speedInWords(1)).toBe('1 game day passes for each real day');
    expect(speedInWords(1.5)).toBe('1.5 game days pass for each real day');
  });
});
