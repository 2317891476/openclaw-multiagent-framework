/**
 * spawn-interceptor — OpenClaw plugin for automatic ACP task tracking.
 *
 * Hooks:
 *   before_tool_call: intercepts sessions_spawn to log and inject completion relay
 *   subagent_ended: updates task status when sub-agents finish (primary completion detection)
 *
 * Defense mechanisms:
 *   - Persistent pending state survives Gateway restarts
 *   - Stale task reaper runs on startup and periodically, marking stuck tasks as timed out
 *   - OPTIONAL prompt relay as enhancement (not relied upon)
 *
 * Install: openclaw plugins install --link ~/.openclaw/plugins/spawn-interceptor
 */

import fs from 'fs';
import path from 'path';
import os from 'os';

const SHARED_CTX = path.join(os.homedir(), '.openclaw', 'shared-context');
const TASK_LOG = path.join(SHARED_CTX, 'monitor-tasks', 'task-log.jsonl');
const PENDING_FILE = path.join(SHARED_CTX, 'monitor-tasks', '.pending-tasks.json');
const COMPLETION_SESSION = 'agent:main:completion-relay';

const STALE_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
const REAPER_INTERVAL_MS = 5 * 60 * 1000; // check every 5 minutes

let pendingTasks = new Map();
let reaperTimer = null;

function loadPending() {
  try {
    if (fs.existsSync(PENDING_FILE)) {
      const data = JSON.parse(fs.readFileSync(PENDING_FILE, 'utf-8'));
      pendingTasks = new Map(Object.entries(data));
    }
  } catch { /* start fresh */ }
}

function savePending() {
  try {
    const dir = path.dirname(PENDING_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(PENDING_FILE, JSON.stringify(Object.fromEntries(pendingTasks), null, 2));
  } catch { /* non-fatal */ }
}

function genId() {
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const r = Math.random().toString(36).slice(2, 8);
  return `tsk_${ts}_${r}`;
}

function appendLog(entry) {
  const dir = path.dirname(TASK_LOG);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  fs.appendFileSync(TASK_LOG, JSON.stringify(entry) + '\n');
}

function relay(taskId) {
  return `\n\n---\n[COMPLETION RELAY — OPTIONAL]\nIf possible, after completing all work, call sessions_send with:\n  sessionKey: "${COMPLETION_SESSION}"\n  message: {"type":"acp_completion","taskId":"${taskId}","status":"completed or failed","summary":"one-sentence result"}\nThis is optional — completion is also tracked automatically.\n---`;
}

function reapStaleTasks(logger) {
  const now = Date.now();
  let reaped = 0;

  for (const [taskId, task] of [...pendingTasks.entries()]) {
    const spawnedAt = new Date(task.spawnedAt).getTime();
    if (now - spawnedAt > STALE_TIMEOUT_MS) {
      pendingTasks.delete(taskId);

      appendLog({
        taskId,
        agentId: task.agentId,
        sessionKey: task.sessionKey,
        runtime: task.runtime,
        task: task.task,
        spawnedAt: task.spawnedAt,
        status: 'timeout',
        completedAt: new Date().toISOString(),
        completionSource: 'stale_reaper',
        reason: `no subagent_ended received within ${STALE_TIMEOUT_MS / 60000}min`,
      });

      reaped++;
    }
  }

  if (reaped > 0) {
    savePending();
    logger.info(`spawn-interceptor: reaped ${reaped} stale task(s), ${pendingTasks.size} still pending`);
  }
}

const spawnInterceptorPlugin = {
  id: 'spawn-interceptor',
  name: 'Spawn Interceptor',
  description: 'Auto-tracks sessions_spawn and injects ACP completion relay',
  version: '2.2.0',

  register(api) {
    api.logger.info('spawn-interceptor v2.2: registering hooks (subagent_ended primary + stale reaper)');

    loadPending();
    if (pendingTasks.size > 0) {
      api.logger.info(`spawn-interceptor: restored ${pendingTasks.size} pending task(s) from disk`);
      reapStaleTasks(api.logger);
    }

    reaperTimer = setInterval(() => reapStaleTasks(api.logger), REAPER_INTERVAL_MS);

    api.on('before_tool_call', (event, ctx) => {
      if (event.toolName !== 'sessions_spawn') return;

      const p = event.params || {};
      const id = genId();
      const rt = p.runtime || 'subagent';

      const taskEntry = {
        taskId: id,
        agentId: ctx.agentId || '?',
        sessionKey: ctx.sessionKey || '',
        runtime: rt,
        task: String(p.task || '').slice(0, 200),
        spawnedAt: new Date().toISOString(),
        status: 'spawning',
      };

      appendLog(taskEntry);

      pendingTasks.set(id, taskEntry);
      savePending();

      api.logger.info(`spawn-interceptor: tracked task ${id} (runtime=${rt}, pending=${pendingTasks.size})`);

      if (rt === 'acp' && p.task) {
        return { params: { ...p, task: p.task + relay(id) } };
      }
    });

    api.on('subagent_ended', (event, ctx) => {
      const targetKey = event.targetSessionKey || '';
      const reason = event.reason || '';
      const outcome = event.outcome || '';
      const endedAt = new Date().toISOString();

      let matchedTaskId = null;
      let matchedTask = null;

      for (const [taskId, task] of pendingTasks.entries()) {
        if (targetKey.includes(':acp:') && task.runtime === 'acp') {
          matchedTaskId = taskId;
          matchedTask = task;
          break;
        }
        if (targetKey.includes(':subagent:') && task.runtime === 'subagent') {
          matchedTaskId = taskId;
          matchedTask = task;
          break;
        }
      }

      const completionStatus = (outcome === 'ok' || reason === 'subagent-complete')
        ? 'completed'
        : 'failed';

      if (matchedTaskId && matchedTask) {
        pendingTasks.delete(matchedTaskId);
        savePending();

        const completionEntry = {
          taskId: matchedTaskId,
          agentId: matchedTask.agentId,
          sessionKey: matchedTask.sessionKey,
          runtime: matchedTask.runtime,
          task: matchedTask.task,
          spawnedAt: matchedTask.spawnedAt,
          status: completionStatus,
          completedAt: endedAt,
          completionSource: 'subagent_ended_hook',
          reason,
          outcome,
          targetSessionKey: targetKey,
        };

        appendLog(completionEntry);
        api.logger.info(`spawn-interceptor: task ${matchedTaskId} → ${completionStatus} (via subagent_ended, pending=${pendingTasks.size})`);
      } else {
        appendLog({
          event: 'subagent_ended',
          targetSessionKey: targetKey,
          targetKind: event.targetKind || 'unknown',
          reason,
          outcome,
          agentId: ctx.runId || '?',
          endedAt,
          matchedTask: false,
        });
        api.logger.info(`spawn-interceptor: subagent ended (${targetKey}, ${reason}) — no matching pending task`);
      }
    });

    api.logger.info('spawn-interceptor v2.2: hooks registered');
  },
};

export default spawnInterceptorPlugin;
