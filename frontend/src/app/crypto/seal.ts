/**
 * Client-side AES-256-GCM seal matching backend `app.core.crypto`.
 *
 * AAD = `${tenantId}|${clientEventId}` (UTF-8).
 * Double Ratchet headers are opaque base64 placeholders until a full Signal
 * stack lands — clients own key material; the API never decrypts.
 */

export const ALGO_AES_256_GCM = 'aes-256-gcm';

export interface SealedEnvelope {
  algo: string;
  keyId: string;
  nonce: string;
  ciphertext: string;
  ratchetHeader: string | null;
  ciphertextSha256: string;
}

function b64Encode(bytes: ArrayBuffer | Uint8Array): string {
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = '';
  for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]!);
  return btoa(s);
}

function b64Decode(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function sha256Hex(data: Uint8Array): Promise<string> {
  const copy = new Uint8Array(data);
  const digest = await crypto.subtle.digest('SHA-256', copy);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function asBufferSource(data: Uint8Array): BufferSource {
  // TS 6 / DOM lib: narrow away SharedArrayBuffer-backed views.
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

export function associatedData(tenantId: string, clientEventId: string): Uint8Array {
  return new TextEncoder().encode(`${tenantId}|${clientEventId}`);
}

export async function generateAesKey(): Promise<CryptoKey> {
  return crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, [
    'encrypt',
    'decrypt',
  ]);
}

export async function importAesKeyRaw(raw: Uint8Array): Promise<CryptoKey> {
  const copy = new Uint8Array(raw);
  return crypto.subtle.importKey('raw', copy, { name: 'AES-GCM' }, false, [
    'encrypt',
    'decrypt',
  ]);
}

export async function exportAesKeyRaw(key: CryptoKey): Promise<Uint8Array> {
  return new Uint8Array(await crypto.subtle.exportKey('raw', key));
}

/**
 * Seal plaintext for FORJD ingest. `ratchetHeader` is opaque (base64); pass a
 * client-generated ratchet blob or a PoC placeholder.
 */
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
  const ct = new Uint8Array(
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
    ciphertext: b64Encode(ct),
    ratchetHeader: opts.ratchetHeader ?? null,
    ciphertextSha256: await sha256Hex(ct),
  };
}

/** Local decrypt for demos — never used by the server E2EE path. */
export async function openEnvelope(
  envelope: SealedEnvelope,
  opts: { key: CryptoKey; tenantId: string; clientEventId: string },
): Promise<Uint8Array> {
  const nonce = b64Decode(envelope.nonce);
  const ct = b64Decode(envelope.ciphertext);
  const aad = associatedData(opts.tenantId, opts.clientEventId);
  const pt = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: asBufferSource(nonce),
      additionalData: asBufferSource(aad),
      tagLength: 128,
    },
    opts.key,
    asBufferSource(ct),
  );
  return new Uint8Array(pt);
}
