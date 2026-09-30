import assert from 'node:assert/strict';
import test from 'node:test';

import {
  completeAnthropicSubscriptionOAuth,
  disconnectAnthropicSubscription,
  formatAnthropicSubscriptionError,
  getAnthropicSubscriptionStatus,
  startAnthropicSubscriptionOAuth,
  validAnthropicSubscriptionCallback,
} from '../../static/js/anthropicSubscriptionFlow.js';

const jsonResponse = (body, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

test('starts and completes OAuth with JSON while retaining no browser storage', async () => {
  const requests = [];
  const fetchImpl = async (url, options = {}) => {
    requests.push({ url, options });
    if (url.endsWith('/oauth/start')) {
      return jsonResponse({ authorize_url: 'https://claude.ai/oauth/authorize?opaque=1', attempt_id: 'attempt-1', expires_in: 900 });
    }
    return jsonResponse({ endpoint: { id: 'endpoint-1', models: ['claude-test'] } });
  };

  const start = await startAnthropicSubscriptionOAuth({ fetchImpl });
  const complete = await completeAnthropicSubscriptionOAuth(start.attemptId, 'https://localhost/callback?code=private-code', { fetchImpl });

  assert.equal(start.authorizationUrl, 'https://claude.ai/oauth/authorize?opaque=1');
  assert.equal(complete.endpoint.id, 'endpoint-1');
  assert.deepEqual(JSON.parse(requests[0].options.body), {});
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    attempt_id: 'attempt-1', callback: 'https://localhost/callback?code=private-code',
  });
  assert.equal(requests[1].options.headers['Content-Type'], 'application/json');
});

test('accepts the legacy authorization_url start-response spelling', async () => {
  const start = await startAnthropicSubscriptionOAuth({
    fetchImpl: async () => jsonResponse({
      authorization_url: 'https://claude.ai/oauth/authorize?legacy=1',
      attempt_id: 'attempt-legacy',
      expires_in: 600,
    }),
  });

  assert.equal(start.authorizationUrl, 'https://claude.ai/oauth/authorize?legacy=1');
  assert.equal(start.attemptId, 'attempt-legacy');
});

test('rejects blank callbacks before making a request', async () => {
  let called = false;
  await assert.rejects(
    () => completeAnthropicSubscriptionOAuth('attempt-1', '   ', { fetchImpl: async () => { called = true; } }),
    /not accepted/,
  );
  assert.equal(called, false);
  assert.equal(validAnthropicSubscriptionCallback('code'), true);
  assert.equal(validAnthropicSubscriptionCallback(''), false);
});

test('uses safe error messages without server detail or callback data', async () => {
  await assert.rejects(
    () => completeAnthropicSubscriptionOAuth('attempt-1', 'secret-code', {
      fetchImpl: async () => jsonResponse({ detail: 'secret-code should never be shown' }, 422),
    }),
    error => error.message === 'Could not complete Claude subscription sign-in.',
  );
  assert.equal(formatAnthropicSubscriptionError({ status: 429 }), 'Claude subscription quota or rate limit reached. Try again later.');
  assert.equal(formatAnthropicSubscriptionError({ status: 410 }), 'Authorization expired. Start the connection again.');
  assert.equal(formatAnthropicSubscriptionError({ status: 403 }), 'Your Claude subscription needs to be reconnected.');
});

test('checks status and disconnects with same-origin credentials', async () => {
  const requests = [];
  const fetchImpl = async (url, options = {}) => {
    requests.push({ url, options });
    return jsonResponse({ connected: true });
  };
  await getAnthropicSubscriptionStatus({ fetchImpl });
  await disconnectAnthropicSubscription({ fetchImpl });
  assert.equal(requests[0].url, '/api/anthropic-subscription/status');
  assert.equal(requests[0].options.credentials, 'same-origin');
  assert.equal(requests[1].url, '/api/anthropic-subscription/connection');
  assert.equal(requests[1].options.method, 'DELETE');
});
