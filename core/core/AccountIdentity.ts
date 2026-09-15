/** 已验证账号的本地数据边界；用户名和 token 绝不参与存储键。 */
export interface AccountIdentity {
  origin: string
  userId: number
  storageKey: string
}

const fnv1a = (value: string, seed: bigint): string => {
  let hash = seed
  for (const byte of new TextEncoder().encode(value)) {
    hash ^= BigInt(byte)
    hash = BigInt.asUintN(64, hash * 0x100000001b3n)
  }
  return hash.toString(16).padStart(16, '0')
}

export function normalizeServerOrigin(value: string): string {
  const url = new URL(value.trim())
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('unsupported_server_origin')
  return url.origin.toLowerCase()
}

export function createAccountIdentity(serverOrigin: string, userId: number): AccountIdentity {
  if (!Number.isSafeInteger(userId) || userId <= 0) throw new Error('invalid_account_user_id')
  const origin = normalizeServerOrigin(serverOrigin)
  const material = `${origin}\u0000${userId}`
  const storageKey = `acct-${fnv1a(material, 0xcbf29ce484222325n)}${fnv1a(material, 0x84222325cbf29cen)}`
  return { origin, userId, storageKey }
}
