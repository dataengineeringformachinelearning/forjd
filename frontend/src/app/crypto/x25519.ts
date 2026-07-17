/**
 * Client-side X25519 ECDH + HKDF → AES-256 key (matches backend `app.core.crypto`).
 *
 * Private keys never leave the browser. Publish only public keys via
 * `POST /api/v1/sessions`. Message encryption uses `seal.ts` with the derived key.
 *
 * Forward secrecy: rotate ephemeral key pairs per Double Ratchet step; do not
 * reuse a derived AES key across ratchet generations in production clients.
 */

const HKDF_SALT = new TextEncoder().encode('forjd-e2ee-v1');

export interface X25519KeyPair {
  privateKey: CryptoKey;
  publicKey: CryptoKey;
  publicKeyRaw: Uint8Array;
  publicKeyB64: string;
}

function b64Encode(bytes: Uint8Array): string {
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]!);
  return btoa(s);
}

function b64Decode(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function asBufferSource(data: Uint8Array): BufferSource {
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

export async function generateX25519KeyPair(): Promise<X25519KeyPair> {
  const pair = await crypto.subtle.generateKey({ name: 'X25519' }, true, [
    'deriveBits',
  ]);
  const publicKeyRaw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  return {
    privateKey: pair.privateKey,
    publicKey: pair.publicKey,
    publicKeyRaw,
    publicKeyB64: b64Encode(publicKeyRaw),
  };
}

export async function importX25519PublicB64(b64: string): Promise<CryptoKey> {
  const raw = b64Decode(b64);
  if (raw.length !== 32) throw new Error('X25519 public key must be 32 bytes');
  return crypto.subtle.importKey('raw', asBufferSource(raw), { name: 'X25519' }, true, []);
}

/**
 * ECDH + HKDF-SHA256 → raw 32-byte AES key (same info/salt as Python).
 */
export async function deriveSessionKeyRaw(
  privateKey: CryptoKey,
  peerPublicKey: CryptoKey,
  sessionId: string,
): Promise<Uint8Array> {
  const shared = await crypto.subtle.deriveBits(
    { name: 'X25519', public: peerPublicKey },
    privateKey,
    256,
  );
  const info = new TextEncoder().encode(`forjd-session-v1|${sessionId}`);
  const baseKey = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: asBufferSource(HKDF_SALT),
      info: asBufferSource(info),
    },
    baseKey,
    256,
  );
  return new Uint8Array(bits);
}
