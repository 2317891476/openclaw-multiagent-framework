#!/usr/bin/env node

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');

const FINAL_SUMMARY_PREFIX = 'FINAL_SUMMARY_JSON=';
const FINAL_SUMMARY_PATH_PREFIX = 'FINAL_SUMMARY_PATH=';
const FINAL_SUMMARY_VERSION = 1;
const DEFAULT_TAIL_CHARS = 2000;
const DEFAULT_HEARTBEAT_MS = 5000;
const DEFAULT_TIMEOUT_SEC = 1800;
const DEFAULT_IDLE_TIMEOUT_SEC = 600;
const DEFAULT_KILL_GRACE_MS = 5000;

function usage(code = 0) {
  const text = `Usage:
  node scripts/subagent_claude_runner.js --task "your task" [--run-dir /path/to/run]

Options:
  --task <text>            Task/prompt passed to Claude CLI
  --task-file <path>       Read task from file
  --run-dir <path>         Run directory (default: tmp/claude-runs/run-<timestamp>)
  --cwd <path>             Working directory for Claude CLI subprocess (default: current process cwd)
  --label <text>           Optional label stored in meta/status
  --heartbeat-ms <ms>      Heartbeat interval (default: ${DEFAULT_HEARTBEAT_MS})
  --timeout-s <sec>        Total runtime timeout in seconds (default: ${DEFAULT_TIMEOUT_SEC}, 0 disables)
  --idle-timeout-s <sec>   No stdout/stderr timeout in seconds (default: ${DEFAULT_IDLE_TIMEOUT_SEC}, 0 disables)
  --kill-grace-ms <ms>     Delay between SIGTERM and SIGKILL escalation (default: ${DEFAULT_KILL_GRACE_MS})
  --claude-bin <path>      Claude executable (default: auto-detect known Claude Code CLI paths)
  --help                   Show this help

Environment:
  SUBAGENT_CLAUDE_TIMEOUT_S
  SUBAGENT_CLAUDE_IDLE_TIMEOUT_S
  SUBAGENT_CLAUDE_KILL_GRACE_MS
  CLAUDE_BIN
  CLAUDE_EXTRA_ARGS

Notes:
  - Default command is: <detected-claude-cli> --permission-mode bypassPermissions --print <task>
  - Detection order: --claude-bin > CLAUDE_BIN > PATH 'claude' > known npm install locations.
  - Extra args can be supplied via CLAUDE_EXTRA_ARGS as a whitespace-separated string.
  - First stdout line is always the runDir; terminal summary lines are emitted only after completion.
  - On timeout, runner marks state=failed + failureKind=timeout, then performs SIGTERM -> SIGKILL cleanup.
`;
  const out = code === 0 ? process.stdout : process.stderr;
  out.write(text);
  process.exit(code);
}

function parseNumberOption(flagName, rawValue, { allowZero = false, fallback = undefined } = {}) {
  const source = rawValue === undefined || rawValue === null || rawValue === '' ? fallback : rawValue;
  const value = Number(source);
  const min = allowZero ? 0 : Number.EPSILON;
  if (!Number.isFinite(value) || value < min) {
    throw new Error(`${flagName} must be ${allowZero ? 'a non-negative' : 'a positive'} number`);
  }
  return value;
}

