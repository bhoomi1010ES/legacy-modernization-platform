import { afterEach, describe, expect, it, vi } from 'vitest';
import { webcrypto } from 'node:crypto';
import { fetchVerifiedZip } from '../services/verifiedDownload';

const bytes = new Uint8Array([0x50, 0x4b, 3, 4, 0, 1]);
async function hash(data: Uint8Array) {
  return Buffer.from(await webcrypto.subtle.digest('SHA-256', data)).toString('hex');
}
afterEach(() => vi.unstubAllGlobals());

describe('Verified ZIP download', () => {
  it('saves only bytes matching the approved hash and sends session credentials', async () => {
    vi.stubGlobal('crypto', webcrypto);
    const expected = await hash(bytes);
    const fetch = vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ 'X-Content-SHA256': expected }), arrayBuffer: async () => bytes.buffer });
    vi.stubGlobal('fetch', fetch);
    const blob = await fetchVerifiedZip('job-1', 'artifact-1', expected);
    expect(blob.size).toBe(bytes.length);
    expect(fetch).toHaveBeenCalledWith('/api/v1/jobs/job-1/artifacts/artifact-1/download', { credentials: 'include', redirect: 'error' });
  });

  it('rejects changed bytes even when the response hash header is correct', async () => {
    vi.stubGlobal('crypto', webcrypto);
    const expected = await hash(bytes);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: new Headers({ 'X-Content-SHA256': expected }), arrayBuffer: async () => new Uint8Array([9]).buffer }));
    await expect(fetchVerifiedZip('job-1', 'artifact-1', expected)).rejects.toThrow('integrity check failed');
  });

  it('rejects a missing or mismatched response hash', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: new Headers() }));
    await expect(fetchVerifiedZip('job-1', 'artifact-1', 'a'.repeat(64))).rejects.toThrow('approved artifact hash');
  });

  it.each([401, 404, 409])('preserves authentication, cross-job or stale-package rejection (%s)', async status => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({ error: { message: 'Delivery denied' } }) }));
    await expect(fetchVerifiedZip('job-1', 'artifact-1', 'a'.repeat(64))).rejects.toThrow('Delivery denied');
  });
});
