/** Actionable recapture advice grounded in an uncertain visual answer. */
export function cameraFeedback(uncertain: boolean, answer: string, warnings: readonly string[] = [], visualContext = true): string | null {
  if (!uncertain || !visualContext) return null;
  const text = answer.toLowerCase();
  if (/ground|floor|walking surface|path ahead/.test(text) && /not visible|isn't visible|can't see|cannot see|out of (?:the )?(?:view|frame)|not shown|unclear/.test(text)) {
    return "The ground isn't visible—tilt the camera slightly downward and try again.";
  }
  if (/too dark|low light|poor lighting|not enough light|underexposed|dim image|image is dark/.test(text)) {
    return 'The image looks too dark. Move toward better light and try again.';
  }
  if (/blurr|out of focus|motion blur|shak/.test(text)) {
    return 'The image looks blurry. Hold the camera steady, let it focus, and try again.';
  }
  if (/partially (?:visible|hidden)|cut off|out of (?:the )?frame|not fully visible/.test(text)) {
    return 'Part of the subject is outside the view. Move back slightly and center it in the frame.';
  }
  if (warnings.includes('current_view_timeout') || warnings.includes('evidence_expired_during_inference')) {
    return 'A fresh view was not available. Hold the camera steady and ask again.';
  }
  return 'For a clearer answer, center what you want to identify, hold the camera steady, and try again in good light.';
}
