const { execFile } = require('child_process');

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function runReviewBridge(config, command, args = []) {
  const candidates = unique([
    process.env.V2_PYTHON_BIN,
    config.PYTHON_BIN,
    'python3',
    'python',
  ]);

  return new Promise((resolve, reject) => {
    const attempt = (index, lastError = null) => {
      if (index >= candidates.length) {
        reject(lastError || new Error('No Python interpreter available for V2 review API'));
        return;
      }

      execFile(
        candidates[index],
        [config.V2_REVIEW_BRIDGE_FILE, command, ...args, '--db', config.V2_DB_FILE],
        {
          cwd: config.WORKSPACE_ROOT,
          maxBuffer: 16 * 1024 * 1024,
          windowsHide: true,
        },
        (error, stdout, stderr) => {
          if (error && error.code === 'ENOENT') {
            attempt(index + 1, error);
            return;
          }

          if (error) {
            const detail = String(stderr || error.message || '').trim();
            reject(new Error(detail || `V2 review bridge failed with ${error.code || 'unknown error'}`));
            return;
          }

          try {
            resolve(JSON.parse(stdout));
          } catch (parseError) {
            reject(new Error(`Invalid V2 review bridge response: ${parseError.message}`));
          }
        },
      );
    };

    attempt(0);
  });
}

async function getV2ReviewTasks(config, { stream, batch } = {}) {
  const args = [];
  if (stream) args.push('--stream', stream);
  if (batch) args.push('--batch', String(batch));
  return runReviewBridge(config, 'tasks', args);
}

async function getV2ReviewTask(config, taskId) {
  return runReviewBridge(config, 'task', ['--task-id', taskId || '']);
}

async function submitV2Review(config, payload) {
  const encoded = Buffer.from(JSON.stringify(payload || {}), 'utf8').toString('base64');
  return runReviewBridge(config, 'submit', [
    '--manifest', config.V2_REVIEW_MANIFEST_FILE,
    '--payload-base64', encoded,
  ]);
}

module.exports = {
  getV2ReviewTasks,
  getV2ReviewTask,
  submitV2Review,
};
