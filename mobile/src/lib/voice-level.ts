export type VoiceLevelSnapshot = { listening: boolean; level: number };

export function normalizeVoiceLevel(value: number) {
  if (!Number.isFinite(value) || value <= 0) return 0;
  // The recognizer reports -2..10; emphasize quiet speech without clipping peaks.
  return Math.round(Math.pow(Math.min(value, 10) / 10, 0.65) * 100) / 100;
}

// Meter updates do not rerender the auth/navigation tree or the camera preview.
export class VoiceLevelMeter {
  private snapshot: VoiceLevelSnapshot = { listening: false, level: 0 };
  private listeners = new Set<() => void>();
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  setListening(listening: boolean) { this.publish({ listening, level: 0 }); }
  update(value: number) {
    if (this.snapshot.listening) this.publish({ listening: true, level: normalizeVoiceLevel(value) });
  }
  private publish(snapshot: VoiceLevelSnapshot) {
    if (snapshot.listening === this.snapshot.listening && snapshot.level === this.snapshot.level) return;
    this.snapshot = snapshot;
    this.listeners.forEach(listener => listener());
  }
}
export const voiceLevel = new VoiceLevelMeter();
