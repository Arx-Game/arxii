import { Link } from 'react-router-dom';
import { SITE_NAME } from '../config';

export function SiteTitle() {
  return (
    <h1 className="text-2xl font-bold">
      <Link to="/">{SITE_NAME}</Link>
    </h1>
  );
}
