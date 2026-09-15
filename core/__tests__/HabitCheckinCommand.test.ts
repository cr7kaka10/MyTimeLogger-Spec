import { describe, expect, it, vi } from 'vitest'
import { ApiClient, type ApiRequester } from '../core/ApiClient'

const reply = (status: number, body = '') => ({ ok: status >= 200 && status < 300, status, text: async () => body })

describe('habit checkin command client contract', () => {
  it('sends the stable idempotency key to the server command endpoint', async () => {
    const requester = vi.fn<ApiRequester>(async () => reply(200, '{"idempotency_key":"habit-request","status":"confirmed"}'))
    const client = new ApiClient('https://example.test', 'token', 50, requester)
    const response = await client.commandHabitCheckin({ habit_id: 'ticktick:1:h1', date: '2026-08-01', desired_status: 0, idempotency_key: 'habit-request' })
    expect(response.data).toMatchObject({ status: 'confirmed' })
    expect(requester.mock.calls[0][0]).toBe('https://example.test/api/habits/checkin-commands')
    expect(requester.mock.calls[0][1]?.headers).toMatchObject({ Authorization: 'Bearer token', 'X-Sync-Run-Id': 'habit-request' })
    expect(JSON.parse(String(requester.mock.calls[0][1]?.body))).toMatchObject({
      habit_id: 'ticktick:1:h1',
      date: '2026-08-01',
      desired_status: 0,
      idempotency_key: 'habit-request',
    })
  })

})
