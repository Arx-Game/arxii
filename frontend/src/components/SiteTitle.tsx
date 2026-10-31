import { Link } from 'react-router-dom';
import { SITE_NAME } from '@/config';

export function SiteTitle() {
  return (
    <h1 className="min-w-0 shrink text-xl font-bold sm:text-2xl">
      <Link to="/" className="block truncate">
        {SITE_NAME}
      </Link>
    </h1>
  );
}
