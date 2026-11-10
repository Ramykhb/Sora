import { useEffect, useState } from 'react';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import { shareSOSLocation } from '@/lib/emergency';
import { speech } from '@/lib/speech';
import { Action, Field } from './controls';
import { Card, Label } from './sora-ui';

export function EmergencySettings() {
  const { tokens } = useAuth();
  return tokens ? <EmergencyContactForm key={tokens.user.id} /> : null;
}

function EmergencyContactForm() {
  const { api } = useAuth();
  const { colors } = usePreferences();
  const [email, setEmail] = useState('');
  const [saved, setSaved] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    void api.request<{ email: string }>('/emergency/contact').then(value => {
      if (active) { setEmail(value.email); setSaved(value.email); }
    }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api]);
  async function save() {
    setBusy(true); setError(''); setMessage('');
    try {
      const value = await api.request<{ email: string }>('/emergency/contact', 'PUT', { email: email.trim() });
      setEmail(value.email); setSaved(value.email);
      setMessage(value.email ? 'SOS contact saved.' : 'SOS contact removed.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save SOS contact.'); }
    finally { setBusy(false); }
  }
  async function share() {
    setBusy(true); setError(''); setMessage('Getting your current location…');
    try { const result = await shareSOSLocation(api); setMessage(result); await speech.answer(result, 'en'); }
    catch (e) { setMessage(''); setError(e instanceof Error ? e.message : 'Unable to send your location.'); }
    finally { setBusy(false); }
  }
  return <Card style={{ gap: 12 }}>
    <Label bold>Emergency SOS &amp; location sharing</Label>
    <Label muted size={12}>Save your emergency contact’s email. Say “SOS”, “Send SOS”, “Send SOS contact”, or “Send my location to my SOS contact”.</Label>
    <Field accessibilityLabel="SOS contact email" placeholder="Emergency contact email" keyboardType="email-address" autoCapitalize="none" autoCorrect={false} value={email} onChangeText={setEmail} editable={!loading && !busy} />
    <Action title={loading ? 'Loading SOS contact…' : 'Save SOS contact'} disabled={loading || busy} onPress={() => void save()} />
    <Action title={busy ? 'Please wait…' : 'Send my location to SOS contact'} disabled={loading || busy || !saved || email.trim().toLowerCase() !== saved} variant="danger" onPress={() => void share()} />
    <Label muted size={11}>Sends your current coordinates and a Google Maps link by email. This does not call emergency services. Voice sharing works while Sora is open and voice controls are enabled.</Label>
    {!!message && <Label accessibilityLiveRegion="polite" size={12}>{message}</Label>}
    {!!error && <Label accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Label>}
  </Card>;
}
