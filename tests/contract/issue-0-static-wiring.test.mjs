// Supporting wiring check for manual criterion 9.  No network or credentials.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');

// Regression: the UI names the provider but cannot invoke its connect/reconnect
// flow, leaving the account-gated live smoke impossible to start.
const admin = read('static/js/admin.js');
const setup = read('static/js/slashCommands.js');
const index = read('static/index.html');
const flow = read('static/js/anthropicSubscriptionFlow.js');
assert.match(admin, /anthropic-subscription/);
assert.match(setup, /anthropic-subscription/);

assert.match(index, /value="anthropic-subscription"[^>]*>Claude Subscription \(experimental\)<\/option>/);
assert.match(admin, /startAnthropicSubscriptionOAuth/);
assert.match(admin, /completeAnthropicSubscriptionOAuth/);
assert.match(admin, /disconnectAnthropicSubscription/);
assert.match(setup, /async function _setupAnthropicSubscriptionFlow/);
assert.match(setup, /async function _completeAnthropicSubscriptionSetup/);
assert.match(setup, /paste the returned callback URL or code here/i);
assert.match(flow, /\/oauth\/start/);
assert.match(flow, /\/oauth\/complete/);
assert.match(flow, /\/connection/);
assert.doesNotMatch(flow, /localStorage|sessionStorage/);
