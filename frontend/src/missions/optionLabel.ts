import type { MissionOption } from './types';

/** Same rule as `option_label` in the server's graph check. */
export function optionLabel(
  opt: Pick<MissionOption, 'key' | 'authored_ic_framing' | 'order'>
): string {
  if (opt.key) return opt.key;
  const framing = opt.authored_ic_framing ?? '';
  if (framing) return framing.slice(0, 40);
  return `option ${opt.order}`;
}
