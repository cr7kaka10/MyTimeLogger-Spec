const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')
const { accountDatabasePath, isolateSharedDatabases } = require('./account-storage')

test('account database paths never reuse an unknown shared database', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'mtl-isolation-'))
  try {
    const shared = path.join(root, 'my_time_logger.db')
    fs.writeFileSync(shared, 'old-account-data')
    fs.writeFileSync(`${shared}-wal`, 'uncheckpointed-data')
    const moved = isolateSharedDatabases(root, [shared])
    const accountA = accountDatabasePath(root, 'acct-0123456789abcdef0123456789abcdef')
    const accountB = accountDatabasePath(root, 'acct-fedcba9876543210fedcba9876543210')
    assert.equal(fs.existsSync(shared), false)
    assert.equal(moved.length, 1)
    assert.equal(fs.readFileSync(moved[0], 'utf8'), 'old-account-data')
    assert.equal(fs.readFileSync(`${moved[0]}-wal`, 'utf8'), 'uncheckpointed-data')
    assert.notEqual(accountA, accountB)
    assert.equal(fs.existsSync(accountA), false)
  } finally {
    fs.rmSync(root, { recursive: true, force: true })
  }
})
