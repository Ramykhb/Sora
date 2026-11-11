type Driver = {
  stop: () => Promise<void>;
  speak: (text: string, options: { language: string; onDone?: () => void; onStopped?: () => void; onError?: (error: Error) => void }) => void | Promise<void>;
};

// Shared by automatic answers and obstacle alerts. No device APIs in this policy.
export class SpeechController {
  private generation = 0;
  private muted = false;
  private urgent = false;
  private seen = new Set<string>();
  private interruptors = new Set<() => void>();
  private lastAnswer: { text: string; language: string } | null = null;
  private lastDirections: { text: string; language: string } | null = null;
  constructor(private driver: Driver) {}
  rememberAnswer(text: string, language: string) {
    if (!text.trim()) return;
    const reply = { text, language };
    this.lastAnswer = reply;
    // These are the localized headings emitted by the walking-route formatter.
    // Keep a route available after an unrelated camera answer or app confirmation.
    if (/(?:Walking directions from Google Maps:|Itinéraire piéton de Google Maps\s*:|اتجاهات المشي من Google Maps:)\s*$/.test(text.split('\n')[0])) {
      this.lastDirections = reply;
    }
  }
  clearHistory() {
    this.lastAnswer = null;
    this.lastDirections = null;
  }
  async repeatLastAnswer(directionsOnly = false) {
    const reply = directionsOnly ? this.lastDirections : this.lastAnswer;
    if (!reply) return false;
    await this.answer(reply.text, reply.language);
    return true;
  }
  get isMuted() { return this.muted; }
  setMuted(muted: boolean) {
    this.muted = muted;
    return muted ? this.stop() : Promise.resolve();
  }
  registerInterruptor(callback: () => void) {
    this.interruptors.add(callback);
    return () => { this.interruptors.delete(callback); };
  }
  async stop() {
    this.generation++;
    this.urgent = false;
    this.interruptors.forEach(callback => callback());
    await this.driver.stop();
  }
  async answer(text: string, language: string, onDone?: () => void) {
    if (this.muted) { onDone?.(); return; }
    if (this.urgent) return;
    const generation = ++this.generation;
    this.interruptors.forEach(callback => callback());
    await this.driver.stop();
    if (generation === this.generation) await this.driver.speak(text, { language, ...(onDone ? { onDone, onStopped: onDone, onError: onDone } : {}) });
  }
  async alert(id: string, text: string, language: string, expiresAt: string) {
    if (this.muted) return;
    const deadline = Date.parse(expiresAt);
    if (!Number.isFinite(deadline) || deadline <= Date.now() || this.seen.has(id)) return;
    this.seen.add(id);
    if (this.seen.size > 128) this.seen.delete(this.seen.values().next().value!);
    const generation = ++this.generation;
    this.urgent = true;
    this.interruptors.forEach(callback => callback());
    await this.driver.stop();
    if (generation !== this.generation) return;
    if (deadline <= Date.now()) { this.urgent = false; return; }
    const done = () => { if (generation === this.generation) this.urgent = false; };
    await this.driver.speak(text, { language, onDone: done, onStopped: done, onError: done });
  }
}
