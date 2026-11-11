import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Platform, View } from 'react-native';
import { useFocusEffect } from 'expo-router';

import type { SavedDestination } from '@/lib/api';
import { currentLocation } from '@/lib/question-location';
import { destinationInput } from '@/lib/saved-destinations';
import { useAuth } from '@/providers/auth';
import { usePreferences } from '@/providers/preferences';
import { Action, Field } from './controls';
import { Card, Label } from './sora-ui';

export function SavedDestinationsSettings() {
  const { tokens, serverUrl } = useAuth();
  return tokens ? <SavedDestinationsForm key={`${serverUrl}:${tokens.user.id}`} /> : null;
}

function SavedDestinationsForm() {
  const { api, tokens, serverUrl } = useAuth();
  const { colors } = usePreferences();
  const ownerId = tokens?.user.id;
  const mounted = useRef(true);
  const [destinations, setDestinations] = useState<SavedDestination[]>([]);
  const [nickname, setNickname] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const lock = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  function currentAccount() { return mounted.current && api.tokens?.user?.id === ownerId && api.baseUrl === serverUrl; }
  useFocusEffect(useCallback(() => {
    let active = true;
    void api.request<SavedDestination[]>('/destinations').then(values => {
      if (active && api.tokens?.user?.id === ownerId && api.baseUrl === serverUrl) setDestinations(values);
    }).catch(e => { if (active) setError(e.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, ownerId, serverUrl]));

  function resetForm() { setNickname(''); setLatitude(''); setLongitude(''); setEditingId(null); }
  async function run(work: () => Promise<void>) {
    if (lock.current || !currentAccount()) return;
    lock.current = true; setBusy(true); setError(''); setMessage('');
    try { await work(); }
    catch (e) { if (currentAccount()) setError(e instanceof Error ? e.message : 'Unable to update saved destinations.'); }
    finally { lock.current = false; if (currentAccount()) setBusy(false); }
  }
  async function save() {
    await run(async () => {
      const body = destinationInput(nickname, latitude, longitude);
      const value = await api.request<SavedDestination>(editingId ? `/destinations/${editingId}` : '/destinations', editingId ? 'PUT' : 'POST', body);
      if (!currentAccount()) return;
      setDestinations(previous => [...previous.filter(item => item.id !== value.id), value].sort((a, b) => a.nickname.localeCompare(b.nickname)));
      resetForm(); setMessage(`Saved “${value.nickname}”. Say “route ${value.nickname}” to get walking directions.`);
    });
  }
  async function fillCurrentLocation() {
    await run(async () => {
      const value = await currentLocation(true);
      if (!currentAccount()) return;
      setLatitude(String(value.latitude)); setLongitude(String(value.longitude));
      setMessage('Current coordinates filled in. Check the nickname and tap Save destination to keep this place.');
    });
  }
  function edit(value: SavedDestination) {
    setEditingId(value.id); setNickname(value.nickname); setLatitude(String(value.latitude)); setLongitude(String(value.longitude));
    setMessage(`Editing “${value.nickname}”.`); setError('');
  }
  function remove(value: SavedDestination) {
    const work = () => run(async () => {
      await api.request(`/destinations/${value.id}`, 'DELETE');
      if (!currentAccount()) return;
      setDestinations(previous => previous.filter(item => item.id !== value.id));
      if (editingId === value.id) resetForm();
      setMessage(`Deleted “${value.nickname}”.`);
    });
    if (Platform.OS === 'web') {
      if (window.confirm(`Delete saved destination “${value.nickname}”?`)) void work();
    } else Alert.alert('Delete saved destination?', `Remove “${value.nickname}” from your saved places?`, [
      { text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: () => void work() },
    ]);
  }
  return <Card style={{ gap: 14 }}>
    <Label bold>Saved destinations</Label>
    <Label muted size={12}>Save a nickname and coordinates for each place, such as home, university, or your favorite restaurant. Say “route home” or “route to university”.</Label>
    <Label bold size={13}>{editingId ? 'Edit destination' : 'Add a destination'}</Label>
    <Field accessibilityLabel="Destination nickname" placeholder="Nickname, e.g. home" value={nickname} maxLength={80} onChangeText={setNickname} editable={!busy && !loading} autoCorrect={false} />
    <Field accessibilityLabel="Destination latitude" placeholder="Latitude (-90 to 90)" value={latitude} onChangeText={setLatitude} editable={!busy && !loading} keyboardType={Platform.OS === 'ios' ? 'numbers-and-punctuation' : 'default'} autoCapitalize="none" autoCorrect={false} maxLength={32} />
    <Field accessibilityLabel="Destination longitude" placeholder="Longitude (-180 to 180)" value={longitude} onChangeText={setLongitude} editable={!busy && !loading} keyboardType={Platform.OS === 'ios' ? 'numbers-and-punctuation' : 'default'} autoCapitalize="none" autoCorrect={false} maxLength={32} />
    <Action title="Use my current location" disabled={busy || loading} onPress={() => void fillCurrentLocation()} />
    <Action title={busy ? 'Please wait…' : editingId ? 'Save changes' : 'Save destination'} variant="primary" disabled={busy || loading || !nickname.trim() || !latitude.trim() || !longitude.trim()} onPress={() => void save()} />
    {editingId && <Action title="Cancel editing destination" disabled={busy} onPress={resetForm} />}
    {!!message && <Label accessibilityLiveRegion="polite" size={12}>{message}</Label>}
    {!!error && <Label accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Label>}
    <Label bold size={13}>{loading ? 'Loading saved destinations…' : 'Your destinations'}</Label>
    {!loading && !destinations.length && <Label muted size={12}>No saved destinations yet. Add your first place above.</Label>}
    {destinations.map(value => <View key={value.id} style={{ borderTopWidth: 1, borderColor: colors.border, paddingTop: 12, gap: 8 }}>
      <Label bold>{value.nickname}</Label>
      <Label muted selectable size={12}>{value.latitude.toFixed(6)}, {value.longitude.toFixed(6)}</Label>
      <Action title={`Edit ${value.nickname}`} disabled={busy || loading} onPress={() => edit(value)} />
      <Action title={`Delete ${value.nickname}`} variant="danger" disabled={busy || loading} onPress={() => remove(value)} />
    </View>)}
    <Label muted size={11}>Saved to your account until you delete them. Directions use your current GPS as the starting point; saved coordinates are the destination.</Label>
  </Card>;
}
