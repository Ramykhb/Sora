import assert from 'node:assert/strict';
import { test } from 'node:test';
import { recognizedText, ocrWarning } from '../src/lib/ocr.js';

test('OCR failures are not displayed as a successful no-text result', () => {
  for (const warning of ['ocr_timeout', 'ocr_busy', 'ocr_unavailable']) {
    assert.match(recognizedText({ ocr_text: '', processing_warnings: [warning] }), /Text could not be checked/);
  }
  assert.equal(recognizedText({ ocr_text: '', processing_warnings: [] }), 'No text recognized');
  assert.equal(recognizedText({ ocr_text: 'EXIT', processing_warnings: ['ocr_timeout'] }), 'EXIT');
  assert.match(ocrWarning('ocr_partial'), /Some text may be missing/);
  assert.match(ocrWarning('ocr_timeout'), /Capture again/);
});
