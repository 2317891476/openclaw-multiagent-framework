#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

function usage(code = 0) {
  const text = `Usage:
  node watcher.js --run-dir /path/to/run [--once]

Options:
  --run-dir <path>       Run directory to watch (required)
  --poll-ms <ms>         Poll interval in milliseconds (default: 2000)
  --stall-ms <ms>        Fallback no-activity threshold for old runs without stall metadata (default: 30000)
  --once                 Scan once and exit
  --help                 Show this help

Outputs:
  - Prints events to stdout
  - Appends JSONL to <run-dir>/watcher.events.jsonl
  - Persists cursor in <run-dir>/watcher.cursor.json
`;
  const out = code === 0 ? process.stdout : process.stderr;
  out.write(text);
  process.exit(code);
}

function parseArgs(argv) {
  const args = {
    pollMs: 2000,
    stallMs: 30000,
    once: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case '--run-dir':
        args.runDir = argv[++i];
        break;
      case '--poll-ms':
        args.pollMs = Number(argv[++i]);
        break;
      case '--stall-ms':
        args.stallMs = Number(argv[++i]);
        break;
      case '--once':
        args.once = true;
        break;
      case '--help':
      case '-h':
        usage(0);
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!args.runDir) {
    throw new Error('Missing required --run-dir');
  }
  if (!Number.isFinite(args.pollMs) || args.pollMs <= 0) {
    throw new Error('--poll-ms must be a positive number');
  }
  if (!Number.isFinite(args.stallMs) || args.stallMs <= 0) {
    throw new Error('--stall-ms must be a positive number');
  }
  return args;
}

