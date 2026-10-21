import { describe, it, expect } from 'vitest';
import {
  buildZipBundle,
  calculateCanonicalFingerprint,
  scanWithFileList,
  EXCLUDED_DIRS,
  MAX_DEPTH,
} from '../services/localSourceScanner';

describe('LocalSourceScanner', () => {
  it('should build a valid ZIP bundle with proper ZIP signatures', async () => {
    const files = [
      {
        relativePath: 'package.json',
        size: 25,
        content: new TextEncoder().encode('{"name": "test-project"}'),
      },
      {
        relativePath: 'src/index.ts',
        size: 19,
        content: new TextEncoder().encode('console.log("hi");'),
      },
    ];

    const zipBlob = buildZipBundle(files);
    expect(zipBlob.type).toBe('application/zip');
    expect(zipBlob.size).toBeGreaterThan(0);

    const buffer = await zipBlob.arrayBuffer();
    const view = new DataView(buffer);
    // Standard ZIP local header signature 0x04034b50
    expect(view.getUint32(0, true)).toBe(0x04034b50);
  });

  it('should compute deterministic canonical Merkle fingerprints independent of file order', async () => {
    const fileA = {
      relativePath: 'src/a.ts',
      size: 5,
      content: new TextEncoder().encode('alpha'),
    };
    const fileB = {
      relativePath: 'src/b.ts',
      size: 4,
      content: new TextEncoder().encode('beta'),
    };

    const fp1 = await calculateCanonicalFingerprint([fileA, fileB]);
    const fp2 = await calculateCanonicalFingerprint([fileB, fileA]);

    expect(fp1).toHaveLength(64);
    expect(fp1).toBe(fp2);
  });

  it('should filter out .git, node_modules, and sensitive credential files', async () => {
    const mockFiles: File[] = [
      new File(['console.log(1)'], 'src/main.js'),
      new File(['git-internals'], '.git/HEAD'),
      new File(['dep-code'], 'node_modules/express/index.js'),
      new File(['SECRET=123'], '.env'),
      new File(['PRIVATE KEY'], 'server.key'),
      new File(['CERTIFICATE'], 'cert.pem'),
    ];

    // Mock webkitRelativePath
    Object.defineProperty(mockFiles[0], 'webkitRelativePath', { value: 'my-app/src/main.js' });
    Object.defineProperty(mockFiles[1], 'webkitRelativePath', { value: 'my-app/.git/HEAD' });
    Object.defineProperty(mockFiles[2], 'webkitRelativePath', { value: 'my-app/node_modules/express/index.js' });
    Object.defineProperty(mockFiles[3], 'webkitRelativePath', { value: 'my-app/.env' });
    Object.defineProperty(mockFiles[4], 'webkitRelativePath', { value: 'my-app/server.key' });
    Object.defineProperty(mockFiles[5], 'webkitRelativePath', { value: 'my-app/cert.pem' });

    const result = await scanWithFileList(mockFiles, 'my-app');
    expect(result.sourceName).toBe('my-app');
    // Only src/main.js should be eligible
    expect(result.files).toHaveLength(1);
    expect(result.files[0].relativePath).toBe('src/main.js');
    expect(result.warnings.some((w) => w.includes('Sensitive file skipped'))).toBe(true);
  });
});
