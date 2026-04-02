import type { SoulfrayWarningData } from '../actionTypes';

interface SoulfrayWarningProps {
  warning: SoulfrayWarningData;
  techniqueName: string;
  animaCost: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export function SoulfrayWarning({
  warning,
  techniqueName,
  animaCost,
  onConfirm,
  onCancel,
}: SoulfrayWarningProps) {
  const isDangerous = warning.has_death_risk;

  return (
    <div
      className={`rounded-lg border p-4 ${isDangerous ? 'border-red-500 bg-red-950/50' : 'border-amber-500 bg-amber-950/50'}`}
    >
      <h3 className={`mb-2 font-bold ${isDangerous ? 'text-red-400' : 'text-amber-400'}`}>
        {isDangerous ? 'DANGER: ' : ''}Soulfray Warning — {warning.stage_name}
      </h3>
      <p className="mb-2 text-sm text-gray-300">{warning.stage_description}</p>
      <p className="mb-4 text-sm text-gray-400">
        Using <strong>{techniqueName}</strong> will cost <strong>{animaCost} anima</strong> and may
        worsen your condition.
      </p>
      <div className="flex gap-2">
        <button
          onClick={onCancel}
          className="rounded bg-gray-700 px-3 py-1 text-sm hover:bg-gray-600"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          className={`rounded px-3 py-1 text-sm ${isDangerous ? 'bg-red-700 hover:bg-red-600' : 'bg-amber-700 hover:bg-amber-600'}`}
        >
          {isDangerous ? 'Accept Risk' : 'Proceed'}
        </button>
      </div>
    </div>
  );
}
