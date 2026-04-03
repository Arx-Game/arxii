import { useState } from 'react';
import { Swords, ChevronDown, ChevronUp } from 'lucide-react';
import type { ActionResultData } from '../actionTypes';

interface Props {
  content: string;
  actionKey?: string;
  techniqueName?: string;
  outcome?: string;
  result?: ActionResultData;
}

interface ParsedAction {
  actionName: string;
  techniqueName: string | null;
  outcomeName: string | null;
  consequenceLabel: string | null;
  rawContent: string;
}

/**
 * Parse the backend content format:
 * "[ActionKey] using TechniqueName -- OutcomeName (ConsequenceLabel)"
 */
function parseActionContent(content: string): ParsedAction {
  const pattern = /^\[([^\]]+)\](?:\s+using\s+(.+?))?\s*(?:--\s*(.+?))?(?:\s*\(([^)]+)\))?\s*$/;
  const match = content.match(pattern);

  if (match) {
    return {
      actionName: match[1],
      techniqueName: match[2] || null,
      outcomeName: match[3]?.trim() || null,
      consequenceLabel: match[4] || null,
      rawContent: content,
    };
  }

  return {
    actionName: 'Action',
    techniqueName: null,
    outcomeName: null,
    consequenceLabel: null,
    rawContent: content,
  };
}

function getOutcomeColor(outcome: string | null | undefined): string {
  if (!outcome) return 'border-l-blue-500';
  const lower = outcome.toLowerCase();
  if (lower.includes('success') || lower.includes('triumph')) return 'border-l-green-500';
  if (lower.includes('fail') || lower.includes('disaster')) return 'border-l-red-500';
  if (lower.includes('partial') || lower.includes('mixed')) return 'border-l-yellow-500';
  return 'border-l-blue-500';
}

function getOutcomeTextColor(outcome: string | null | undefined): string {
  if (!outcome) return '';
  const lower = outcome.toLowerCase();
  if (lower.includes('success') || lower.includes('triumph')) return 'text-green-400';
  if (lower.includes('fail') || lower.includes('disaster')) return 'text-red-400';
  if (lower.includes('partial') || lower.includes('mixed')) return 'text-yellow-400';
  return '';
}

export function ActionResult({ content, actionKey, techniqueName, outcome, result }: Props) {
  const [expanded, setExpanded] = useState(false);

  // Structured data path — used when the backend returns full resolution data
  if (result?.action_resolution) {
    const checkOutcome = result.action_resolution.main_result?.check_outcome ?? null;
    const borderColor = getOutcomeColor(checkOutcome);
    const outcomeTextColor = getOutcomeTextColor(checkOutcome);
    const techniqueInfo = result.technique_result;
    const displayAction = result.action_key ?? 'Action';
    const displayTechnique = result.technique_name;

    return (
      <div className={`rounded-md border-l-4 ${borderColor} bg-muted/30 px-4 py-3`}>
        <div className="flex items-start gap-2">
          <Swords className="mt-0.5 h-4 w-4 shrink-0 text-purple-500" />
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">{displayAction}</span>
              {displayTechnique && (
                <span className="text-xs text-muted-foreground">using {displayTechnique}</span>
              )}
              {checkOutcome && (
                <span className={`text-sm font-medium ${outcomeTextColor}`}>{checkOutcome}</span>
              )}
            </div>

            {techniqueInfo && (
              <div className="mt-1 text-sm text-gray-400">
                <span>{techniqueInfo.anima_spent} anima spent</span>
                {techniqueInfo.soulfray_stage && (
                  <span className="ml-2 text-amber-400">
                    Soulfray: {techniqueInfo.soulfray_stage}
                  </span>
                )}
                {techniqueInfo.mishap_label && (
                  <span className="ml-2 text-red-400">Mishap: {techniqueInfo.mishap_label}</span>
                )}
              </div>
            )}

            <button
              className="mt-1 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-3 w-3" /> Hide details
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3" /> Show details
                </>
              )}
            </button>

            {expanded && (
              <div className="mt-2 rounded border bg-background p-2 text-xs text-muted-foreground">
                <p className="font-mono">{content}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Legacy string-parsing path — used for older interactions stored as plain text
  const parsed = parseActionContent(content);

  const displayAction = actionKey || parsed.actionName;
  const displayTechnique = techniqueName || parsed.techniqueName;
  const displayOutcome = outcome || parsed.outcomeName;
  const borderColor = getOutcomeColor(displayOutcome);

  return (
    <div className={`rounded-md border-l-4 ${borderColor} bg-muted/30 px-4 py-3`}>
      <div className="flex items-start gap-2">
        <Swords className="mt-0.5 h-4 w-4 shrink-0 text-purple-500" />
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{displayAction}</span>
            {displayTechnique && (
              <span className="text-xs text-muted-foreground">using {displayTechnique}</span>
            )}
          </div>

          {displayOutcome && (
            <p className="mt-1 text-sm">
              <span className="font-medium">{displayOutcome}</span>
              {parsed.consequenceLabel && (
                <span className="ml-1 text-muted-foreground">({parsed.consequenceLabel})</span>
              )}
            </p>
          )}

          {!parsed.outcomeName && !actionKey && <p className="mt-1 text-sm">{content}</p>}

          <button
            className="mt-1 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? (
              <>
                <ChevronUp className="h-3 w-3" /> Hide details
              </>
            ) : (
              <>
                <ChevronDown className="h-3 w-3" /> Show details
              </>
            )}
          </button>

          {expanded && (
            <div className="mt-2 rounded border bg-background p-2 text-xs text-muted-foreground">
              <p className="font-mono">{content}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
