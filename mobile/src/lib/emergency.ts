import type { ApiClient } from './api';
import { currentLocation } from './question-location';

export async function shareSOSLocation(api: ApiClient) {
  const accountId = api.tokens?.user?.id;
  const contact = await api.request<{ email: string }>('/emergency/contact');
  if (!contact.email) throw new Error('Add and save your SOS contact email in Settings first.');
  const location = await currentLocation(true);
  if (api.tokens?.user?.id !== accountId) throw new Error('Sign-in changed. Please try sharing your SOS location again.');
  const result = await api.request<{ message: string }>('/emergency/location', 'POST', location);
  return result.message;
}
