import { describe, expect, it, vi } from 'vitest'
import { ApiClient, type ApiRequester } from '../core/ApiClient'

const reply = (status: number, body = '') => ({
  ok: status >= 200 && status < 300,
  status,
  text: async () => body,
  json: async () => body ? JSON.parse(body) : undefined,
})

describe('ApiClient requester contract', () => {
  it('injects requester for every verb with URL, headers, JSON and timeout', async () => {
    const requester = vi.fn<ApiRequester>(async () => reply(200, '{"status":"ok"}'))
    const client = new ApiClient('https://example.test', 'token-value', 321, requester)
    await client.get('/api/sync/pull', { since_version: '7' }, 123, 'run-get')
    await client.post('/api/sync/push', { operations: [1] }, 234, 'run-post')
    await client.put('/config', { enabled: true })
    await client.delete('/config')
    expect(requester).toHaveBeenCalledTimes(4)
    const [getUrl, getInit] = requester.mock.calls[0]
    expect(getUrl).toBe('https://example.test/api/sync/pull?since_version=7')
    expect(getInit).toMatchObject({ method: 'GET', timeoutMs: 123 })
    expect(getInit.headers).toMatchObject({ Authorization: 'Bearer token-value', 'X-Sync-Run-Id': 'run-get' })
    expect(getInit.signal).toBeInstanceOf(AbortSignal)
    expect(requester.mock.calls.map(call => call[1].method)).toEqual(['GET', 'POST', 'PUT', 'DELETE'])
    expect(requester.mock.calls[1][1]).toMatchObject({ body: '{"operations":[1]}', timeoutMs: 234 })
  })

  it('separates body shapes, auth, server, network and timeout outcomes', async () => {
    const responses = [reply(200, '{"value":1}'), reply(200, 'plain'), reply(204), reply(403, 'private'), reply(500, 'private')]
    const requester = vi.fn<ApiRequester>(async () => responses.shift()!)
    const client = new ApiClient('https://example.test', '', 5, requester)
    expect((await client.get('/object')).data).toEqual({ value: 1 })
    expect((await client.get('/string')).data).toBe('plain')
    expect((await client.get('/empty')).data).toBeUndefined()
    expect(await client.get('/auth')).toMatchObject({ ok: false, status: 403, error: 'auth_expired' })
    expect(await client.get('/server', undefined, undefined, 'sync-server-500')).toMatchObject({ ok: false, status: 500, error: 'server_error', request_id: 'sync-server-500' })
    requester.mockRejectedValueOnce(new Error('secret network body'))
    expect(await client.get('/network', undefined, undefined, 'sync-network')).toMatchObject({ ok: false, status: 0, error: 'server_unreachable', request_id: 'sync-network' })
    requester.mockImplementationOnce((_url, init) => new Promise((_resolve, reject) => init.signal?.addEventListener('abort', () => reject(Object.assign(new Error(), { name: 'AbortError' })))))
    expect(await client.get('/timeout', undefined, 1, 'sync-timeout')).toMatchObject({ ok: false, status: 0, error: 'request_timeout', request_id: 'sync-timeout' })
  })

  it('maps current timer outcomes and keeps request bodies/header allowlisted', async () => {
    const responses = [
      reply(200, '{"status":"accepted","state":{"revision":1,"server_time":"2026-07-24 12:00:00"}}'),
      reply(409, '{"status":"conflict","error_code":"stale_timer_revision","state":{"revision":2}}'),
      reply(200, '{"status":"active","state":{"revision":2}}'),
      reply(426, '{"detail":"升级"}'),
    ]
    const requester = vi.fn<ApiRequester>(async () => responses.shift()!)
    const client = new ApiClient('https://example.test', 'token', 50, requester)

    expect((await client.commandCurrentTimer('start', {
      session_id: 's', device_id: 'pc', observed_revision: 0,
      category_id: 1, category_name: '输入', current_note: '任务', idempotency_key: 'k', user_intent_id: 'intent',
    })).code).toBe('accepted')
    const stale = await client.commandCurrentTimer('switch', {
      device_id: 'android', observed_revision: 1, category_name: '输出',
      idempotency_key: 'k2', user_intent_id: 'intent-2',
    })
    expect(stale).toMatchObject({ code: 'stale_revision', errorCode: 'stale_timer_revision', revision: 2 })
    expect((await client.readCurrentTimer()).state?.revision).toBe(2)
    expect((await client.readCurrentTimer()).code).toBe('upgrade_required')

    const [url, init] = requester.mock.calls[0]
    expect(url).toBe('https://example.test/api/timer/current/start')
    expect(init.headers).toMatchObject({
      Authorization: 'Bearer token',
      'X-MTL-Timer-State': 'timer-current-state-v1',
    })
    expect(JSON.parse(String(init.body))).toEqual({
      session_id: 's', device_id: 'pc', observed_revision: 0,
      category_id: 1, category_name: '输入', current_note: '任务',
      idempotency_key: 'k', user_intent_id: 'intent',
    })
  })

  it('sends TickTick task commands through the authenticated command endpoint', async () => {
    const requester = vi.fn<ApiRequester>(async () => reply(200, '{"request_id":"task-request","status":"confirmed","result_task_id":"provider-task"}'))
    const client = new ApiClient('https://example.test', 'token', 50, requester)
    const response = await client.commandTickTickTask({ request_id: 'task-request', operation: 'create', title: 'safe task' })
    expect(response.data).toMatchObject({ status: 'confirmed', result_task_id: 'provider-task' })
    expect(requester.mock.calls[0][0]).toBe('https://example.test/api/ticktick/tasks/commands')
    expect(requester.mock.calls[0][1].headers).toMatchObject({ Authorization: 'Bearer token', 'X-Sync-Run-Id': 'task-request' })
    expect(JSON.parse(String(requester.mock.calls[0][1].body))).toEqual({ request_id: 'task-request', operation: 'create', title: 'safe task' })
  })

})
