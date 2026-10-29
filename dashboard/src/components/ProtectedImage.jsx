import { useEffect, useState } from 'react';
import { useAuth } from '../providers/Auth.jsx';
export default function ProtectedImage({ path, alt, ...props }) {
  const { api } = useAuth();
  const [result, setResult] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    let url;
    void api.response(path, { signal: controller.signal }).then(response => response.blob()).then(blob => {
      if (disposed) return;
      url = URL.createObjectURL(blob); setResult({ path, url });
    }).catch(error => { if (!disposed) setResult({ path, error: error.message }); });
    return () => { disposed = true; controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [api, path]);
  if (result?.path !== path) return <span className="image-placeholder" role="status">Loading image…</span>;
  if (result.error) return <span className="image-placeholder" role="status">{result.error}</span>;
  return <img src={result.url} alt={alt} {...props} />;
}
