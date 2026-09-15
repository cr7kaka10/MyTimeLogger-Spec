const fs = require('fs')
const path = require('path')

const safeKey = (value) => {
  if (!/^acct-[a-f0-9]{32}$/i.test(String(value))) throw new Error('invalid_account_storage_key')
  return String(value).toLowerCase()
}

function accountDatabasePath(dataDir, storageKey) {
  return path.join(dataDir, 'accounts', `${safeKey(storageKey)}.db`)
}

function uniqueQuarantinePath(quarantineDir, source) {
  const stem = path.basename(source, path.extname(source)).replace(/[^a-z0-9_-]/gi, '_')
  let suffix = 0
  let target
  do {
    target = path.join(quarantineDir, `${stem}-unknown${suffix ? `-${suffix}` : ''}.db`)
    suffix += 1
  } while (fs.existsSync(target))
  return target
}

function isolateSharedDatabases(dataDir, candidates) {
  const quarantineDir = path.join(dataDir, 'quarantine', 'unknown-account')
  const moved = []
  for (const candidate of new Set(candidates.map(value => path.resolve(value)))) {
    if (!fs.existsSync(candidate)) continue
    fs.mkdirSync(quarantineDir, { recursive: true })
    const target = uniqueQuarantinePath(quarantineDir, candidate)
    for (const suffix of ['', '-wal', '-shm']) {
      if (fs.existsSync(`${candidate}${suffix}`)) fs.renameSync(`${candidate}${suffix}`, `${target}${suffix}`)
    }
    moved.push(target)
  }
  return moved
}

module.exports = { accountDatabasePath, isolateSharedDatabases }
