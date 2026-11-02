export function isFreshObservation(value, time = Date.now()) {
  return Boolean(value?.expires_at && Number.isFinite(Date.parse(value.expires_at)) && Date.parse(value.expires_at) > time);
}

export function descriptionStatus(frame) {
  if (frame?.caption) return frame.caption;
  if (['pending', 'processing'].includes(frame?.enrichment_status)) return 'Frame saved. AI description is being prepared.';
  if (frame?.enrichment_status === 'skipped') return 'Objects and text saved. Detailed caption omitted to keep up with live capture.';
  return 'Saved observations available below.';
}