function parseArgs(argv) {
  const args = {
    heartbeatMs: parseNumberOption('--heartbeat-ms', process.env.SUBAGENT_CLAUDE_HEARTBEAT_MS, {
      allowZero: false,
      fallback: DEFAULT_HEARTBEAT_MS,
    }),
    timeoutSec: parseNumberOption('--timeout-s', process.env.SUBAGENT_CLAUDE_TIMEOUT_S, {
      allowZero: true,
      fallback: DEFAULT_TIMEOUT_SEC,
    }),
    idleTimeoutSec: parseNumberOption('--idle-timeout-s', process.env.SUBAGENT_CLAUDE_IDLE_TIMEOUT_S, {
      allowZero: true,
      fallback: DEFAULT_IDLE_TIMEOUT_SEC,
    }),
    killGraceMs: parseNumberOption('--kill-grace-ms', process.env.SUBAGENT_CLAUDE_KILL_GRACE_MS, {
      allowZero: true,
      fallback: DEFAULT_KILL_GRACE_MS,
    }),
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    switch (arg) {
      case '--task':
        args.task = argv[++i];
        break;
      case '--task-file':
        args.taskFile = argv[++i];
        break;
      case '--run-dir':
        args.runDir = argv[++i];
        break;
      case '--cwd':
        args.cwd = argv[++i];
        break;
      case '--label':
        args.label = argv[++i];
        break;
      case '--heartbeat-ms':
        args.heartbeatMs = parseNumberOption('--heartbeat-ms', argv[++i]);
        break;
      case '--timeout-s':
        args.timeoutSec = parseNumberOption('--timeout-s', argv[++i], { allowZero: true });
        break;
      case '--idle-timeout-s':
        args.idleTimeoutSec = parseNumberOption('--idle-timeout-s', argv[++i], { allowZero: true });
        break;
      case '--kill-grace-ms':
        args.killGraceMs = parseNumberOption('--kill-grace-ms', argv[++i], { allowZero: true });
        break;
      case '--claude-bin':
        args.claudeBin = argv[++i];
        break;
      case '--help':
      case '-h':
        usage(0);
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (args.taskFile) {
    args.task = fs.readFileSync(path.resolve(args.taskFile), 'utf8').trim();
  }

  if (!args.task) {
    throw new Error('Missing required --task or --task-file');
  }

  return args;
}

function nowIso() {
  return new Date().toISOString();
}

function isoFromEpochMs(epochMs) {
  if (!Number.isFinite(epochMs)) {
    return null;
  }
  return new Date(epochMs).toISOString();
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function writeJson(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2) + '\n');
}

function appendJsonl(filePath, data) {
  fs.appendFileSync(filePath, JSON.stringify(data) + '\n');
}

function splitExtraArgs(text) {
  if (!text || !text.trim()) {
    return [];
  }
  return text.trim().split(/\s+/).filter(Boolean);
}

function sanitizeLabel(text) {
  return String(text || '')
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64);
}

function defaultRunDir(label) {
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const suffix = sanitizeLabel(label);
  const name = suffix ? `run-${ts}-${suffix}` : `run-${ts}`;
  return path.resolve(process.cwd(), 'tmp', 'claude-runs', name);
}

function createLineReader(onLine) {
  let buffer = '';
  return {
    push(chunk) {
      buffer += chunk;
      const parts = buffer.split(/\r?\n/);
      buffer = parts.pop();
      for (const line of parts) {
        onLine(line);
      }
    },
    flush() {
      if (buffer) {
        onLine(buffer);
        buffer = '';
      }
    },
  };
}

function extractMilestone(line) {
  const patterns = [
    /^\s*MILESTONE\s*:\s*(.+?)\s*$/i,
    /^\s*\[milestone\]\s*(.+?)\s*$/i,
    /^\s*\[\[milestone\]\]\s*(.+?)\s*$/i,
  ];

  for (const pattern of patterns) {
    const match = line.match(pattern);
    if (match) {
      return match[1];
    }
  }
  return null;
}

function pathCandidatesForCommand(name) {
  const parts = String(process.env.PATH || '').split(path.delimiter).filter(Boolean);
  return parts.map((dir) => path.join(dir, name));
}

function firstExisting(paths) {
  for (const candidate of paths) {
    if (!candidate) continue;
    try {
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    } catch (_) {
      // ignore bad candidate
    }
  }
  return null;
}

