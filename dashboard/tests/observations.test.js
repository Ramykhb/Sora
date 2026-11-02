import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isFreshObservation, descriptionStatus } from '../src/lib/observations.js';

test('live observations and alerts expire independently of retained history', () => {
  const value = { expires_at: '2026-11-02T12:00:02Z' };
  assert.equal(isFreshObservation(value, Date.parse('2026-11-02T12:00:01Z')), true);
  assert.equal(isFreshObservation(value, Date.parse(value.expires_at)), false);
  assert.equal(isFreshObservation({ expires_at: 'invalid' }), false);
  assert.equal(isFreshObservation(null), false);
});

test('skipped captions describe available observations without implying completion', () => {
  assert.match(descriptionStatus({ enrichment_status: 'skipped' }), /Objects and text saved/);
  assert.match(descriptionStatus({ enrichment_status: 'processing' }), /being prepared/);
  assert.equal(descriptionStatus({ caption: 'A chair', enrichment_status: 'complete' }), 'A chair');
});
