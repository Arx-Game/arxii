/**
 * The spelling two facet names share when they mean one facet (#4197).
 *
 * Mirrors `world.magic.services.facets.facet_key` so a picker can tell "Scythes" from
 * a new word before it asks the server: casefold, letters and spaces only, one space
 * between words, the last word singular. The server's answer is still the truth; this
 * only decides what the picker shows while you type.
 */
export function facetKey(name: string): string {
  const lowered = name
    .toLowerCase()
    .replace(/-/g, ' ')
    .replace(/[^a-z ]+/g, ' ');
  const words = lowered.replace(/ +/g, ' ').trim().split(' ').filter(Boolean);
  if (words.length > 0) words[words.length - 1] = singular(words[words.length - 1]);
  return words.join(' ');
}

const SHORTEST_IES_PLURAL = 5;
const SHORTEST_ES_PLURAL = 5;
const SHORTEST_S_PLURAL = 4;

function singular(word: string): string {
  if (word.length >= SHORTEST_IES_PLURAL && word.endsWith('ies')) return `${word.slice(0, -3)}y`;
  if (word.length >= SHORTEST_ES_PLURAL && /(ches|shes|sses|xes)$/.test(word)) {
    return word.slice(0, -2);
  }
  if (word.length >= SHORTEST_S_PLURAL && word.endsWith('s') && !word.endsWith('ss')) {
    return word.slice(0, -1);
  }
  return word;
}
