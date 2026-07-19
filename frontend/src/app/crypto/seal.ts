/**
 * Client-side AES-256-GCM sealing matching backend `app.core.crypto`.
 * Private keys and plaintext remain in the browser; FORJD receives only the envelope.
 */

export const ALGO_AES_256_GCM = 'aes-256-gcm';

// --- Wire types ---
export interface SealedEnvelope {
  algo: string;
  keyId: string;
  nonce: string;
  ciphertext: string;
  ratchetHeader: string | null;
  ciphertextSha256: string;
}

// --- Encoding and hashing ---
function b64Encode(bytes: ArrayBuffer | Uint8Array): string {
  const value = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let binary = '';
  for (const byte of value) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function b64Decode(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function sha256Hex(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', asBufferSource(data));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function asBufferSource(data: Uint8Array): BufferSource {
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

// --- AAD and AES key helpers ---
export function associatedData(tenantId: string, clientEventId: string): Uint8Array {
  return new TextEncoder().encode(`${tenantId}|${clientEventId}`);
}

export async function generateAesKey(): Promise<CryptoKey> {
  return crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
}

export async function importAesKeyRaw(raw: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey('raw', asBufferSource(raw), { name: 'AES-GCM' }, false, [
    'encrypt',
    'decrypt',
  ]);
}

// --- Sealing boundary ---
export async function seal(
  plaintext: string | Uint8Array,
  opts: {
    key: CryptoKey;
    keyId: string;
    tenantId: string;
    clientEventId: string;
    ratchetHeader?: string | null;
  },
): Promise<SealedEnvelope> {
  const data =
    typeof plaintext === 'string' ? new TextEncoder().encode(plaintext) : new Uint8Array(plaintext);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const aad = associatedData(opts.tenantId, opts.clientEventId);
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: asBufferSource(nonce),
        additionalData: asBufferSource(aad),
        tagLength: 128,
      },
      opts.key,
      asBufferSource(data),
    ),
  );
  return {
    algo: ALGO_AES_256_GCM,
    keyId: opts.keyId,
    nonce: b64Encode(nonce),
    ciphertext: b64Encode(ciphertext),
    ratchetHeader: opts.ratchetHeader ?? null,
    ciphertextSha256: await sha256Hex(ciphertext),
  };
}

/** Browser-only test/demo open path. The server never calls or receives key material from it. */
export async function openEnvelope(
  envelope: SealedEnvelope,
  opts: { key: CryptoKey; tenantId: string; clientEventId: string },
): Promise<Uint8Array> {
  const plaintext = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: asBufferSource(b64Decode(envelope.nonce)),
      additionalData: asBufferSource(associatedData(opts.tenantId, opts.clientEventId)),
      tagLength: 128,
    },
    opts.key,
    asBufferSource(b64Decode(envelope.ciphertext)),
  );
  return new Uint8Array(plaintext);
}
