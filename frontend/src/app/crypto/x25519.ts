/**
 * Browser X25519 ECDH + HKDF-SHA256 key derivation.
 * Private keys are non-exported from the workflow and never cross the API boundary.
 */

const HKDF_SALT = new TextEncoder().encode('forjd-e2ee-v1');

export interface X25519KeyPair {
  privateKey: CryptoKey;
  publicKey: CryptoKey;
  publicKeyRaw: Uint8Array;
  publicKeyB64: string;
}

// --- Encoding helpers ---
function b64Encode(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function b64Decode(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

function asBufferSource(data: Uint8Array): BufferSource {
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

// --- Key generation and import ---
export async function generateX25519KeyPair(): Promise<X25519KeyPair> {
  const pair = await crypto.subtle.generateKey({ name: 'X25519' }, false, ['deriveBits']);
  const publicKeyRaw = new Uint8Array(await crypto.subtle.exportKey('raw', pair.publicKey));
  return {
    privateKey: pair.privateKey,
    publicKey: pair.publicKey,
    publicKeyRaw,
    publicKeyB64: b64Encode(publicKeyRaw),
  };
}

export async function importX25519PublicB64(value: string): Promise<CryptoKey> {
  const raw = b64Decode(value);
  if (raw.length !== 32) throw new Error('X25519 public key must be 32 bytes');
  return crypto.subtle.importKey('raw', asBufferSource(raw), { name: 'X25519' }, true, []);
}

// --- ECDH + HKDF ---
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
  const baseKey = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveBits']);
  new Uint8Array(shared).fill(0);
  const bits = await crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: asBufferSource(HKDF_SALT),
      info: asBufferSource(new TextEncoder().encode(`forjd-session-v1|${sessionId}`)),
    },
    baseKey,
    256,
  );
  return new Uint8Array(bits);
}
