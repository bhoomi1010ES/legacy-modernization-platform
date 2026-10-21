/**
 * Browser-Native Local Source Scanner.
 * 
 * Provides safe, client-side directory traversal using the File System Access API
 * (window.showDirectoryPicker) with universal fallback to <input type="file" webkitdirectory>.
 * 
 * Enforces:
 * 1. Zero code execution (strictly static inspection).
 * 2. Strict exclusions: .git, node_modules, .venv, build, dist, and secrets (.env*, *.pem, *.key, id_rsa).
 * 3. Configurable bounds: depth <= 10, files <= 15,000, per-file <= 2MB for manifests, total <= 50MB preview.
 * 4. Deterministic Canonical Snapshot Fingerprint matching backend specification.
 * 5. Lightweight, self-contained ZIP bundle packaging for streaming upload.
 */

export interface ScanProgress {
  totalScanned: number;
  eligibleFiles: number;
  totalBytes: number;
  currentPath: string;
  isComplete: boolean;
  warnings: string[];
}

export interface ScannedFile {
  relativePath: string;
  size: number;
  content: Uint8Array;
}

export interface LocalScanResult {
  sourceName: string;
  files: ScannedFile[];
  canonicalFingerprint: string;
  totalBytes: number;
  fileCount: number;
  isComplete: boolean;
  warnings: string[];
  bundleZip: Blob;
}

export const EXCLUDED_DIRS = new Set([
  '.git',
  'node_modules',
  '.venv',
  'venv',
  'env',
  '.env',
  'dist',
  'build',
  'target',
  '.build',
  'vendor',
  '__pycache__',
  '.pytest_cache',
  '.mypy_cache',
  '.tox',
  '.idea',
  '.vscode',
  '.gradle',
  'bin',
  'obj',
  'out',
  'coverage',
  '.next',
  '.nuxt',
]);

export const SENSITIVE_PATTERNS = [
  /^\.env(\..+)?$/i,
  /\.pem$/i,
  /\.key$/i,
  /^id_rsa/i,
  /\.pfx$/i,
  /\.keystore$/i,
  /\.p12$/i,
  /\.credentials$/i,
  /secrets\.json$/i,
];

export const MAX_DEPTH = 10;
export const MAX_FILES = 15000;
export const MAX_FILE_BYTES = 2 * 1024 * 1024;      // 2 MB per file for preview
export const MAX_TOTAL_BYTES = 50 * 1024 * 1024;   // 50 MB total preview bundle

/** Feature detection for File System Access API */
export function isFileSystemAccessSupported(): boolean {
  return typeof window !== 'undefined' && typeof (window as any).showDirectoryPicker === 'function';
}

function isSensitiveFile(filename: string): boolean {
  return SENSITIVE_PATTERNS.some((pattern) => pattern.test(filename));
}

// CRC32 Table
const crcTable = new Uint32Array(256);
for (let i = 0; i < 256; i++) {
  let c = i;
  for (let k = 0; k < 8; k++) {
    c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  }
  crcTable[i] = c;
}

function crc32(buf: Uint8Array): number {
  let crc = -1;
  for (let i = 0; i < buf.length; i++) {
    crc = (crc >>> 8) ^ crcTable[(crc ^ buf[i]) & 0xff];
  }
  return (crc ^ -1) >>> 0;
}

/**
 * Builds a valid, uncompressed (STORE) ZIP archive Blob in pure TypeScript.
 * Compatible with standard unzip and Python zipfile.
 */