function findClaudeCodeCliInNpmGlobal() {
  const home = os.homedir();
  const roots = [
    path.join(home, '.npm-global', 'lib', 'node_modules', '@anthropic-ai'),
    path.join(home, '.config', 'yarn', 'global', 'node_modules', '@anthropic-ai'),
  ];

  for (const root of roots) {
    if (!fs.existsSync(root)) continue;

    const direct = path.join(root, 'claude-code', 'cli.js');
    if (fs.existsSync(direct)) return direct;

    try {
      const entries = fs.readdirSync(root, { withFileTypes: true });
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;
        if (!entry.name.startsWith('.claude-code-')) continue;
        const candidate = path.join(root, entry.name, 'cli.js');
        if (fs.existsSync(candidate)) {
          return candidate;
        }
      }
    } catch (_) {
      // ignore unreadable roots
    }
  }

  return null;
}

function resolveClaudeBin(explicitBin) {
  if (explicitBin) return explicitBin;
  if (process.env.CLAUDE_BIN) return process.env.CLAUDE_BIN;

  const pathClaude = firstExisting(pathCandidatesForCommand('claude'));
  if (pathClaude) return pathClaude;

  try {
    const binDir = path.join(os.homedir(), '.npm-global', 'bin');
    if (fs.existsSync(binDir)) {
      const entries = fs.readdirSync(binDir);
      for (const name of entries) {
        if (!name.startsWith('.claude-')) continue;
        const candidate = path.join(binDir, name);
        if (fs.existsSync(candidate)) return candidate;
      }
    }
  } catch (_) {
    // ignore unreadable bin dir
  }

  const npmCli = findClaudeCodeCliInNpmGlobal();
  if (npmCli) return npmCli;

  return 'claude';
}

function limitTail(text, maxChars = DEFAULT_TAIL_CHARS) {
  const value = String(text || '');
  if (value.length <= maxChars) {
    return value;
  }
  return `...${value.slice(-maxChars)}`;
}

function createTailBuffer(maxChars = DEFAULT_TAIL_CHARS) {
  let value = '';
  return {
    push(chunk) {
      value += String(chunk || '');
      if (value.length > maxChars) {
        value = value.slice(-maxChars);
      }
    },
    get() {
      return value;
    },
  };
}

function formatTerminalReport(summary) {
  const lines = [
    '# Claude Runner Final Report',
    '',
    `- state: ${summary.state}`,
    `- failureKind: ${summary.failureKind || 'null'}`,
    `- timedOut: ${summary.timedOut ? 'true' : 'false'}`,
    `- timeoutType: ${summary.timeout?.type || 'null'}`,
    `- exitCode: ${summary.exitCode === null ? 'null' : summary.exitCode}`,
    `- signal: ${summary.signal || 'null'}`,
    `- label: ${summary.label || 'null'}`,
    `- runDir: ${summary.runDir}`,
    `- workdir: ${summary.workdir || 'null'}`,
    `- statusPath: ${summary.statusPath}`,
    `- stdoutPath: ${summary.stdoutPath}`,
    `- stderrPath: ${summary.stderrPath}`,
    `- finalSummaryPath: ${summary.finalSummaryPath}`,
    `- createdAt: ${summary.createdAt || 'null'}`,
    `- startedAt: ${summary.startedAt || 'null'}`,
    `- completedAt: ${summary.completedAt || 'null'}`,
    `- milestoneCount: ${summary.milestoneCount}`,
    '',
    '## timeout policy',
    '',
    `- totalSec: ${summary.timeout?.totalSec ?? 'null'}`,
    `- idleSec: ${summary.timeout?.idleSec ?? 'null'}`,
    `- killGraceMs: ${summary.timeout?.killGraceMs ?? 'null'}`,
    `- triggeredAt: ${summary.timeout?.triggeredAt || 'null'}`,
    `- sentSigtermAt: ${summary.timeout?.sentSigtermAt || 'null'}`,
    `- escalatedSigkillAt: ${summary.timeout?.escalatedSigkillAt || 'null'}`,
    '',
    '## stdout tail',
    '',
    '~~~text',
    summary.stdoutTail || '(empty)',
    '~~~',
    '',
    '## stderr tail',
    '',
    '~~~text',
    summary.stderrTail || '(empty)',
    '~~~',
  ];

  if (summary.error) {
    lines.push('', '## error', '', '~~~text', summary.error, '~~~');
  }

  return lines.join('\n') + '\n';
}

