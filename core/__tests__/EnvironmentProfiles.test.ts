import { describe, expect, it, vi } from 'vitest'
import { androidSmokeResidueWrites, deriveProfileConnectionStatus, environmentKey, migrateEnvironmentConfig, readActiveEnvironmentRuntimeConfig, readEnvironmentProfile, requireActiveEnvironmentRuntimeConfig } from '../core/EnvironmentProfiles'

describe('EnvironmentProfiles', () => {
  it('migrates missing testing profile from legacy keys without overwriting existing values', () => {
    const cfg = {
      active_environment: 'development',
      testing_server_url: 'https://testing.example.com',
      testing_username: 'old-user',
      testing_auth_token: 'example-old-token',
      [environmentKey('testing', 'username')]: 'new-user',
    }

    const writes = migrateEnvironmentConfig(cfg)

    expect(writes[environmentKey('testing', 'server_url')]).toBe('https://testing.example.com')
    expect(writes[environmentKey('testing', 'auth_token')]).toBe('example-old-token')
    expect(writes[environmentKey('testing', 'username')]).toBeUndefined()
  })

  it('normalizes only the legacy local development endpoint to port 8000', () => {
    const devUrl = environmentKey('development', 'server_url')
    expect(migrateEnvironmentConfig({})[devUrl]).toBe('http://127.0.0.1:8000')
    expect(migrateEnvironmentConfig({ [devUrl]: 'http://127.0.0.1:18010/' })[devUrl]).toBe('http://127.0.0.1:8000')
    for (const value of ['https://example.test', 'https://example.com', 'http://127.0.0.1:18011']) {
      expect(migrateEnvironmentConfig({ [devUrl]: value })[devUrl]).toBeUndefined()
    }
    const migrated = { [devUrl]: 'http://127.0.0.1:8000' }
    expect(migrateEnvironmentConfig({ ...migrated, ...migrateEnvironmentConfig(migrated) })).toEqual({})
  })

  it('clears Android smoke identity only when paired with the legacy endpoint', () => {
    const urlKey = environmentKey('development', 'server_url')
    const userKey = environmentKey('development', 'username')
    const tokenKey = environmentKey('development', 'auth_token')
    const paired = { [urlKey]: 'http://127.0.0.1:18010', [userKey]: 'android_smoke_20260717', [tokenKey]: 'token' }
    expect(androidSmokeResidueWrites(paired)).toEqual({ [userKey]: '', [tokenKey]: '' })
    expect(androidSmokeResidueWrites({ ...paired, [urlKey]: 'http://127.0.0.1:8000' })).toEqual({})
    expect(androidSmokeResidueWrites({ ...paired, [userKey]: 'real-user' })).toEqual({})
    expect(androidSmokeResidueWrites({ ...paired, [environmentKey('testing', 'username')]: 'keep-me' }))
      .toEqual({ [userKey]: '', [tokenKey]: '' })
  })

  it('keeps testing profile visible from scoped keys', () => {
    const cfg = {
      [environmentKey('testing', 'server_url')]: 'https://testing.example.com',
      [environmentKey('testing', 'username')]: 'tester',
      [environmentKey('testing', 'auth_token')]: 'example-secret-token',
    }

    expect(readEnvironmentProfile(cfg, 'testing')).toEqual({
      serverUrl: 'https://testing.example.com',
      username: 'tester',
      authToken: 'example-secret-token',
      verifiedUserId: '',
    })
  })

  it('does not mark a token-only profile as connected before its user id is verified', () => {
    expect(deriveProfileConnectionStatus({ serverUrl: 'https://testing.example.com', authToken: 'token' }, true, 'connected')).toBe('unconfigured')
    expect(deriveProfileConnectionStatus({ serverUrl: 'https://testing.example.com', authToken: 'token', verifiedUserId: '9' }, true, 'connected')).toBe('connected')
  })

  it('reads runtime config from active profile first', () => {
    const cfg = {
      active_environment: 'testing',
      server_url: 'https://legacy.example.com',
      auth_token: 'example-legacy-token',
      [environmentKey('testing', 'server_url')]: 'https://testing.example.com',
      [environmentKey('testing', 'auth_token')]: 'example-testing-token',
    }

    expect(readActiveEnvironmentRuntimeConfig(cfg)).toEqual({
      environment: 'testing',
      serverUrl: 'https://testing.example.com',
      authToken: 'example-testing-token',
    })
  })

  it('does not fall back to legacy runtime config when active profile is incomplete', () => {
    const cfg = { active_environment: 'production', server_url: 'https://legacy.example.com', auth_token: 'example-legacy-token' }

    expect(readActiveEnvironmentRuntimeConfig(cfg)).toEqual({
      environment: 'production',
      serverUrl: '',
      authToken: '',
    })
  })

  it('throws and logs when required active profile runtime config is missing', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const cfg = { active_environment: 'production', server_url: 'https://legacy.example.com', auth_token: 'legacy-token' }

    expect(() => requireActiveEnvironmentRuntimeConfig(cfg, 'test')).toThrow('production 环境缺少server_url、auth_token')
    expect(errorSpy).toHaveBeenCalledWith(
      '[EnvironmentProfiles] active environment runtime config missing',
      { source: 'test', environment: 'production', missing: ['server_url', 'auth_token'] },
    )
    errorSpy.mockRestore()
  })

  it('returns empty runtime config when no active profile or legacy config exists', () => {
    expect(readActiveEnvironmentRuntimeConfig({ active_environment: 'development' })).toEqual({
      environment: 'development',
      serverUrl: '',
      authToken: '',
    })
  })
})
