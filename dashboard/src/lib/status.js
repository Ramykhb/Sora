// Only display measurements actually supplied by the account's backend.
export function dashboardStatus({ selectedId, connection, status, error }) {
  const connected = Boolean(selectedId) && connection === 'Connected';
  const streaming = Boolean(status?.streaming);
  const stale = streaming && (status.last_frame_seconds_ago ?? 0) > 10;
  const processingError = status?.processing_error || status?.detection_error;
  return {
    connected, streaming,
    healthy: connected && streaming && !stale && !processingError && !error,
    label: !selectedId ? 'No session' : !connected ? connection : processingError || error ? 'Needs attention' : stale ? 'Camera delayed' : streaming ? 'Live' : 'Standby',
    detail: processingError || error || (stale ? 'Waiting for fresh camera frames' : connected ? streaming ? 'Camera and server connected' : 'Server connected · camera idle' : 'Waiting for a server connection'),
  };
}
export function latencyLabel(milliseconds) {
  return typeof milliseconds === 'number' && Number.isFinite(milliseconds) && milliseconds >= 0 ? milliseconds >= 1000 ? `${(milliseconds / 1000).toFixed(1)} s` : `${Math.round(milliseconds)} ms` : 'Not measured';
}
