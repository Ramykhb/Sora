export function parseWalkingRoute(text: string) {
  const [intro, ...lines] = text.split('\n');
  if (!/(?:Walking directions from Google Maps:|Itinéraire piéton de Google Maps\s*:|اتجاهات المشي من Google Maps:)\s*$/.test(intro)) return null;
  const steps: string[] = [];
  while (lines.length && new RegExp(`^${steps.length + 1}\\.\\s+`).test(lines[0])) steps.push(lines.shift()!);
  if (!steps.length) return null;
  return { intro, steps, notes: lines.join('\n') };
}
export type RoutePlayback = { text: string; language: string; route: NonNullable<ReturnType<typeof parseWalkingRoute>>; index: number; full: boolean };

type Driver = {
  stop: () => Promise<void>;
  speak: (text: string, options: { language: string; urgent?: boolean; dynamicAlert?: boolean; onDone?: () => void; onStopped?: () => void; onError?: (error: Error) => void }) => void | Promise<void>;
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
  private routePlayback: RoutePlayback | null = null;
  private routeListeners = new Set<() => void>();
  getRoutePlayback = () => this.routePlayback;
  subscribeRoute = (listener: () => void) => {
    this.routeListeners.add(listener);
    return () => { this.routeListeners.delete(listener); };
  };
  private updateRoute(value: RoutePlayback | null) {
    this.routePlayback = value;
    this.routeListeners.forEach(listener => listener());
  }
  constructor(private driver: Driver) {}
  rememberAnswer(text: string, language: string) {
    if (!text.trim()) return;
    const reply = { text, language };
    this.lastAnswer = reply;
    const route = parseWalkingRoute(text);
    if (route) {
      this.lastDirections = reply;
      if (this.routePlayback?.text !== text || this.routePlayback.language !== language) {
        this.updateRoute({ ...reply, route, index: 0, full: false });
      }
    }
  }
  clearHistory() {
    this.lastAnswer = null;
    this.lastDirections = null;
    this.updateRoute(null);
  }
  async repeatLastAnswer(directionsOnly = false) {
    const reply = directionsOnly ? this.lastDirections : this.lastAnswer;
    if (!reply) return false;
    if (directionsOnly) return this.showFullRoute();
    await this.answer(reply.text, reply.language);
    return true;
  }
  async showFullRoute() {
    const current = this.routePlayback;
    if (!current) return false;
    this.updateRoute({ ...current, full: true });
    await this.answer(current.text, current.language, undefined, true);
    return true;
  }
  async moveRouteStep(offset: -1 | 1) {
    const current = this.routePlayback;
    if (!current) return false;
    const index = Math.max(0, Math.min(current.route.steps.length - 1, current.index + offset));
    this.updateRoute({ ...current, index, full: false });
    const lang = current.language.split(/[-_]/)[0];
    const boundary = index === current.index ? (lang === 'fr'
      ? (offset < 0 ? 'Vous êtes à la première étape.' : 'Vous êtes à la dernière étape.')
      : lang === 'ar' ? (offset < 0 ? 'هذه هي الخطوة الأولى.' : 'هذه هي الخطوة الأخيرة.')
      : (offset < 0 ? 'This is the first step.' : 'This is the last step.')) : '';
    await this.answer([boundary, current.route.steps[index]].filter(Boolean).join(' '), current.language);
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
  async answer(text: string, language: string, onDone?: () => void, fullRoute = false) {
    if (this.muted) { onDone?.(); return; }
    if (this.urgent) return;
    const route = !fullRoute && parseWalkingRoute(text);
    if (route) {
      this.rememberAnswer(text, language);
      const current = this.routePlayback!;
      this.updateRoute({ ...current, full: false });
      text = [route.intro, route.steps[current.index], route.notes].filter(Boolean).join('\n');
    }
    const generation = ++this.generation;
    this.interruptors.forEach(callback => callback());
    await this.driver.stop();
    if (generation === this.generation) await this.driver.speak(text, { language, ...(onDone ? { onDone, onStopped: onDone, onError: onDone } : {}) });
  }
  async alert(id: string, text: string, language: string, expiresAt: string, dynamicAlert = false) {
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
    await this.driver.speak(text, { language, urgent: true, ...(dynamicAlert ? { dynamicAlert: true } : {}), onDone: done, onStopped: done, onError: done });
  }
}