function buildFinalSummary(status, files, tails) {
  return {
    version: FINAL_SUMMARY_VERSION,
    state: status.state,
    failureKind: status.failureKind,
    timedOut: Boolean(status.timedOut),
    exitCode: status.exitCode,
    signal: status.signal,
    error: status.error,
    label: status.label || null,
    runDir: status.runDir,
    workdir: status.workdir || null,
    createdAt: status.createdAt,
    startedAt: status.startedAt,
    completedAt: status.completedAt,
    milestoneCount: status.milestoneCount,
    timeout: status.timeout,
    statusPath: files.status,
    stdoutPath: files.stdout,
    stderrPath: files.stderr,
    reportPath: files.finalReport,
    finalSummaryPath: files.finalSummary,
    stdoutTail: limitTail(tails.stdout.get()),
    stderrTail: limitTail(tails.stderr.get()),
    taskPreview: status.taskPreview,
  };
}

function pidExists(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === 'EPERM';
  }
}

function sendSignalToChildTree(pid, signal) {
  if (!Number.isInteger(pid) || pid <= 0) {
    return false;
  }

  const attempts = [
    () => process.kill(-pid, signal),
    () => process.kill(pid, signal),
  ];

  for (const attempt of attempts) {
    try {
      attempt();
      return true;
    } catch (error) {
      if (error.code === 'ESRCH') {
        continue;
      }
      if (error.code === 'EPERM') {
        return false;
      }
    }
  }

  return false;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runDir = path.resolve(args.runDir || defaultRunDir(args.label));
  const workdir = path.resolve(args.cwd || process.cwd());
  if (!fs.existsSync(workdir) || !fs.statSync(workdir).isDirectory()) {
    throw new Error(`Working directory does not exist or is not a directory: ${workdir}`);
  }
  ensureDir(runDir);

  const files = {
    meta: path.join(runDir, 'meta.json'),
    status: path.join(runDir, 'status.json'),
    milestones: path.join(runDir, 'milestones.jsonl'),
    stdout: path.join(runDir, 'claude.stdout.log'),
    stderr: path.join(runDir, 'claude.stderr.log'),
    finalSummary: path.join(runDir, 'final-summary.json'),
    finalReport: path.join(runDir, 'final-report.md'),
  };

  const createdAt = nowIso();
  const claudeBin = resolveClaudeBin(args.claudeBin);
  const extraArgs = splitExtraArgs(process.env.CLAUDE_EXTRA_ARGS || '');
  const claudeArgs = ['--permission-mode', 'bypassPermissions', '--print', ...extraArgs, args.task];

  const meta = {
    label: args.label || null,
    runDir,
    workdir,
    createdAt,
    command: {
      bin: claudeBin,
      args: claudeArgs,
      cwd: workdir,
    },
    timeoutPolicy: {
      totalSec: args.timeoutSec,
      idleSec: args.idleTimeoutSec,
      killGraceMs: args.killGraceMs,
    },
    files,
  };
  writeJson(files.meta, meta);

  const status = {
    label: args.label || null,
    state: 'starting',
    failureKind: null,
    timedOut: false,
    runDir,
    workdir,
    createdAt,
    startedAt: createdAt,
    updatedAt: createdAt,
    lastHeartbeatAt: createdAt,
    lastStdoutAt: null,
    lastStderrAt: null,
    lastOutputAt: null,
    completedAt: null,
    pid: null,
    exitCode: null,
    signal: null,
    error: null,
    taskPreview: args.task.slice(0, 200),
    milestoneCount: 0,
    files,
    command: meta.command,
    timeout: {
      totalSec: args.timeoutSec,
      idleSec: args.idleTimeoutSec,
      killGraceMs: args.killGraceMs,
      totalDeadlineAt: args.timeoutSec > 0 ? isoFromEpochMs(Date.now() + args.timeoutSec * 1000) : null,
      idleDeadlineAt: args.idleTimeoutSec > 0 ? isoFromEpochMs(Date.now() + args.idleTimeoutSec * 1000) : null,
      triggered: false,
      type: null,
      reason: null,
      triggeredAt: null,
      sentSigtermAt: null,
      escalatedSigkillAt: null,
    },
  };

  function flushStatus() {
    status.updatedAt = nowIso();
    writeJson(files.status, status);
  }

  flushStatus();
  process.stdout.write(`${runDir}\n`);

  const stdoutStream = fs.createWriteStream(files.stdout, { flags: 'a' });
  const stderrStream = fs.createWriteStream(files.stderr, { flags: 'a' });
  const tails = {
    stdout: createTailBuffer(),
    stderr: createTailBuffer(),
  };

  const child = spawn(claudeBin, claudeArgs, {
    cwd: workdir,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: process.platform !== 'win32',
  });

  let milestoneSeq = 0;
  let resolved = false;
  let totalTimer = null;
  let idleTimer = null;
  let killTimer = null;

  function clearTimers() {
    if (totalTimer) {
      clearTimeout(totalTimer);
      totalTimer = null;
    }
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
    if (killTimer) {
      clearTimeout(killTimer);
      killTimer = null;
    }
  }

  function onMilestone(message, source, line) {
    milestoneSeq += 1;
    const record = {
      seq: milestoneSeq,
      ts: nowIso(),
      source,
      message,
      line,
    };
    appendJsonl(files.milestones, record);
    status.milestoneCount = milestoneSeq;
    flushStatus();
  }

  function scheduleIdleTimeout() {
    if (resolved || status.timeout.triggered || args.idleTimeoutSec <= 0) {
      return;
    }
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
    const baseAt = status.lastOutputAt || status.startedAt || createdAt;
    const deadlineMs = new Date(baseAt).getTime() + args.idleTimeoutSec * 1000;
    status.timeout.idleDeadlineAt = isoFromEpochMs(deadlineMs);
    const delayMs = Math.max(0, deadlineMs - Date.now());
    idleTimer = setTimeout(() => {
      triggerTimeout('idle', `No stdout/stderr for ${args.idleTimeoutSec}s`);
    }, delayMs);
  }

  function scheduleTotalTimeout() {
    if (resolved || status.timeout.triggered || args.timeoutSec <= 0) {
      return;
    }
    if (totalTimer) {
      clearTimeout(totalTimer);
      totalTimer = null;
    }
    const baseAt = status.startedAt || createdAt;
    const deadlineMs = new Date(baseAt).getTime() + args.timeoutSec * 1000;
    status.timeout.totalDeadlineAt = isoFromEpochMs(deadlineMs);
    const delayMs = Math.max(0, deadlineMs - Date.now());
    totalTimer = setTimeout(() => {
      triggerTimeout('total', `Exceeded total runtime ${args.timeoutSec}s`);
    }, delayMs);
  }

  function markOutput(source) {
    const ts = nowIso();
    if (source === 'stdout') {
      status.lastStdoutAt = ts;
    }
    if (source === 'stderr') {
      status.lastStderrAt = ts;
    }
    status.lastOutputAt = ts;
    scheduleIdleTimeout();
  }

  function terminateChildForTimeout() {
    if (!pidExists(child.pid)) {
      return;
    }

    status.timeout.sentSigtermAt = nowIso();
    flushStatus();
    sendSignalToChildTree(child.pid, 'SIGTERM');

    if (args.killGraceMs <= 0) {
      status.timeout.escalatedSigkillAt = nowIso();
      flushStatus();
      sendSignalToChildTree(child.pid, 'SIGKILL');
      return;
    }

    killTimer = setTimeout(() => {
      if (resolved || !pidExists(child.pid)) {
        return;
      }
      status.timeout.escalatedSigkillAt = nowIso();
      flushStatus();
      sendSignalToChildTree(child.pid, 'SIGKILL');
    }, args.killGraceMs);
  }

  function triggerTimeout(type, reason) {
    if (resolved || status.timeout.triggered) {
      return;
    }

    status.state = 'failed';
    status.failureKind = 'timeout';
    status.timedOut = true;
    status.error = reason;
    status.timeout.triggered = true;
    status.timeout.type = type;
    status.timeout.reason = reason;
    status.timeout.triggeredAt = nowIso();
    flushStatus();
    terminateChildForTimeout();
  }

  const stdoutLines = createLineReader((line) => {
    markOutput('stdout');
    const milestone = extractMilestone(line);
    if (milestone) {
      onMilestone(milestone, 'stdout', line);
      return;
    }
    flushStatus();
  });

  const stderrLines = createLineReader((line) => {
    markOutput('stderr');
    const milestone = extractMilestone(line);
    if (milestone) {
      onMilestone(milestone, 'stderr', line);
      return;
    }
    flushStatus();
  });

  child.stdout.on('data', (chunk) => {
    const text = chunk.toString('utf8');
    stdoutStream.write(text);
    tails.stdout.push(text);
    stdoutLines.push(text);
  });

  child.stderr.on('data', (chunk) => {
    const text = chunk.toString('utf8');
    stderrStream.write(text);
    tails.stderr.push(text);
    stderrLines.push(text);
  });

  const heartbeat = setInterval(() => {
    status.lastHeartbeatAt = nowIso();
    flushStatus();
  }, args.heartbeatMs);

  function emitTerminalSummary() {
    const summary = buildFinalSummary(status, files, tails);
    writeJson(files.finalSummary, summary);
    fs.writeFileSync(files.finalReport, formatTerminalReport(summary));
    process.stdout.write(`${FINAL_SUMMARY_PATH_PREFIX}${files.finalSummary}\n`);
    process.stdout.write(`${FINAL_SUMMARY_PREFIX}${JSON.stringify(summary)}\n`);
    return summary;
  }

  function finish(result) {
    if (resolved) {
      return result;
    }
    resolved = true;
    clearInterval(heartbeat);
    clearTimers();
    stdoutLines.flush();
    stderrLines.flush();
    status.lastHeartbeatAt = nowIso();
    flushStatus();
    emitTerminalSummary();
    stdoutStream.end();
    stderrStream.end();
    return result;
  }

  child.on('spawn', () => {
    const startedAt = nowIso();
    status.state = 'running';
    status.startedAt = startedAt;
    status.pid = child.pid;
    status.lastHeartbeatAt = startedAt;
    status.timeout.totalDeadlineAt = args.timeoutSec > 0 ? isoFromEpochMs(new Date(startedAt).getTime() + args.timeoutSec * 1000) : null;
    status.timeout.idleDeadlineAt = args.idleTimeoutSec > 0 ? isoFromEpochMs(new Date(startedAt).getTime() + args.idleTimeoutSec * 1000) : null;
    flushStatus();
    scheduleTotalTimeout();
    scheduleIdleTimeout();
  });

  const settle = await new Promise((resolve) => {
    child.on('error', (error) => {
      status.state = 'failed';
      if (!status.failureKind) {
        status.failureKind = 'spawn_error';
      }
      status.error = status.error || error.message;
      status.completedAt = nowIso();
      resolve(finish({ ok: false, error }));
    });

    child.on('close', (code, signal) => {
      status.exitCode = code;
      status.signal = signal;
      status.completedAt = nowIso();
      if (status.timeout.triggered) {
        status.state = 'failed';
        status.failureKind = 'timeout';
        status.timedOut = true;
      } else {
        status.state = code === 0 ? 'completed' : 'failed';
        if (code !== 0 && !status.failureKind) {
          status.failureKind = 'process_exit';
        }
      }
      resolve(finish({ ok: code === 0 && !status.timeout.triggered, code, signal }));
    });
  });

  if (!settle.ok) {
    if (Number.isInteger(settle.code)) {
      process.exit(settle.code);
    }
    process.exit(1);
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