export function buildZipBundle(files: ScannedFile[]): Blob {
  const fileRecords: Array<{
    nameBytes: Uint8Array;
    content: Uint8Array;
    crc: number;
    offset: number;
  }> = [];

  const chunks: Uint8Array[] = [];
  let currentOffset = 0;

  // 1. Local File Headers + Data
  for (const f of files) {
    const nameBytes = new TextEncoder().encode(f.relativePath);
    const crc = crc32(f.content);

    const localHeader = new Uint8Array(30 + nameBytes.length);
    const view = new DataView(localHeader.buffer);

    view.setUint32(0, 0x04034b50, true);  // Local header signature
    view.setUint16(4, 20, true);          // Version needed (2.0)
    view.setUint16(6, 0, true);           // General purpose bit flag
    view.setUint16(8, 0, true);           // Compression: 0 (Store)
    view.setUint16(10, 0, true);          // Mod time
    view.setUint16(12, 0, true);          // Mod date
    view.setUint32(14, crc, true);        // CRC-32
    view.setUint32(18, f.size, true);     // Compressed size
    view.setUint32(22, f.size, true);     // Uncompressed size
    view.setUint16(26, nameBytes.length, true); // Name length
    view.setUint16(28, 0, true);          // Extra field length
    localHeader.set(nameBytes, 30);

    chunks.push(localHeader);
    chunks.push(f.content);

    fileRecords.push({
      nameBytes,
      content: f.content,
      crc,
      offset: currentOffset,
    });

    currentOffset += localHeader.length + f.content.length;
  }

  // 2. Central Directory
  const centralDirStart = currentOffset;
  for (const r of fileRecords) {
    const cdHeader = new Uint8Array(46 + r.nameBytes.length);
    const view = new DataView(cdHeader.buffer);

    view.setUint32(0, 0x02014b50, true);  // Central dir signature
    view.setUint16(4, 20, true);          // Version made by
    view.setUint16(6, 20, true);          // Version needed
    view.setUint16(8, 0, true);           // Bit flag
    view.setUint16(10, 0, true);          // Compression: Store
    view.setUint16(12, 0, true);          // Mod time
    view.setUint16(14, 0, true);          // Mod date
    view.setUint32(16, r.crc, true);      // CRC-32
    view.setUint32(20, r.content.length, true); // Compressed size
    view.setUint32(24, r.content.length, true); // Uncompressed size
    view.setUint16(28, r.nameBytes.length, true); // Name length
    view.setUint16(30, 0, true);          // Extra field length
    view.setUint16(32, 0, true);          // Comment length
    view.setUint16(34, 0, true);          // Disk start
    view.setUint16(36, 0, true);          // Internal attributes
    view.setUint32(38, 0x81a40000, true); // External attributes (0644 regular file)
    view.setUint32(42, r.offset, true);   // Local header offset
    cdHeader.set(r.nameBytes, 46);

    chunks.push(cdHeader);
    currentOffset += cdHeader.length;
  }

  const centralDirSize = currentOffset - centralDirStart;

  // 3. End of Central Directory
  const eocd = new Uint8Array(22);
  const eocdView = new DataView(eocd.buffer);
  eocdView.setUint32(0, 0x06054b50, true);     // EOCD signature
  eocdView.setUint16(4, 0, true);              // Disk number
  eocdView.setUint16(6, 0, true);              // Disk with CD
  eocdView.setUint16(8, files.length, true);   // Entries on this disk
  eocdView.setUint16(10, files.length, true);  // Total entries
  eocdView.setUint32(12, centralDirSize, true);// Central dir size
  eocdView.setUint32(16, centralDirStart, true); // Central dir offset
  eocdView.setUint16(20, 0, true);             // Comment length

  chunks.push(eocd);

  return new Blob(chunks as unknown as BlobPart[], { type: 'application/zip' });
}

/**
 * Calculates the canonical Merkle fingerprint matching backend specification.
 */
