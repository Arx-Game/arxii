/**
 * Routing rule text (#3563): the one formatter behind the DAG edge label,
 * the DAG hover text and the author tree's transition row.
 */
import type { TransitionRoutingRule } from './types';

export function formatRoutingRule(rule: TransitionRoutingRule): string {
  if (rule.stake != null) {
    const subject = rule.stake_summary || `stake #${rule.stake}`;
    return `${subject} = ${String(rule.required_stake_column ?? '').toUpperCase()}`;
  }
  const subject = rule.beat_title || `beat #${rule.beat}`;
  const key = rule.required_outcome_key ? ` (${rule.required_outcome_key})` : '';
  return `${subject} = ${String(rule.required_outcome ?? '').toUpperCase()}${key}`;
}

export function formatRoutingRules(rules: readonly TransitionRoutingRule[] | undefined): string {
  return (rules ?? []).map(formatRoutingRule).join(' · ');
}