function nowIso() {
  return new Date().toISOString();
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function readJson(filePath, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (_) {
    return fallback;
  }
}

function writeJson(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n');
}

function readJsonLines(filePath) {
  try {
    const text = fs.readFileSync(filePath, 'utf8');
    return text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch (_) {
    return [];
  }
}

function appendJsonl(filePath, data) {
  fs.appendFileSync(filePath, JSON.stringify(data) + '\n');
}

function humanLine(event) {
  const body = event.message || JSON.stringify(event.data || {});
  return `[${event.ts}] ${event.kind.toUpperCase()} ${body}`;
}

function pickLastActivity(status) {
  const candidates = [
    status?.lastActivityAt,
    status?.activity?.lastActivityAt,
    status?.lastOutputAt,
    status?.activity?.lastOutputAt,
    status?.lastWorkdirAt,
    status?.activity?.lastWorkdirAt,
    status?.lastStdoutAt,
    status?.lastStderrAt,
    status?.startedAt,
  ].filter(Boolean);

  if (candidates.length === 0) {
    return null;
  }
  return candidates.sort().at(-1);
}

function buildEvent(kind, runDir, message, data = {}) {
  return {
    ts: nowIso(),
    kind,
    runDir,
    message,
    data,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runDir = path.resolve(args.runDir);
  const files = {
    status: path.join(runDir, 'status.json'),
    milestones: path.join(runDir, 'milestones.jsonl'),
    events: path.join(runDir, 'watcher.events.jsonl'),
    cursor: path.join(runDir, 'watcher.cursor.json'),
  };

  if (!fs.existsSync(runDir)) {
    throw new Error(`Run directory does not exist: ${runDir}`);
  }

  const cursor = readJson(files.cursor, {
    startedAt: null,
    lastHeartbeatAt: null,
    milestoneSeqSeen: 0,
    lastFallbackStallKey: null,
    stallSuspectedAt: null,
    stallRecoveredAt: null,
    terminalState: null,
    terminalCompletedAt: null,
  });

  function emit(event) {
    process.stdout.write(humanLine(event) + '\n');
    appendJsonl(files.events, event);
  }

  while (true) {
    const status = readJson(files.status, null);
    const milestones = readJsonLines(files.milestones);

    if (status?.startedAt && cursor.startedAt !== status.startedAt) {
      emit(buildEvent('started', runDir, 'runner started', {
        state: status.state,
        pid: status.pid,
        startedAt: status.startedAt,
        label: status.label || null,
      }));
      cursor.startedAt = status.startedAt;
    }

    if (status?.lastHeartbeatAt && cursor.lastHeartbeatAt !== status.lastHeartbeatAt) {
      emit(buildEvent('heartbeat', runDir, 'heartbeat observed', {
        state: status.state,
        lastHeartbeatAt: status.lastHeartbeatAt,
        pid: status.pid,
      }));
      cursor.lastHeartbeatAt = status.lastHeartbeatAt;
    }

    for (const milestone of milestones) {
      if ((milestone.seq || 0) <= cursor.milestoneSeqSeen) {
        continue;
      }
      emit(buildEvent('milestone', runDir, milestone.message || 'milestone', milestone));
      cursor.milestoneSeqSeen = milestone.seq || cursor.milestoneSeqSeen + 1;
    }

    if (status) {
      const suspectedAt = status.stall?.suspectedAt || null;
      const recoveredAt = status.stall?.recoveredAt || null;
      if (status.stall?.suspected && suspectedAt && cursor.stallSuspectedAt !== suspectedAt) {
        emit(buildEvent('stall', runDir, status.stall?.lastReason || 'suspected stall', {
          suspectedAt,
          deadlineAt: status.stall?.deadlineAt || null,
          idleThresholdSec: status.stall?.idleThresholdSec ?? null,
          graceSec: status.stall?.graceSec ?? null,
          lastActivityAt: status.lastActivityAt || status.activity?.lastActivityAt || null,
          lastActivitySource: status.lastActivitySource || status.activity?.lastActivitySource || null,
        }));
        cursor.stallSuspectedAt = suspectedAt;
      }

      if (!status.stall?.suspected && recoveredAt && cursor.stallRecoveredAt !== recoveredAt) {
        emit(buildEvent('stall_cleared', runDir, `stall cleared by ${status.stall?.lastRecoverySource || 'activity'}`, {
          recoveredAt,
          recoveryCount: status.stall?.recoveryCount ?? 0,
          lastRecoverySource: status.stall?.lastRecoverySource || null,
          lastActivityAt: status.lastActivityAt || status.activity?.lastActivityAt || null,
          lastActivitySource: status.lastActivitySource || status.activity?.lastActivitySource || null,
        }));
        cursor.stallRecoveredAt = recoveredAt;
      }
    }

    if (status && status.state === 'running' && !status.stall) {
      const lastActivityAt = pickLastActivity(status);
      if (lastActivityAt) {
        const idleMs = Date.now() - new Date(lastActivityAt).getTime();
        if (idleMs >= args.stallMs && cursor.lastFallbackStallKey !== lastActivityAt) {
          emit(buildEvent('stall', runDir, `no activity for ${idleMs}ms`, {
            idleMs,
            lastActivityAt,
            thresholdMs: args.stallMs,
          }));
          cursor.lastFallbackStallKey = lastActivityAt;
        }
        if (cursor.lastFallbackStallKey && new Date(lastActivityAt).getTime() > new Date(cursor.lastFallbackStallKey).getTime()) {
          cursor.lastFallbackStallKey = null;
        }
      }
    }

    if (status && ['completed', 'failed'].includes(status.state)) {
      const terminalKey = `${status.state}:${status.completedAt || ''}`;
      const previousKey = `${cursor.terminalState || ''}:${cursor.terminalCompletedAt || ''}`;
      if (terminalKey !== previousKey) {
        emit(buildEvent(status.state, runDir, `runner ${status.state}`, {
          state: status.state,
          completedAt: status.completedAt,
          exitCode: status.exitCode,
          signal: status.signal,
          error: status.error,
          milestoneCount: status.milestoneCount,
          timedOut: Boolean(status.timedOut),
          timeoutType: status.timeout?.type || null,
          lastActivityAt: status.lastActivityAt || status.activity?.lastActivityAt || null,
          lastActivitySource: status.lastActivitySource || status.activity?.lastActivitySource || null,
          stallRecoveryCount: status.stall?.recoveryCount ?? 0,
        }));
        cursor.terminalState = status.state;
        cursor.terminalCompletedAt = status.completedAt || null;
      }
    }

    writeJson(files.cursor, cursor);

    if (args.once) {
      return;
    }

    if (status && ['completed', 'failed'].includes(status.state)) {
      return;
    }

    await sleep(args.pollMs);
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
