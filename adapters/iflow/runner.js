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
const DEFAULT_TIMEOUT_SEC = 3600;
const DEFAULT_IDLE_TIMEOUT_SEC = 900;
const DEFAULT_STALL_GRACE_SEC = 300;
const DEFAULT_KILL_GRACE_MS = 5000;

function usage(code = 0) {
  const text = `Usage:
  node runner.js --task "your task" [--run-dir /path/to/run]

Options:
  --task <text>            Task/prompt passed to iFlow CLI
  --task-file <path>       Read task from file
  --job-id <id>            Job identifier (default: JOB-001)
  --task-id <id>           Task identifier (default: task-001)
  --agent-type <type>      Logical worker type, e.g. rtl/tb/verif (default: generic)
  --run-dir <path>         Run directory (default: runs/<job-id>/<task-id>)
  --cwd <path>             Working directory for iFlow CLI subprocess (default: current process cwd)
  --label <text>           Optional human label stored in meta/status
  --heartbeat-ms <ms>      Heartbeat interval (default: ${DEFAULT_HEARTBEAT_MS})
  --timeout-s <sec>        Total runtime timeout in seconds (default: ${DEFAULT_TIMEOUT_SEC}, 0 disables)
  --idle-timeout-s <sec>   No activity timeout in seconds before suspected stall (default: ${DEFAULT_IDLE_TIMEOUT_SEC}, 0 disables)
  --stall-grace-s <sec>    Additional grace after suspected stall before hard timeout (default: ${DEFAULT_STALL_GRACE_SEC}, 0 disables grace)
  --kill-grace-ms <ms>     Delay between SIGTERM and SIGKILL escalation (default: ${DEFAULT_KILL_GRACE_MS})
  --iflow-bin <path>      iFlow executable (default: auto-detect known iFlow CLI paths)
  --help                   Show this help

Environment:
  SUBAGENT_IFLOW_HEARTBEAT_MS
  SUBAGENT_IFLOW_TIMEOUT_S
  SUBAGENT_IFLOW_IDLE_TIMEOUT_S
  SUBAGENT_IFLOW_STALL_GRACE_S
  SUBAGENT_IFLOW_KILL_GRACE_MS
  IFLOW_BIN
  IFLOW_EXTRA_ARGS

Notes:
  - Default command is: <detected-iflow-cli> -y -p <task>
  - Detection order: --iflow-bin > IFLOW_BIN > PATH 'iflow' > known npm install locations.
  - Activity watchdog uses stdout/stderr plus workdir file activity (fs.watch when available).
  - Idle timeout is two-stage: suspected stall at idle threshold, hard timeout only after grace expires.
  - First stdout line is always the runDir; terminal summary lines are emitted only after completion.
  - On hard timeout, runner marks state=failed + failureKind=timeout, then performs SIGTERM -> SIGKILL cleanup.
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
    heartbeatMs: parseNumberOption('--heartbeat-ms', process.env.SUBAGENT_IFLOW_HEARTBEAT_MS, {
      allowZero: false,
      fallback: DEFAULT_HEARTBEAT_MS,
    }),
    timeoutSec: parseNumberOption('--timeout-s', process.env.SUBAGENT_IFLOW_TIMEOUT_S, {
      allowZero: true,
      fallback: DEFAULT_TIMEOUT_SEC,
    }),
    idleTimeoutSec: parseNumberOption('--idle-timeout-s', process.env.SUBAGENT_IFLOW_IDLE_TIMEOUT_S, {
      allowZero: true,
      fallback: DEFAULT_IDLE_TIMEOUT_SEC,
    }),
    stallGraceSec: parseNumberOption('--stall-grace-s', process.env.SUBAGENT_IFLOW_STALL_GRACE_S, {
      allowZero: true,
      fallback: DEFAULT_STALL_GRACE_SEC,
    }),
    killGraceMs: parseNumberOption('--kill-grace-ms', process.env.SUBAGENT_IFLOW_KILL_GRACE_MS, {
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
      case '--job-id':
        args.jobId = argv[++i];
        break;
      case '--task-id':
        args.taskId = argv[++i];
        break;
      case '--agent-type':
        args.agentType = argv[++i];
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
      case '--stall-grace-s':
        args.stallGraceSec = parseNumberOption('--stall-grace-s', argv[++i], { allowZero: true });
        break;
      case '--kill-grace-ms':
        args.killGraceMs = parseNumberOption('--kill-grace-ms', argv[++i], { allowZero: true });
        break;
      case '--iflow-bin':
        args.iflowBin = argv[++i];
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

  args.jobId = args.jobId || 'JOB-001';
  args.taskId = args.taskId || 'task-001';
  args.agentType = args.agentType || 'generic';
  if (!args.label) {
    args.label = `${args.jobId}-${args.taskId}`;
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

function defaultRunDir(jobId, taskId) {
  const safeJobId = sanitizeLabel(jobId || 'JOB-001') || 'JOB-001';
  const safeTaskId = sanitizeLabel(taskId || 'task-001') || 'task-001';
  return path.resolve(process.cwd(), 'runs', safeJobId, safeTaskId);
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

function findIflowCliInNpmGlobal() {
  const home = os.homedir();
  const roots = [
    path.join(home, '.npm-global', 'bin'),
    path.join(home, '.local', 'bin'),
    path.join(home, '.yarn', 'bin'),
  ];

  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    const direct = path.join(root, 'iflow');
    if (fs.existsSync(direct)) return direct;
    const directCmd = path.join(root, 'iflow.cmd');
    if (fs.existsSync(directCmd)) return directCmd;
  }

  return null;
}

function resolveIflowBin(explicitBin) {
  if (explicitBin) return explicitBin;
  if (process.env.IFLOW_BIN) return process.env.IFLOW_BIN;

  const pathIflow = firstExisting(pathCandidatesForCommand('iflow'));
  if (pathIflow) return pathIflow;

  const npmCli = findIflowCliInNpmGlobal();
  if (npmCli) return npmCli;

  return 'iflow';
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
    '# iFlow Adapter Final Report',
    '',
    `- job_id: ${summary.job_id}`,
    `- task_id: ${summary.task_id}`,
    `- agent_type: ${summary.agent_type}`,
    `- status: ${summary.status}`,
    `- exit_code: ${summary.exit_code === null ? 'null' : summary.exit_code}`,
    `- signal: ${summary.signal || 'null'}`,
    `- run_dir: ${summary.run_dir}`,
    `- workdir: ${summary.workdir || 'null'}`,
    `- prompt_path: ${summary.prompt_path}`,
    `- meta_path: ${summary.meta_path}`,
    `- status_path: ${summary.status_path}`,
    `- stdout_path: ${summary.stdout_path}`,
    `- stderr_path: ${summary.stderr_path}`,
    `- final_summary_path: ${summary.final_summary_path}`,
    `- created_at: ${summary.created_at || 'null'}`,
    `- started_at: ${summary.started_at || 'null'}`,
    `- completed_at: ${summary.completed_at || 'null'}`,
    '',
    '## timeout policy',
    '',
    `- totalSec: ${summary.timeout?.totalSec ?? 'null'}`,
    `- idleSec: ${summary.timeout?.idleSec ?? 'null'}`,
    `- stallGraceSec: ${summary.timeout?.stallGraceSec ?? 'null'}`,
    `- killGraceMs: ${summary.timeout?.killGraceMs ?? 'null'}`,
    `- triggeredAt: ${summary.timeout?.triggeredAt || 'null'}`,
    `- sentSigtermAt: ${summary.timeout?.sentSigtermAt || 'null'}`,
    `- escalatedSigkillAt: ${summary.timeout?.escalatedSigkillAt || 'null'}`,
    '',
    '## activity',
    '',
    `- lastActivityAt: ${summary.lastActivityAt || 'null'}`,
    `- lastActivitySource: ${summary.lastActivitySource || 'null'}`,
    `- lastOutputAt: ${summary.lastOutputAt || 'null'}`,
    `- lastWorkdirAt: ${summary.activity?.lastWorkdirAt || 'null'}`,
    `- lastWorkdirPath: ${summary.activity?.lastWorkdirPath || 'null'}`,
    `- workdirEventCount: ${summary.activity?.workdirEventCount ?? 'null'}`,
    `- monitorKind: ${summary.activity?.monitor?.kind || 'null'}`,
    `- monitorError: ${summary.activity?.monitor?.error || 'null'}`,
    '',
    '## stall watchdog',
    '',
    `- suspected: ${summary.stall?.suspected ? 'true' : 'false'}`,
    `- suspectedAt: ${summary.stall?.suspectedAt || 'null'}`,
    `- deadlineAt: ${summary.stall?.deadlineAt || 'null'}`,
    `- recoveredAt: ${summary.stall?.recoveredAt || 'null'}`,
    `- recoveryCount: ${summary.stall?.recoveryCount ?? 'null'}`,
    `- lastRecoverySource: ${summary.stall?.lastRecoverySource || 'null'}`,
    `- hardTimeoutAt: ${summary.stall?.hardTimeoutAt || 'null'}`,
    `- lastReason: ${summary.stall?.lastReason || 'null'}`,
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
  const stdoutTail = limitTail(tails.stdout.get());
  const stderrTail = limitTail(tails.stderr.get());
  return {
    job_id: status.jobId,
    task_id: status.taskId,
    agent_type: status.agentType,
    status: status.state === 'completed' ? 'completed' : 'failed',
    changed_files: [],
    summary: status.state === 'completed'
      ? (stdoutTail.trim() || 'Task completed.')
      : (status.error || stderrTail.trim() || 'Task failed.'),
    next_hint: status.state === 'completed' ? null : 'inspect_stderr',
    exit_code: status.exitCode,
    error: status.error || null,
    signal: status.signal || null,
    run_dir: status.runDir,
    workdir: status.workdir || null,
    prompt_path: files.prompt,
    meta_path: files.meta,
    status_path: files.status,
    stdout_path: files.stdout,
    stderr_path: files.stderr,
    final_summary_path: files.finalSummary,
    report_path: files.finalReport,
    created_at: status.createdAt,
    started_at: status.startedAt,
    completed_at: status.completedAt,
    timeout: status.timeout,
    stall: status.stall,
    activity: status.activity,
    lastActivityAt: status.lastActivityAt || null,
    lastActivitySource: status.lastActivitySource || null,
    lastOutputAt: status.lastOutputAt || null,
    stdoutTail,
    stderrTail,
    stdout_tail: stdoutTail,
    stderr_tail: stderrTail,
    task_preview: status.taskPreview,
    version: FINAL_SUMMARY_VERSION,
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

function normalizePathLike(value) {
  if (typeof value === 'string') {
    return value;
  }
  if (Buffer.isBuffer(value)) {
    return value.toString('utf8');
  }
  return value == null ? '' : String(value);
}

function pathContains(targetPath, parentPath) {
  const target = path.resolve(targetPath);
  const parent = path.resolve(parentPath);
  return target === parent || target.startsWith(parent + path.sep);
}

function createWorkdirActivityMonitor({ workdir, ignoredRoots, onActivity, onError }) {
  const recursive = process.platform === 'darwin' || process.platform === 'win32';
  let watcher = null;
  let closed = false;
  let lastEventKey = null;
  let lastEventAtMs = 0;

  function shouldIgnore(absPath) {
    return ignoredRoots.some((root) => pathContains(absPath, root));
  }

  try {
    watcher = fs.watch(workdir, { recursive }, (eventType, filename) => {
      if (closed) {
        return;
      }
      const raw = normalizePathLike(filename).trim();
      const absPath = raw ? path.resolve(workdir, raw) : workdir;
      if (shouldIgnore(absPath)) {
        return;
      }

      const nowMs = Date.now();
      const key = `${eventType}:${raw || '(unknown)'}`;
      if (key === lastEventKey && nowMs - lastEventAtMs < 250) {
        return;
      }
      lastEventKey = key;
      lastEventAtMs = nowMs;

      onActivity({
        source: 'workdir',
        eventType,
        path: absPath,
        filename: raw || null,
        ts: nowIso(),
      });
    });

    watcher.on('error', (error) => {
      if (closed) {
        return;
      }
      onError(error);
    });

    return {
      kind: 'fs.watch',
      recursive,
      supported: true,
      close() {
        closed = true;
        if (watcher) {
          watcher.close();
        }
      },
    };
  } catch (error) {
    onError(error);
    return {
      kind: 'fs.watch',
      recursive,
      supported: false,
      close() {
        closed = true;
      },
    };
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runDir = path.resolve(args.runDir || defaultRunDir(args.jobId, args.taskId));
  const workdir = path.resolve(args.cwd || process.cwd());
  if (!fs.existsSync(workdir) || !fs.statSync(workdir).isDirectory()) {
    throw new Error(`Working directory does not exist or is not a directory: ${workdir}`);
  }
  ensureDir(runDir);

  const files = {
    prompt: path.join(runDir, 'prompt.txt'),
    meta: path.join(runDir, 'meta.json'),
    status: path.join(runDir, 'status.json'),
    milestones: path.join(runDir, 'milestones.jsonl'),
    stdout: path.join(runDir, 'stdout.log'),
    stderr: path.join(runDir, 'stderr.log'),
    finalSummary: path.join(runDir, 'final_summary.json'),
    finalReport: path.join(runDir, 'final-report.md'),
  };

  const createdAt = nowIso();
  fs.writeFileSync(files.prompt, args.task + '\n');
  const iflowBin = resolveIflowBin(args.iflowBin);
  const extraArgs = splitExtraArgs(process.env.IFLOW_EXTRA_ARGS || '');
  const iflowArgs = ['-y', '-p', args.task, ...extraArgs];
  const runsRoot = path.resolve(workdir, 'tmp', 'iflow-runs');
  const ignoredRoots = [runDir];
  if (pathContains(runDir, runsRoot)) {
    ignoredRoots.push(runsRoot);
  }

  const meta = {
    job_id: args.jobId,
    task_id: args.taskId,
    agent_type: args.agentType,
    label: args.label || null,
    runDir,
    workdir,
    createdAt,
    command: {
      bin: iflowBin,
      args: iflowArgs,
      cwd: workdir,
    },
    timeoutPolicy: {
      totalSec: args.timeoutSec,
      idleSec: args.idleTimeoutSec,
      stallGraceSec: args.stallGraceSec,
      killGraceMs: args.killGraceMs,
    },
    activityPolicy: {
      sources: ['stdout', 'stderr', 'workdir'],
      workdirMonitor: 'fs.watch',
      ignoredRoots,
    },
    files,
  };
  writeJson(files.meta, meta);

  const status = {
    jobId: args.jobId,
    taskId: args.taskId,
    agentType: args.agentType,
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
    lastActivityAt: null,
    lastActivitySource: null,
    lastWorkdirAt: null,
    lastWorkdirPath: null,
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
      stallGraceSec: args.stallGraceSec,
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
    stall: {
      suspected: false,
      suspectedAt: null,
      deadlineAt: null,
      recoveredAt: null,
      recoveryCount: 0,
      lastReason: null,
      lastRecoverySource: null,
      hardTimeoutAt: null,
      idleThresholdSec: args.idleTimeoutSec,
      graceSec: args.stallGraceSec,
    },
    activity: {
      lastActivityAt: null,
      lastActivitySource: null,
      lastOutputAt: null,
      lastWorkdirAt: null,
      lastWorkdirPath: null,
      lastWorkdirEventType: null,
      stdoutChunkCount: 0,
      stderrChunkCount: 0,
      workdirEventCount: 0,
      monitor: {
        kind: null,
        recursive: null,
        supported: null,
        error: null,
        ignoredRoots,
      },
    },
  };

  function flushStatus() {
    status.updatedAt = nowIso();
    writeJson(files.status, status);
  }

  function syncActivityMirror() {
    status.lastActivityAt = status.activity.lastActivityAt;
    status.lastActivitySource = status.activity.lastActivitySource;
    status.lastWorkdirAt = status.activity.lastWorkdirAt;
    status.lastWorkdirPath = status.activity.lastWorkdirPath;
  }

  flushStatus();
  process.stdout.write(`${runDir}\n`);

  const stdoutStream = fs.createWriteStream(files.stdout, { flags: 'a' });
  const stderrStream = fs.createWriteStream(files.stderr, { flags: 'a' });
  const tails = {
    stdout: createTailBuffer(),
    stderr: createTailBuffer(),
  };

  let milestoneSeq = 0;
  let resolved = false;
  let totalTimer = null;
  let idleTimer = null;
  let stallTimer = null;
  let killTimer = null;
  let workdirMonitor = null;

  function clearTimers() {
    if (totalTimer) {
      clearTimeout(totalTimer);
      totalTimer = null;
    }
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
    if (stallTimer) {
      clearTimeout(stallTimer);
      stallTimer = null;
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
    const baseAt = status.lastActivityAt || status.startedAt || createdAt;
    const deadlineMs = new Date(baseAt).getTime() + args.idleTimeoutSec * 1000;
    status.timeout.idleDeadlineAt = isoFromEpochMs(deadlineMs);
    const delayMs = Math.max(0, deadlineMs - Date.now());
    idleTimer = setTimeout(() => {
      const baseline = status.lastActivityAt || status.startedAt || createdAt;
      const reason = `No activity for ${args.idleTimeoutSec}s since ${baseline} (${status.lastActivitySource || 'none'})`;
      triggerSuspectedStall(reason);
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

  function clearSuspectedStall(source) {
    if (!status.stall.suspected) {
      return;
    }
    status.stall.suspected = false;
    status.stall.recoveredAt = nowIso();
    status.stall.recoveryCount += 1;
    status.stall.lastRecoverySource = source || null;
    status.stall.deadlineAt = null;
    if (stallTimer) {
      clearTimeout(stallTimer);
      stallTimer = null;
    }
  }

  function markActivity(source, detail = {}) {
    const ts = detail.ts || nowIso();

    if (source === 'stdout') {
      status.lastStdoutAt = ts;
      status.lastOutputAt = ts;
      status.activity.lastOutputAt = ts;
      status.activity.stdoutChunkCount += 1;
    } else if (source === 'stderr') {
      status.lastStderrAt = ts;
      status.lastOutputAt = ts;
      status.activity.lastOutputAt = ts;
      status.activity.stderrChunkCount += 1;
    } else if (source === 'workdir') {
      status.activity.lastWorkdirAt = ts;
      status.activity.lastWorkdirPath = detail.path || null;
      status.activity.lastWorkdirEventType = detail.eventType || null;
      status.activity.workdirEventCount += 1;
    }

    status.activity.lastActivityAt = ts;
    status.activity.lastActivitySource = source;
    syncActivityMirror();
    clearSuspectedStall(source);
    scheduleIdleTimeout();
  }

  function triggerSuspectedStall(reason) {
    if (resolved || status.timeout.triggered || status.stall.suspected || args.idleTimeoutSec <= 0) {
      return;
    }

    const suspectedAt = nowIso();
    status.stall.suspected = true;
    status.stall.suspectedAt = suspectedAt;
    status.stall.lastReason = reason;
    status.stall.deadlineAt = args.stallGraceSec > 0 ? isoFromEpochMs(Date.now() + args.stallGraceSec * 1000) : suspectedAt;
    flushStatus();

    if (args.stallGraceSec <= 0) {
      status.stall.hardTimeoutAt = nowIso();
      triggerTimeout('stall', `${reason}; grace exhausted immediately`);
      return;
    }

    if (stallTimer) {
      clearTimeout(stallTimer);
      stallTimer = null;
    }
    stallTimer = setTimeout(() => {
      status.stall.hardTimeoutAt = nowIso();
      const totalIdleSec = args.idleTimeoutSec + args.stallGraceSec;
      triggerTimeout('stall', `No activity for ${totalIdleSec}s (idle ${args.idleTimeoutSec}s + grace ${args.stallGraceSec}s)`);
    }, args.stallGraceSec * 1000);
  }

  function terminateChildForTimeout(child) {
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
    terminateChildForTimeout(child);
  }

  const child = spawn(iflowBin, iflowArgs, {
    cwd: workdir,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: process.platform !== 'win32',
  });

  const stdoutLines = createLineReader((line) => {
    const milestone = extractMilestone(line);
    if (milestone) {
      onMilestone(milestone, 'stdout', line);
    }
  });

  const stderrLines = createLineReader((line) => {
    const milestone = extractMilestone(line);
    if (milestone) {
      onMilestone(milestone, 'stderr', line);
    }
  });

  workdirMonitor = createWorkdirActivityMonitor({
    workdir,
    ignoredRoots,
    onActivity: (event) => {
      markActivity('workdir', event);
      flushStatus();
    },
    onError: (error) => {
      status.activity.monitor.error = error.message;
      flushStatus();
    },
  });
  status.activity.monitor.kind = workdirMonitor.kind;
  status.activity.monitor.recursive = workdirMonitor.recursive;
  status.activity.monitor.supported = workdirMonitor.supported;
  flushStatus();

  child.stdout.on('data', (chunk) => {
    const text = chunk.toString('utf8');
    stdoutStream.write(text);
    tails.stdout.push(text);
    markActivity('stdout');
    stdoutLines.push(text);
    flushStatus();
  });

  child.stderr.on('data', (chunk) => {
    const text = chunk.toString('utf8');
    stderrStream.write(text);
    tails.stderr.push(text);
    markActivity('stderr');
    stderrLines.push(text);
    flushStatus();
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
    if (workdirMonitor) {
      workdirMonitor.close();
    }
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
    markActivity('spawn', { ts: startedAt });
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
