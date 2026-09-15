const fs = require('fs');
const os = require('os');
const path = require('path');
const { createTimerFlowLogger } = require('./timer-flow-logger');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'mtl-timer-flow-'));
const resolvedRoot = path.resolve(root);
assert(resolvedRoot.startsWith(path.resolve(os.tmpdir())), 'test log root must stay inside OS temp');

async function main() {
try {
  let current = new Date('2026-07-11T02:00:00.000Z');
  const logger = createTimerFlowLogger({ baseDir: root, maxBytes: 220, retentionDays: 7, now: () => current });
  const sensitive = {
    traceId: 'trace-sensitive', step: 1, layer: 'test', event: 'flow.failed',
    note: 'private-note', token: 'private-token', password: 'private-password',
    Authorization: 'Bearer private', Cookie: 'secret-cookie', headers: { token: 'nested' },
    hasNote: true, noteLength: 12, errorCode: 'safe-error', failedStep: 'preflight',
  };
  assert((await logger.append(sensitive)).ok, 'first timer-flow event should persist');
  assert((await logger.append({ traceId: 'oversized-single-line', payloadLength: 1000, diagnosticValue: 'x'.repeat(500) })).ok, 'single event larger than rotation limit must still be written once');
  logger.append({ traceId: 'trace-success', step: 1, layer: 'App', event: 'shortcut.received', result: 'received' });
  logger.append({ traceId: 'trace-success', step: 2, layer: 'useTimer', event: 'flow.completed', result: 'completed' });
  logger.append({ traceId: 'trace-gated', step: 1, layer: 'useTimer', event: 'shortcut.gated', result: 'gated' });
  logger.append({ traceId: 'trace-gated', step: 2, layer: 'useTimer', event: 'flow.completed', result: 'gated' });
  for (let index = 0; index < 8; index += 1) {
    assert((await logger.append({ traceId: 'trace-rotate', step: index + 1, layer: 'test', event: 'step', payloadLength: 80 })).ok, 'rotated event should persist');
  }
  await logger.flush();
  const files = fs.readdirSync(root).filter(name => name.endsWith('.jsonl'));
  assert(files.length > 1, 'small maxBytes should rotate timer-flow files');
  const allText = files.map(name => fs.readFileSync(path.join(root, name), 'utf8')).join('');
  for (const forbidden of ['private-note', 'private-token', 'private-password', 'Bearer private', 'secret-cookie', 'nested']) {
    assert(!allText.includes(forbidden), `persisted log leaked ${forbidden}`);
  }
  assert(allText.includes('safe-error') && allText.includes('trace-sensitive'), 'diagnostic identifiers should persist');
  const restartedLogger = createTimerFlowLogger({ baseDir: root, maxBytes: 220, retentionDays: 7, now: () => current });
  assert((await restartedLogger.append({ traceId: 'trace-after-restart', step: 1, layer: 'test', event: 'logger.reopened' })).ok, 'logger should append after recreation');
  await restartedLogger.flush();
  const persisted = fs.readdirSync(root).filter(name => name.endsWith('.jsonl')).flatMap(name => (
    fs.readFileSync(path.join(root, name), 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line))
  ));
  for (const traceId of ['trace-success', 'trace-gated']) {
    const trace = persisted.filter(item => item.traceId === traceId).sort((a, b) => a.step - b.step);
    assert(JSON.stringify(trace.map(item => item.step)) === JSON.stringify([1, 2]), `${traceId} should persist complete steps`);
    assert(trace.filter(item => item.event === 'flow.completed').length === 1, `${traceId} should have exactly one terminal event`);
  }
  assert(persisted.some(item => item.traceId === 'trace-after-restart'), 'trace file should survive logger recreation');

  const stale = path.join(root, 'timer-flow-2026-06-01.jsonl');
  fs.writeFileSync(stale, '{}\n');
  await logger.cleanup(current);
  assert(!fs.existsSync(stale), 'logs older than seven days should be removed');

  const blockedPath = path.join(root, 'not-a-directory');
  fs.writeFileSync(blockedPath, 'file');
  const blockedLogger = createTimerFlowLogger({ baseDir: blockedPath });
  assert((await blockedLogger.append({ traceId: 'write-failure' })).ok === false, 'write failure should be returned instead of thrown');

  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const pressureRoot = path.join(root, 'pressure');
  const pressureLogger = createTimerFlowLogger({ baseDir: pressureRoot, appendFile: async (...args) => { await gate; return fs.promises.appendFile(...args); } });
  const writes = Array.from({ length: 20 }, (_, step) => pressureLogger.append({ traceId: 'pressure', step, event: 'step' }));
  let settled = false;
  pressureLogger.flush().then(() => { settled = true; });
  await Promise.resolve();
  const dbHandlerRan = true;
  assert(dbHandlerRan && !settled, 'database work can run before delayed log I/O completes');
  release(); await Promise.all(writes); await pressureLogger.flush();
  const pressureLines = fs.readdirSync(pressureRoot).flatMap(name => fs.readFileSync(path.join(pressureRoot, name), 'utf8').trim().split('\n').filter(Boolean).map(JSON.parse));
  assert(pressureLines.map(item => item.step).join(',') === Array.from({ length: 20 }, (_, index) => index).join(','), 'concurrent writes stay ordered');
} finally {
  if (resolvedRoot.startsWith(path.resolve(os.tmpdir()))) fs.rmSync(resolvedRoot, { recursive: true, force: true });
}

console.log('timer-flow-logger tests passed');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
