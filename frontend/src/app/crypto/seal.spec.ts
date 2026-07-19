import { deriveSessionKeyRaw, generateX25519KeyPair } from './x25519';
import { generateAesKey, openEnvelope, seal } from './seal';

describe('browser E2EE', () => {
  it('seals and opens locally while binding ciphertext to tenant and event AAD', async () => {
    const key = await generateAesKey();
    expect(key.extractable).toBe(false);
    const plaintext = 'sensitive-browser-only-value';
    const envelope = await seal(plaintext, {
      key,
      keyId: 'browser-test',
      tenantId: 'tenant-a',
      clientEventId: 'event-a',
    });

    expect(envelope.algo).toBe('aes-256-gcm');
    expect(envelope.ciphertextSha256).toMatch(/^[a-f0-9]{64}$/);
    expect(JSON.stringify(envelope)).not.toContain(plaintext);
    const opened = await openEnvelope(envelope, {
      key,
      tenantId: 'tenant-a',
      clientEventId: 'event-a',
    });
    expect(new TextDecoder().decode(opened)).toBe(plaintext);
    await expect(
      openEnvelope(envelope, { key, tenantId: 'tenant-b', clientEventId: 'event-a' }),
    ).rejects.toBeTruthy();
  });

  it('derives the same ephemeral session key on both X25519 peers', async () => {
    const alice = await generateX25519KeyPair();
    const bob = await generateX25519KeyPair();
    expect(alice.privateKey.extractable).toBe(false);
    expect(bob.privateKey.extractable).toBe(false);
    const aliceKey = await deriveSessionKeyRaw(alice.privateKey, bob.publicKey, 'session-a');
    const bobKey = await deriveSessionKeyRaw(bob.privateKey, alice.publicKey, 'session-a');
    expect([...aliceKey]).toEqual([...bobKey]);
    aliceKey.fill(0);
    bobKey.fill(0);
  });
});
