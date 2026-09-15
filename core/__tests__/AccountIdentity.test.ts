import { describe, expect, it } from 'vitest'
import { createAccountIdentity, normalizeServerOrigin } from '../core/AccountIdentity'

describe('AccountIdentity', () => {
  it('normalizes an HTTP(S) origin without accepting a path as identity', () => {
    expect(normalizeServerOrigin(' HTTPS://Example.COM:443/api/ ')).toBe('https://example.com')
    expect(() => normalizeServerOrigin('file:///local')).toThrow('unsupported_server_origin')
  })

  it('derives a stable key from origin and verified user id only', () => {
    const a = createAccountIdentity('https://server.example/api', 7)
    expect(a.storageKey).toBe(createAccountIdentity('https://SERVER.example', 7).storageKey)
    expect(a.storageKey).not.toBe(createAccountIdentity('https://other.example', 7).storageKey)
    expect(a.storageKey).not.toBe(createAccountIdentity('https://server.example', 8).storageKey)
    expect(a.storageKey).not.toContain('username')
    expect(a.storageKey).not.toContain('server.example')
  })
})
