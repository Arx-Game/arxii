#!/usr/bin/env node
// Reproduce the reviewed manifest from a downloaded archive, without extracting files.
import { execFileSync } from 'node:child_process';
import { createHash, X509Certificate } from 'node:crypto';
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';

try {
  if (process.argv.length !== 3) throw new Error('Usage: node scripts/verify-tls-trust-fixtures.mjs /path/to/chains.zip');
  const fixtures = JSON.parse(readFileSync(new URL('./tls-trust-fixtures.json', import.meta.url), 'utf8'));
  const archive = process.argv[2];
  assert.equal(createHash('sha256').update(readFileSync(archive)).digest('hex'), fixtures.archiveSha256,
    'Archive differs from the reviewed disclosure snapshot; do not automatically refresh pins');
  for (const [host, expected] of Object.entries(fixtures.chains)) {
    const pem = execFileSync('unzip', ['-p', archive, `chains/${host}.pem`], { encoding: 'utf8' });
    const certs = pem.match(/-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----/g) || [];
    const actual = certs.map(cert => new X509Certificate(cert).fingerprint256.replaceAll(':', ''));
    assert.deepEqual(actual, expected, `Certificate fingerprints differ for ${host}`);
  }
  console.log(`Verified ${Object.keys(fixtures.chains).length} fixture chains against archive ${fixtures.archiveSha256}`);
} catch (error) {
  console.error(`Fixture verification failed: ${error.message}`);
  process.exitCode = 2;
}
