#!/usr/bin/env node
// Credential-free diagnostics for #4506. Run with the actual client's Node/curl.
import { execFile } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { connect } from 'node:tls';
import { pathToFileURL } from 'node:url';

export const fixtures = JSON.parse(readFileSync(new URL('./tls-trust-fixtures.json', import.meta.url), 'utf8'));

// Require the native key block, not merely root removal on the twelve paths.
export function classifyNodeError(code) {
  return code === 'CERT_REVOKED' ? 'rejected' : 'inconclusive';
}

export function isPatchedNodeVersion(version) {
  const match = /^v?(22|24)\.(\d+)\.(\d+)$/.exec(version);
  if (!match) return false;
  const [, major, minor, patch] = match.map(Number);
  const [minimumMinor, minimumPatch] = major === 22 ? [23, 4] : [22, 1];
  return minor > minimumMinor || minor === minimumMinor && patch >= minimumPatch;
}

export function classifyCurlError(code, detail) {
  const expectedError = /certificate revoked|unable to get (?:local )?issuer certificate|unable to verify the first certificate|self[- ]signed certificate in certificate chain/i.test(detail);
  return code === 60 && expectedError ? 'observed-rejection' : 'inconclusive';
}

export function classifyIncidentResult(host, fingerprints, authorized, error) {
  const expected = fixtures.chains[host];
  if (!expected || !expected.every((fingerprint, index) => fingerprints[index] === fingerprint)) {
    return { status: 'inconclusive', detail: 'peer chain differs from the pinned incident fixture' };
  }
  return { status: authorized ? 'trusted' : classifyNodeError(error), detail: `pinned chain matched; ${error || 'authorized'}` };
}

export function nodeProbe(host, incident = false) {
  return new Promise((resolve) => {
    // Incident probes complete a handshake only to inspect failed authorization
    // and the peer chain ON THE SAME SOCKET. Verification still runs. No HTTP,
    // credentials or other application bytes are sent on this socket.
    const socket = connect({ host, port: 443, servername: host, rejectUnauthorized: !incident });
    socket.setTimeout(10000, () => socket.destroy(Object.assign(new Error('timeout'), { code: 'ETIMEDOUT' })));
    socket.once('secureConnect', () => {
      if (incident) {
        const fingerprints = [];
        const seen = new Set();
        let peer = socket.getPeerCertificate(true);
        while (peer?.raw && !seen.has(peer.fingerprint256)) {
          seen.add(peer.fingerprint256);
          fingerprints.push(peer.fingerprint256.replaceAll(':', ''));
          peer = peer.issuerCertificate;
        }
        resolve(classifyIncidentResult(host, fingerprints, socket.authorized, socket.authorizationError));
      } else {
        resolve({ status: 'trusted', detail: socket.getProtocol() });
      }
      socket.destroy();
    });
    socket.on('error', (error) => {
      // Without the peer chain, even a certificate error cannot prove that the
      // incident fixture was tested. Fail closed on pre-handshake errors.
      resolve({ status: 'inconclusive', detail: error.code });
    });
  });
}

export function curlProbe(host) {
  return new Promise((resolve) => {
    // -q ignores .curlrc (which may contain --insecure). No credentials or redirects.
    // curl 60 alone is insufficient: it also includes expiry/hostname failures.
    execFile('curl', ['-q', '--silent', '--show-error', '--noproxy', '*',
      '--connect-timeout', '5', '--max-time', '10', '--output', '/dev/null',
      `https://${host}/`], { env: { ...process.env, LC_ALL: 'C' }, timeout: 12000 },
    (error, stdout, stderr) => {
      const detail = stderr.trim().split('\n')[0];
      resolve({
        status: !error ? 'trusted' : classifyCurlError(error.code, detail),
        detail: !error ? 'HTTPS connected' : detail || String(error.code),
      });
    });
  });
}

export async function main() {
  if (!isPatchedNodeVersion(process.version)) {
    console.error(`Unsupported diagnostic runtime ${process.version}; require Node 22.23.4+ or 24.22.1+ on those release lines.`);
    return 2;
  }
  if (process.env.NODE_TLS_REJECT_UNAUTHORIZED === '0') {
    console.error('Remove NODE_TLS_REJECT_UNAUTHORIZED=0 before checking trust.');
    return 2;
  }
  console.log(`Node ${process.version}; curl uses its own configured trust store.`);
  console.log('Direct probes; run outside restricted egress if blocked. No credentials are sent.');
  console.log(`Pinned fixture archive SHA-256: ${fixtures.archiveSha256}`);
  const compromisedHosts = Object.keys(fixtures.chains);
  const controls = ['registry.npmjs.org', 'github.com', 'pypi.org'];
  const checks = await Promise.all([['node', nodeProbe], ['curl', curlProbe]].flatMap(([client, probe]) =>
    [...controls, ...compromisedHosts].map(async (host) => {
      const incident = !controls.includes(host);
      const result = await probe(host, incident);
      const expected = incident ? 'rejected' : 'trusted';
      if (client === 'curl' && incident) {
        console.log(`OBSERVATION curl ${host}: ${result.status} (${result.detail}); peer identity unbound`);
        return { ...result, client, expected, pass: true };
      }
      const pass = result.status === expected;
      console.log(`${pass ? 'PASS' : 'FAIL'} ${client} ${host}: ${result.status} (${result.detail})`);
      return { ...result, client, pass, expected };
    })));
  console.log('Exit 0 assesses pinned Node handshakes and normal HTTPS controls; curl negative probes are unbound observations.');
  return summarizeChecks(checks);
}

export function summarizeChecks(checks) {
  const vulnerable = checks.some((result) => result.expected === 'rejected' && result.status === 'trusted');
  if (vulnerable) return 1;
  if (checks.filter(result => result.client === 'node' && result.expected === 'rejected').length !== 12) return 2;
  if (checks.filter(result => result.expected === 'trusted').length !== 6) return 2;
  return checks.every((result) => result.pass) ? 0 : 2;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    process.exitCode = await main();
  } catch (error) {
    console.error(`Diagnostic failed before completion: ${error.message}`);
    process.exitCode = 2;
  }
}
