/**
 * The trail over an Almanach page (#5039): the way back up. Every step with a
 * destination is a link; the last step is the page itself and never one.
 */
import { Link } from 'react-router-dom';

export interface CrumbStep {
  label: string;
  to?: string;
}

export function Crumbs({ trail }: { trail: CrumbStep[] }) {
  const last = trail.length - 1;
  return (
    <nav className="crumb" aria-label="Breadcrumb">
      {trail.map((step, index) => (
        <span key={`${index}-${step.label}`}>
          {step.to && index < last ? <Link to={step.to}>{step.label}</Link> : step.label}
        </span>
      ))}
    </nav>
  );
}
