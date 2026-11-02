type Driver = {
  stop: () => Promise<void>;
  speak: (text: string, options: { language: string; onDone?: () => void; onStopped?: () => void; onError?: (error: Error) => void }) => void;
};

// Shared by automatic answers and obstacle alerts. No device APIs in this policy.
export class SpeechController {
  private generation = 0;
  private urgent = false;
  private seen = new Set<string>();
  private interruptors = new Set<() => void>();
  constructor(private driver: Driver) {}
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
  async answer(text: string, language: string) {
    if (this.urgent) return;
    const generation = ++this.generation;
    this.interruptors.forEach(callback => callback());
    await this.driver.stop();
    if (generation === this.generation) this.driver.speak(text, { language });
  }
  async alert(id: string, text: string, language: string, expiresAt: string) {
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
    this.driver.speak(text, { language, onDone: done, onStopped: done, onError: done });
  }
}
