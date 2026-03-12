/**
 * spawn-interceptor — OpenClaw plugin that automatically tracks task spawns
 * and injects completion relay instructions into ACP prompts.
 *
 * Solves: "Agent forgets to register watcher" by making registration automatic.
 *
 * Hook: before_tool_call
 * Intercepted tools: sessions_spawn
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const TASK_LOG_PATH = path.join(
  os.homedir(),
  '.openclaw',
  'shared-context',
  'monitor-tasks',
  'task-log.jsonl'
);

const COMPLETION_SESSION = 'agent:main:completion-relay';

function generateTaskId() {
  const ts = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
  const rand = Math.random().toString(36).slice(2, 8);
  return `tsk_${ts}_${rand}`;
}

function appendTaskLog(entry) {
  const dir = path.dirname(TASK_LOG_PATH);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.appendFileSync(TASK_LOG_PATH, JSON.stringify(entry) + '\n');
}

function buildCompletionRelay(taskId, agentId) {
  return `

---
[COMPLETION RELAY — DO NOT REMOVE]
When you have finished ALL work on this task, you MUST execute the following
as your FINAL action before ending:

Use the sessions_send tool with these exact parameters:
  sessionKey: "${COMPLETION_SESSION}"
  message: A JSON object with these fields:
    - type: "acp_completion"
    - taskId: "${taskId}"
    - status: "completed" or "failed"
    - summary: A one-sentence summary of what you accomplished
    - error: If failed, the reason (otherwise omit)

This notification is critical. Without it, the requester will never know
your task finished.
---`;
}

const hooks = {
  before_tool_call: async (event) => {
    const { toolName, params, agentId, sessionKey } = event;

    if (toolName !== 'sessions_spawn') {
      return {};
    }

    const taskId = generateTaskId();
    const runtime = params.runtime || 'subagent';
    const taskSummary = (params.task || '').substring(0, 200);

    appendTaskLog({
      taskId,
      agentId: agentId || 'unknown',
      sessionKey: sessionKey || '',
      runtime,
      task: taskSummary,
      spawnedAt: new Date().toISOString(),
      status: 'spawning',
      completionReceived: false
    });

    if (runtime === 'acp' && params.task) {
      const relay = buildCompletionRelay(taskId, agentId);
      return {
        params: {
          ...params,
          task: params.task + relay
        }
      };
    }

    return {};
  }
};

module.exports = { hooks };
