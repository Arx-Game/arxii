import { beforeEach, describe, expect, it } from 'vitest';
import { clearAccountPlayStorage } from './playStorage';

describe('account play storage cleanup', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('clears only the selected account rows when switching accounts', () => {
    localStorage.setItem('arx:play-preferences:v2:account:1', 'one');
    localStorage.setItem('arx:play-preferences:v2:account:2', 'two');
    localStorage.setItem('arx:play-anchors:v2:account:1', 'one');
    localStorage.setItem('arx:threadTabs:v2:account:1:Aria:7', 'one');
    sessionStorage.setItem('arx:play-draft:v2:1:9:room:7', 'one');
    sessionStorage.setItem('arx:play-draft:v2:2:9:room:7', 'two');

    clearAccountPlayStorage(1);

    expect(localStorage.getItem('arx:play-preferences:v2:account:1')).toBeNull();
    expect(localStorage.getItem('arx:play-anchors:v2:account:1')).toBeNull();
    expect(localStorage.getItem('arx:threadTabs:v2:account:1:Aria:7')).toBeNull();
    expect(sessionStorage.getItem('arx:play-draft:v2:1:9:room:7')).toBeNull();
    expect(localStorage.getItem('arx:play-preferences:v2:account:2')).toBe('two');
    expect(sessionStorage.getItem('arx:play-draft:v2:2:9:room:7')).toBe('two');
  });

  it('clears all account-scoped play rows on logout without touching unscoped legacy data', () => {
    localStorage.setItem('arx:play-preferences:v2:account:1', 'one');
    localStorage.setItem('arx:play-anchors:v2:account:2', 'two');
    localStorage.setItem('arx:play-preferences:v1', 'legacy');
    sessionStorage.setItem('arx:play-draft:v2:1:9:room:7', 'one');

    clearAccountPlayStorage();

    expect(localStorage.getItem('arx:play-preferences:v2:account:1')).toBeNull();
    expect(localStorage.getItem('arx:play-anchors:v2:account:2')).toBeNull();
    expect(sessionStorage.getItem('arx:play-draft:v2:1:9:room:7')).toBeNull();
    expect(localStorage.getItem('arx:play-preferences:v1')).toBe('legacy');
  });
});
