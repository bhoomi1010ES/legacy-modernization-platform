/** Fetch with the session cookie and verify the exact bytes before saving. */
export async function fetchVerifiedZip(jobId: string, artifactId: string, expectedHash: string): Promise<Blob> {
  if (!/^[a-f0-9]{64}$/i.test(expectedHash)) throw new Error('The ZIP SHA-256 is missing or invalid.');
  const response = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactId)}/download`, {
    credentials: 'include', redirect: 'error',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error?.message || `ZIP download failed (${response.status}).`);
  }
  if (response.headers.get('X-Content-SHA256')?.toLowerCase() !== expectedHash.toLowerCase()) {
    throw new Error('The downloaded ZIP does not match the approved artifact hash.');
  }
  const bytes = await response.arrayBuffer();
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), value => value.toString(16).padStart(2, '0')).join('');
  if (hash !== expectedHash.toLowerCase()) throw new Error('ZIP integrity check failed. The file was not saved.');
  return new Blob([bytes], { type: 'application/zip' });
}
