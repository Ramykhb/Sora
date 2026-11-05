import test from 'node:test';
import assert from 'node:assert/strict';
import { dashboardStatus, latencyLabel } from '../src/lib/status.js';
test('an absent, idle, or disconnected camera never reports a healthy live system', () => {
  assert.equal(dashboardStatus({ connection: 'Connected', status: { streaming: true } }).healthy, false);
  assert.equal(dashboardStatus({ selectedId: 's', connection: 'Connected', status: { streaming: false } }).label, 'Standby');
  assert.equal(dashboardStatus({ selectedId: 's', connection: 'Reconnecting', status: { streaming: true } }).healthy, false);
});
test('stale camera frames and backend processing failures override connected state', () => {
  const live = { selectedId: 's', connection: 'Connected', status: { streaming: true, last_frame_seconds_ago: 1 } };
  assert.equal(dashboardStatus(live).healthy, true);
  assert.equal(dashboardStatus({ ...live, status: { ...live.status, last_frame_seconds_ago: 20 } }).label, 'Camera delayed');
  assert.equal(dashboardStatus({ ...live, status: { ...live.status, detection_error: 'Detector unavailable' } }).healthy, false);
  assert.equal(dashboardStatus({ ...live, error: 'Server offline' }).label, 'Needs attention');
});
test('missing or invalid latency is not converted into a fabricated measurement', () => {
  for (const value of [null, undefined, NaN, Infinity, -1, '142']) assert.equal(latencyLabel(value), 'Not measured');
  assert.equal(latencyLabel(0), '0 ms');
  assert.equal(latencyLabel(142.4), '142 ms');
  assert.equal(latencyLabel(1800), '1.8 s');
});
