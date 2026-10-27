import { useEffect, useState } from 'react';

export const pageTitles = {
  overview: 'Overview', live: 'Live session', frames: 'Frame library',
  questions: 'Conversations', settings: 'Preferences',
};

function readPage() {
  const requested = window.location.hash.slice(1);
  return Object.hasOwn(pageTitles, requested) ? requested : 'overview';
}

export default function usePage() {
  const [page, setPage] = useState(readPage);
  useEffect(() => {
    const navigate = () => setPage(readPage());
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  useEffect(() => { document.title = `Sora · ${pageTitles[page]}`; }, [page]);
  return page;
}
