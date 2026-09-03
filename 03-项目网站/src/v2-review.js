const { runPythonJsonBridge } = require('./python-bridge');

async function getV2ReviewTasks(config, { stream, batch } = {}) {
  const args = [];
  if (stream) args.push('--stream', stream);
  if (batch) args.push('--batch', String(batch));
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_REVIEW_BRIDGE_FILE,
    command: 'tasks',
    args,
    errorLabel: 'V2 review API',
    maxBuffer: 16 * 1024 * 1024,
  });
}

async function getV2ReviewTask(config, taskId) {
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_REVIEW_BRIDGE_FILE,
    command: 'task',
    args: ['--task-id', taskId || ''],
    errorLabel: 'V2 review API',
    maxBuffer: 16 * 1024 * 1024,
  });
}

async function submitV2Review(config, payload) {
  const encoded = Buffer.from(JSON.stringify(payload || {}), 'utf8').toString('base64');
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_REVIEW_BRIDGE_FILE,
    command: 'submit',
    args: [
      '--manifest', config.V2_REVIEW_MANIFEST_FILE,
      '--payload-base64', encoded,
    ],
    errorLabel: 'V2 review API',
    maxBuffer: 16 * 1024 * 1024,
  });
}

module.exports = {
  getV2ReviewTasks,
  getV2ReviewTask,
  submitV2Review,
};
