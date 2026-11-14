import type { ApiClient } from './api';
import { currentLocation } from './question-location';
import { voiceText, type VoiceLanguage } from './voice-language';

export async function shareSOSLocation(api: ApiClient, language: VoiceLanguage = 'en') {
  const accountId = api.tokens?.user?.id;
  const contact = await api.request<{ email: string }>('/emergency/contact');
  if (!contact.email) throw new Error(voiceText('sosContactRequired', language));
  const location = await currentLocation(true, {
    permission: voiceText('locationAccessRequired', language),
    timeout: voiceText('locationTimedOut', language),
  });
  if (api.tokens?.user?.id !== accountId) throw new Error(voiceText('sosSignInChanged', language));
  await api.request<{ message: string }>('/emergency/location', 'POST', location);
  return voiceText('sosSent', language);
}
