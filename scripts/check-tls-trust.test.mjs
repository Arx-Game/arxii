import assert from 'node:assert/strict';
import test from 'node:test';
import { classifyCurlError, classifyIncidentResult, classifyNodeError, fixtures,
  isPatchedNodeVersion, summarizeChecks } from './check-tls-trust.mjs';

test('only native revocation counts as a Node rejection', () => {
  assert.equal(classifyNodeError('CERT_REVOKED'), 'rejected');
  for (const code of ['UNABLE_TO_GET_ISSUER_CERT', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY',
    'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'SELF_SIGNED_CERT_IN_CHAIN']) {
    assert.equal(classifyNodeError(code), 'inconclusive');
  }
});

test('curl 60 requires an issuer or revocation error, not expiry or hostname mismatch', () => {
  assert.equal(classifyCurlError(60, 'SSL certificate problem: unable to get local issuer certificate'), 'observed-rejection');
  assert.equal(classifyCurlError(60, 'SSL certificate problem: certificate revoked'), 'observed-rejection');
  for (const [code, message] of [[60, 'SSL certificate problem: certificate has expired'],
    [60, 'no alternative certificate subject name matches'], [6, 'Could not resolve host'],
    [28, 'Timeout was reached'], [7, 'Failed to connect'], ['ENOENT', '']]) {
    assert.equal(classifyCurlError(code, message), 'inconclusive');
  }
});

test('unrelated, partial, reordered or rotated peer chains cannot prove incident rejection', () => {
  const host = Object.keys(fixtures.chains)[0];
  const expected = fixtures.chains[host];
  for (const fingerprints of [[], ['unrelated'], expected.slice(0, 1), [...expected].reverse(),
    ['rotated-leaf', ...expected.slice(1)]]) {
    assert.equal(classifyIncidentResult(host, fingerprints, false, 'CERT_REVOKED').status, 'inconclusive');
    assert.equal(classifyIncidentResult(host, fingerprints, false, 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY').status, 'inconclusive');
  }
  assert.equal(classifyIncidentResult('wrong-host', expected, false, 'CERT_REVOKED').status, 'inconclusive');
});

test('only the same authorized incident chain decides trust; trailing roots are permitted', () => {
  const host = Object.keys(fixtures.chains)[0];
  const expected = fixtures.chains[host];
  assert.equal(classifyIncidentResult(host, expected, true, null).status, 'trusted');
  assert.equal(classifyIncidentResult(host, expected, false, 'CERT_REVOKED').status, 'rejected');
  assert.equal(classifyIncidentResult(host, [...expected, 'trailing-root'], false, 'CERT_REVOKED').status, 'rejected');
  assert.equal(classifyIncidentResult(host, expected, false, 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY').status, 'inconclusive');
  assert.equal(classifyIncidentResult(host, expected, false, 'CERT_HAS_EXPIRED').status, 'inconclusive');
});

test('the diagnostic rejects unsupported majors and versions below each security floor', () => {
  for (const version of ['v22.23.4', '22.24.0', 'v24.22.1', 'v24.23.0']) {
    assert.equal(isPatchedNodeVersion(version), true);
  }
  for (const version of ['v22.23.3', 'v24.22.0', 'v24.4.1', 'v23.99.0', 'v25.0.0',
    'v24.22.1-nightly', 'not-a-version']) {
    assert.equal(isPatchedNodeVersion(version), false);
  }
});

test('exit codes distinguish protection, trusted probes and incomplete evidence', () => {
  const valid = () => [
    ...Array.from({ length: 12 }, () => ({ client: 'node', expected: 'rejected', status: 'rejected', pass: true })),
    ...Array.from({ length: 6 }, () => ({ client: 'node', expected: 'trusted', status: 'trusted', pass: true })),
  ];
  assert.equal(summarizeChecks(valid()), 0);
  const trusted = valid();
  trusted[0] = { ...trusted[0], status: 'trusted', pass: false };
  assert.equal(summarizeChecks(trusted), 1);
  const unknown = valid();
  unknown[0] = { ...unknown[0], status: 'inconclusive', pass: false };
  assert.equal(summarizeChecks(unknown), 2);
  const failedControl = valid();
  failedControl[12] = { ...failedControl[12], status: 'inconclusive', pass: false };
  assert.equal(summarizeChecks(failedControl), 2);
  assert.equal(summarizeChecks([]), 2);
  assert.equal(summarizeChecks(valid().slice(1)), 2);
  assert.equal(summarizeChecks([...valid(), { client: 'curl', expected: 'rejected', status: 'inconclusive', pass: true }]), 0);
  assert.equal(summarizeChecks([...valid(), { client: 'curl', expected: 'rejected', status: 'trusted', pass: true }]), 1);
});

test('network failures and unrelated certificate errors cannot pass the check', () => {
  for (const code of ['ENOTFOUND', 'ECONNREFUSED', 'ETIMEDOUT', 'CERT_HAS_EXPIRED',
    'ERR_TLS_CERT_ALTNAME_INVALID', undefined]) {
    assert.equal(classifyNodeError(code), 'inconclusive');
  }
});
