// DOM-free helper for the Claude subscription OAuth callback flow.
// Deliberately keeps attempt ids and pasted callbacks out of browser storage.

const API_BASE = '/api/anthropic-subscription';

async function jsonOrEmpty(response) {
  try {
    return await response.json();
  } catch (_) {
    return {};
  }
}

function requestFailed(status, fallback) {
  const error = new Error(fallback);
  error.status = status;
  return error;
}

async function requestJson(fetchImpl, url, options, fallback) {
  const response = await fetchImpl(url, options);
  const payload = await jsonOrEmpty(response);
  if (!response.ok) throw requestFailed(response.status, fallback);
  return payload;
}

export function formatAnthropicSubscriptionError(error, fallback = 'The Claude subscription request could not be completed. Try again.') {
  const status = Number(error && error.status);
  if (status === 401 || status === 403) return 'Your Claude subscription needs to be reconnected.';
  if (status === 429) return 'Claude subscription quota or rate limit reached. Try again later.';
  if (status === 408 || status === 410) return 'Authorization expired. Start the connection again.';
  if (status === 400 || status === 404 || status === 409 || status === 422) {
    return 'The pasted authorization callback was not accepted. Start the connection again.';
  }
  return fallback;
}

export function validAnthropicSubscriptionCallback(callback) {
  const value = String(callback || '').trim();
  return value.length > 0 && value.length <= 8192;
}

export async function startAnthropicSubscriptionOAuth(options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch?.bind(globalThis);
  if (!fetchImpl) throw new Error('Fetch API is unavailable');
  const start = await requestJson(fetchImpl, `${API_BASE}/oauth/start`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  }, 'Could not start Claude subscription sign-in.');
  const authorizationUrl = start && (start.authorize_url || start.authorization_url);
  if (typeof authorizationUrl !== 'string' || !authorizationUrl ||
      typeof start.attempt_id !== 'string' || !start.attempt_id) {
    throw new Error('Could not start Claude subscription sign-in.');
  }
  return {
    authorizationUrl,
    attemptId: start.attempt_id,
    expiresIn: Number(start.expires_in || 0),
  };
}

export async function completeAnthropicSubscriptionOAuth(attemptId, callback, options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch?.bind(globalThis);
  if (!fetchImpl) throw new Error('Fetch API is unavailable');
  if (!attemptId || !validAnthropicSubscriptionCallback(callback)) {
    throw new Error('The pasted authorization callback was not accepted. Start the connection again.');
  }
  return requestJson(fetchImpl, `${API_BASE}/oauth/complete`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attempt_id: attemptId, callback: String(callback).trim() }),
  }, 'Could not complete Claude subscription sign-in.');
}

export async function getAnthropicSubscriptionStatus(options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch?.bind(globalThis);
  if (!fetchImpl) throw new Error('Fetch API is unavailable');
  return requestJson(fetchImpl, `${API_BASE}/status`, {
    credentials: 'same-origin',
  }, 'Could not check Claude subscription status.');
}

export async function disconnectAnthropicSubscription(options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch?.bind(globalThis);
  if (!fetchImpl) throw new Error('Fetch API is unavailable');
  return requestJson(fetchImpl, `${API_BASE}/connection`, {
    method: 'DELETE',
    credentials: 'same-origin',
  }, 'Could not disconnect Claude subscription.');
}