export async function calculateCanonicalFingerprint(files: ScannedFile[]): Promise<string> {
  const encoder = new TextEncoder();
  const entryLines: Array<{ relPath: string; lineBytes: Uint8Array }> = [];

  for (const f of files) {
    const hashBuf = await crypto.subtle.digest('SHA-256', f.content as unknown as BufferSource);
    const hashArray = Array.from(new Uint8Array(hashBuf));
    const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');

    const lineStr = `${f.relativePath}\0${f.size}\0${hashHex}\n`;
    entryLines.push({
      relPath: f.relativePath,
      lineBytes: encoder.encode(lineStr),
    });
  }

  // Sort ascending by relative path
  entryLines.sort((a, b) => (a.relPath < b.relPath ? -1 : a.relPath > b.relPath ? 1 : 0));

  // Compute overall SHA-256
  const totalLength = entryLines.reduce((acc, cur) => acc + cur.lineBytes.length, 0);
  const concatenated = new Uint8Array(totalLength);
  let pos = 0;
  for (const e of entryLines) {
    concatenated.set(e.lineBytes, pos);
    pos += e.lineBytes.length;
  }

  const finalHashBuf = await crypto.subtle.digest('SHA-256', concatenated as unknown as BufferSource);
  const finalArray = Array.from(new Uint8Array(finalHashBuf));
  return finalArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Traverses a FileSystemDirectoryHandle recursively.
 */
async function walkDirectoryHandle(
  dirHandle: any,
  currentRelPath: string,
  depth: number,
  state: {
    scannedCount: number;
    totalBytes: number;
    files: ScannedFile[];
    warnings: string[];
    isComplete: boolean;
  },
  onProgress?: (p: ScanProgress) => void,
  signal?: AbortSignal
): Promise<void> {
  if (signal?.aborted) throw new DOMException('Scan cancelled by user', 'AbortError');

  if (depth > MAX_DEPTH) {
    state.warnings.push(`Traversal depth limit (${MAX_DEPTH}) reached at '${currentRelPath}'. Subdirectories skipped.`);
    state.isComplete = false;
    return;
  }

  for await (const entry of dirHandle.values()) {
    if (signal?.aborted) throw new DOMException('Scan cancelled by user', 'AbortError');

    state.scannedCount++;
    const entryName: string = entry.name;
    const relPath = currentRelPath ? `${currentRelPath}/${entryName}` : entryName;

    if (entry.kind === 'directory') {
      if (EXCLUDED_DIRS.has(entryName) || entryName.startsWith('.')) {
        continue;
      }
      await walkDirectoryHandle(entry, relPath, depth + 1, state, onProgress, signal);
    } else if (entry.kind === 'file') {
      if (isSensitiveFile(entryName)) {
        state.warnings.push(`Sensitive file skipped for security: '${relPath}'.`);
        continue;
      }

      if (state.files.length >= MAX_FILES) {
        state.warnings.push(`Maximum file limit (${MAX_FILES}) reached. Remaining files skipped.`);
        state.isComplete = false;
        return;
      }

      try {
        const fileObj: File = await entry.getFile();
        if (fileObj.size > MAX_FILE_BYTES) {
          state.warnings.push(`File '${relPath}' exceeds inspectable size (2 MB) and was skipped.`);
          state.isComplete = false;
          continue;
        }

        if (state.totalBytes + fileObj.size > MAX_TOTAL_BYTES) {
          state.warnings.push(`Total preview size ceiling (50 MB) reached. Scan is partial.`);
          state.isComplete = false;
          return;
        }

        const arrayBuf = await fileObj.arrayBuffer();
        const content = new Uint8Array(arrayBuf);

        state.files.push({
          relativePath: relPath,
          size: fileObj.size,
          content,
        });
        state.totalBytes += fileObj.size;

        if (onProgress && state.files.length % 20 === 0) {
          onProgress({
            totalScanned: state.scannedCount,
            eligibleFiles: state.files.length,
            totalBytes: state.totalBytes,
            currentPath: relPath,
            isComplete: state.isComplete,
            warnings: state.warnings,
          });
        }
      } catch (err: any) {
        state.warnings.push(`Could not read '${relPath}': ${err.message || 'Permission denied'}`);
      }
    }
  }
}

/**
 * Initiates user directory selection via File System Access API.
 */
export async function scanWithDirectoryPicker(
  onProgress?: (p: ScanProgress) => void,
  signal?: AbortSignal
): Promise<LocalScanResult> {
  if (!isFileSystemAccessSupported()) {
    throw new Error('File System Access API is not supported in this browser.');
  }

  // Must be called from user gesture
  const dirHandle = await (window as any).showDirectoryPicker({
    mode: 'read',
  });

  const sourceName = dirHandle.name || 'local-project';
  const state = {
    scannedCount: 0,
    totalBytes: 0,
    files: [] as ScannedFile[],
    warnings: [] as string[],
    isComplete: true,
  };

  await walkDirectoryHandle(dirHandle, '', 1, state, onProgress, signal);

  if (onProgress) {
    onProgress({
      totalScanned: state.scannedCount,
      eligibleFiles: state.files.length,
      totalBytes: state.totalBytes,
      currentPath: 'Packaging bundle...',
      isComplete: state.isComplete,
      warnings: state.warnings,
    });
  }

  const canonicalFingerprint = await calculateCanonicalFingerprint(state.files);
  const bundleZip = buildZipBundle(state.files);

  return {
    sourceName,
    files: state.files,
    canonicalFingerprint,
    totalBytes: state.totalBytes,
    fileCount: state.files.length,
    isComplete: state.isComplete,
    warnings: state.warnings,
    bundleZip,
  };
}

/**
 * Fallback directory scanner from <input type="file" webkitdirectory>.
 */
export async function scanWithFileList(
  fileList: FileList | File[],
  sourceNameFallback = 'local-project',
  onProgress?: (p: ScanProgress) => void,
  signal?: AbortSignal
): Promise<LocalScanResult> {
  const files: ScannedFile[] = [];
  const warnings: string[] = [];
  let totalBytes = 0;
  let isComplete = true;

  const filesArray = Array.from(fileList);
  let inferredRootName = sourceNameFallback;

  for (let i = 0; i < filesArray.length; i++) {
    if (signal?.aborted) throw new DOMException('Scan cancelled by user', 'AbortError');

    const file = filesArray[i];
    const fullPath = (file as any).webkitRelativePath || file.name;
    const parts: string[] = String(fullPath).split('/').filter(Boolean);

    if (parts.length > 1 && inferredRootName === sourceNameFallback) {
      inferredRootName = parts[0];
    }

    // Remove root folder from relative path if present
    const relativeParts = parts.length > 1 ? parts.slice(1) : parts;
    const relPath = relativeParts.join('/');

    if (relativeParts.length > MAX_DEPTH) {
      warnings.push(`Depth limit exceeded at '${relPath}'. Skipped.`);
      isComplete = false;
      continue;
    }

    if (relativeParts.some((p: string) => EXCLUDED_DIRS.has(p) || p.startsWith('.'))) {
      continue;
    }

    if (isSensitiveFile(file.name)) {
      warnings.push(`Sensitive file skipped: '${relPath}'.`);
      continue;
    }

    if (files.length >= MAX_FILES) {
      warnings.push(`Maximum file limit (${MAX_FILES}) reached.`);
      isComplete = false;
      break;
    }

    if (file.size > MAX_FILE_BYTES) {
      warnings.push(`File '${relPath}' exceeds 2 MB limit and was skipped.`);
      isComplete = false;
      continue;
    }

    if (totalBytes + file.size > MAX_TOTAL_BYTES) {
      warnings.push(`Total preview size ceiling (50 MB) reached.`);
      isComplete = false;
      break;
    }

    const arrayBuf = await file.arrayBuffer();
    const content = new Uint8Array(arrayBuf);

    files.push({
      relativePath: relPath,
      size: file.size,
      content,
    });
    totalBytes += file.size;

    if (onProgress && i % 25 === 0) {
      onProgress({
        totalScanned: i + 1,
        eligibleFiles: files.length,
        totalBytes,
        currentPath: relPath,
        isComplete,
        warnings,
      });
    }
  }

  const canonicalFingerprint = await calculateCanonicalFingerprint(files);
  const bundleZip = buildZipBundle(files);

  return {
    sourceName: inferredRootName,
    files,
    canonicalFingerprint,
    totalBytes,
    fileCount: files.length,
    isComplete,
    warnings,
    bundleZip,
  };
}
