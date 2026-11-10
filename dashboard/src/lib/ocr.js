export function recognizedText(frame) {
  if (frame?.ocr_text) return frame.ocr_text;
  const warnings = frame?.processing_warnings || [];
  if (warnings.includes('ocr_timeout')) return 'OCR timed out. Text could not be checked.';
  if (warnings.includes('ocr_busy')) return 'OCR was busy. Text could not be checked.';
  if (warnings.includes('ocr_unavailable')) return 'OCR was unavailable. Text could not be checked.';
  return 'No text recognized';
}

export function ocrWarning(code) {
  return {
    ocr_partial: 'OCR checked part of this image. Some text may be missing.',
    ocr_timeout: 'OCR timed out. Capture again to retry.',
    ocr_busy: 'OCR was busy. Capture again to retry.',
    ocr_unavailable: 'The OCR service was unavailable.',
  }[code] || code;
}
