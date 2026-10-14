import { describe, expect, it } from 'vitest';

import { readComposerLine } from './composerLine';
import type { ComposerLineContext } from './composerLine';

const here: ComposerLineContext = {
  people: ['Nyx', 'Bob', 'Crucible Mundi', 'Éowyn', 'a hooded figure'],
  commandNames: ['look', 'who', 'sheet', 'friend', 'desc', 'set', 'name'],
};
const player: ComposerLineContext = { ...here, commandNames: ['look', 'who', 'sheet', 'friend'] };

describe('readComposerLine (#4346)', () => {
  describe('the slash', () => {
    it('reads / as the command after it', () => {
      expect(readComposerLine('/look', here)).toEqual({ kind: 'command', line: 'look' });
    });

    it('reads // as prose with one literal slash', () => {
      expect(readComposerLine('//shrugs', here)).toMatchObject({
        kind: 'prose',
        socketText: '/shrugs',
        spoken: '/shrugs',
      });
    });
  });

  describe('the plus', () => {
    it('reads +word as a command, sent as typed', () => {
      expect(readComposerLine('+friend Nyx', here)).toEqual({
        kind: 'command',
        line: '+friend Nyx',
      });
    });

    it('reads +word as a command even when the character lacks it, since + never addresses anyone', () => {
      expect(readComposerLine('+grievance', player)).toEqual({
        kind: 'command',
        line: '+grievance',
      });
    });

    it('reads + and a digit as prose', () => {
      expect(readComposerLine('+1 to that', here)).toMatchObject({
        kind: 'prose',
        spoken: '+1 to that',
      });
    });

    it('reads ++ as prose with one literal plus', () => {
      expect(readComposerLine('++friend is a word', here)).toMatchObject({
        kind: 'prose',
        socketText: '+friend is a word',
        spoken: '+friend is a word',
      });
    });

    it('reads a + with nothing after it as prose', () => {
      expect(readComposerLine('+ also this', here)).toMatchObject({ kind: 'prose' });
    });
  });

  describe('the at sign', () => {
    it('addresses someone here, in a target list', () => {
      expect(readComposerLine('@Nyx waves', here)).toEqual({
        kind: 'prose',
        socketText: '@Nyx waves',
        spoken: '@Nyx waves',
        targets: ['Nyx'],
        body: 'waves',
      });
    });

    it('addresses several people here', () => {
      expect(readComposerLine('@Nyx, @bob waves', here)).toMatchObject({
        kind: 'prose',
        targets: ['Nyx', 'bob'],
        body: 'waves',
      });
    });

    it('lets a person win over a command of the same name', () => {
      const lookAlike: ComposerLineContext = { ...here, people: ['Look'] };
      expect(readComposerLine('@Look over here', lookAlike)).toMatchObject({
        kind: 'prose',
        targets: ['Look'],
      });
    });

    it('matches any word of a name the room list shows, and Unicode names', () => {
      expect(readComposerLine('@Crucible nods', here)).toMatchObject({ targets: ['Crucible'] });
      expect(readComposerLine('@Crucible-Mundi nods', here)).toMatchObject({
        targets: ['Crucible-Mundi'],
      });
      expect(readComposerLine('@éowyn smiles', here)).toMatchObject({ targets: ['éowyn'] });
      expect(readComposerLine('@figure turns', here)).toMatchObject({ targets: ['figure'] });
    });

    it('reads @command as the command, sent as typed', () => {
      expect(readComposerLine('@desc here = A cold room', here)).toEqual({
        kind: 'command',
        line: '@desc here = A cold room',
      });
      expect(readComposerLine('@sheet', here)).toEqual({ kind: 'command', line: '@sheet' });
      expect(readComposerLine('@desc/edit here', here)).toEqual({
        kind: 'command',
        line: '@desc/edit here',
      });
    });

    it('holds an @ word that is neither someone here nor a command the character has', () => {
      expect(readComposerLine('@desc here = A cold room', player)).toEqual({
        kind: 'held',
        reason: 'Nobody called desc is here, and you have no desc command.',
        hint: 'Your draft is kept.',
        settled: true,
      });
    });

    it('holds a target list naming anyone who is not here', () => {
      expect(readComposerLine('@Nyx,@Gone,@Lost waves', here)).toEqual({
        kind: 'held',
        reason: 'Nobody called Gone or Lost is here.',
        hint: 'Your draft is kept.',
        settled: true,
      });
    });

    it('holds a list even when one of its names is a command', () => {
      expect(readComposerLine('@desc,@Nyx hi', here)).toMatchObject({
        kind: 'held',
        reason: 'Nobody called desc is here.',
      });
    });

    it('waits for a send before calling a lone unknown word at the end of the line settled', () => {
      expect(readComposerLine('@Ny', player)).toMatchObject({ kind: 'held', settled: false });
      expect(readComposerLine('@xyz/edit', player)).toMatchObject({ kind: 'held', settled: true });
    });

    it('reads a lone @person as prose, as the server does', () => {
      expect(readComposerLine('@Nyx', here)).toMatchObject({ kind: 'prose', targets: [] });
    });

    it('reads @@ as prose with one literal at sign, kept doubled for the server parser', () => {
      expect(readComposerLine('@@everyone gets a drink', here)).toEqual({
        kind: 'prose',
        socketText: '@@everyone gets a drink',
        spoken: '@everyone gets a drink',
        targets: [],
        body: '@everyone gets a drink',
      });
    });

    it('reads an @ followed by a space as prose', () => {
      expect(readComposerLine('@ the docks', here)).toMatchObject({ kind: 'prose' });
    });
  });

  it('reads any other line as prose', () => {
    expect(readComposerLine('look', here)).toEqual({
      kind: 'prose',
      socketText: 'look',
      spoken: 'look',
      targets: [],
      body: 'look',
    });
  });
});
