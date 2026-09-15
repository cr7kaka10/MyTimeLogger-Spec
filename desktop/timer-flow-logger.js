const fs = require('fs');
const path = require('path');

const FILE_PATTERN = /^timer-flow-(\d{4}-\d{2}-\d{2})(?:\.(\d+))?\.jsonl$/;
const BLOCKED_KEY = /(note|summary|task|token|password|api.?key|authorization|cookie|headers?|secret|currentfocustask|error)$/i;

function beijingParts(date) {
  const text = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date);
  const [day, time] = text.split(' ');
  return { day, timestamp: `${day}T${time}+08:00` };
}

function sanitizeTimerFlowEvent(value) {
  const safe = {};
  for (const [key, raw] of Object.entries(value && typeof value === 'object' ? value : {})) {
    if (BLOCKED_KEY.test(key) && !/^(has|.*Length$|errorCode$)/i.test(key)) continue;
    if (raw === undefined || typeof raw === 'function') continue;
    if (raw === null || ['string', 'number', 'boolean'].includes(typeof raw)) safe[key] = raw;
    else if (Array.isArray(raw)) safe[key] = raw.slice(0, 20).map(item => (
      item && typeof item === 'object' ? sanitizeTimerFlowEvent(item) : item
    ));
    else safe[key] = sanitizeTimerFlowEvent(raw);
  }
  return safe;
}

function createTimerFlowLogger(options) {
  const baseDir = path.resolve(options.baseDir);
  const maxBytes = options.maxBytes || 10 * 1024 * 1024;
  const retentionDays = options.retentionDays || 7;
  const now = options.now || (() => new Date());
  const appendFile = options.appendFile || fs.promises.appendFile.bind(fs.promises);
  let tail = Promise.resolve();
  let cleanedDay = '';

  async function cleanup(reference = now()) {
    await fs.promises.mkdir(baseDir, { recursive: true });
    const cutoff = reference.getTime() - retentionDays * 24 * 3600 * 1000;
    for (const name of await fs.promises.readdir(baseDir)) {
      const match = FILE_PATTERN.exec(name);
      if (!match) continue;
      const fileDay = new Date(`${match[1]}T00:00:00+08:00`).getTime();
      const target = path.resolve(baseDir, name);
      if (target.startsWith(`${baseDir}${path.sep}`) && fileDay < cutoff) await fs.promises.rm(target, { force: true });
    }
  }

  async function resolveFile(day, bytes) {
    let index = 0;
    while (true) {
      const suffix = index === 0 ? '' : `.${index}`;
      const candidate = path.join(baseDir, `timer-flow-${day}${suffix}.jsonl`);
      let size = 0;
      try { size = (await fs.promises.stat(candidate)).size; } catch (error) { if (error.code !== 'ENOENT') throw error; }
      if (size === 0 || size + bytes <= maxBytes) return candidate;
      index += 1;
    }
  }

  async function write(event) {
    try {
      await fs.promises.mkdir(baseDir, { recursive: true });
      const current = now();
      const { day, timestamp } = beijingParts(current);
      if (cleanedDay !== day) { await cleanup(current); cleanedDay = day; }
      const safe = sanitizeTimerFlowEvent(event);
      const line = `${JSON.stringify({ beijingTime: safe.beijingTime || timestamp, ...safe })}\n`;
      const file = await resolveFile(day, Buffer.byteLength(line));
      await appendFile(file, line, 'utf8');
      return { ok: true, file };
    } catch (error) {
      return { ok: false, errorCode: 'timer-flow-write-failed' };
    }
  }

  function append(event) {
    const result = tail.then(() => write(event), () => write(event));
    tail = result.then(() => undefined, () => undefined);
    return result;
  }

  return { append, cleanup, flush: () => tail, sanitize: sanitizeTimerFlowEvent };
}

module.exports = { createTimerFlowLogger, sanitizeTimerFlowEvent };
