const { runPythonJsonBridge } = require('./python-bridge');

async function getV2FiveStepAudits(config, caseId) {
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_FIVE_STEP_AUDIT_BRIDGE_FILE,
    command: 'list',
    args: ['--case-id', caseId || ''],
    errorLabel: 'V2 five-step audit API',
  });
}

async function getV2FiveStepAudit(config, auditId) {
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_FIVE_STEP_AUDIT_BRIDGE_FILE,
    command: 'get',
    args: ['--audit-id', auditId || ''],
    errorLabel: 'V2 five-step audit API',
  });
}

async function saveV2FiveStepAudit(config, payload) {
  const encoded = Buffer.from(JSON.stringify(payload || {}), 'utf8').toString('base64');
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_FIVE_STEP_AUDIT_BRIDGE_FILE,
    command: 'save',
    args: ['--payload-base64', encoded],
    errorLabel: 'V2 five-step audit API',
  });
}

async function reviseV2FiveStepAudit(config, payload) {
  const encoded = Buffer.from(JSON.stringify(payload || {}), 'utf8').toString('base64');
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_FIVE_STEP_AUDIT_BRIDGE_FILE,
    command: 'revision',
    args: ['--payload-base64', encoded],
    errorLabel: 'V2 five-step audit API',
  });
}

async function deleteV2FiveStepAudit(config, payload) {
  const encoded = Buffer.from(JSON.stringify(payload || {}), 'utf8').toString('base64');
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_FIVE_STEP_AUDIT_BRIDGE_FILE,
    command: 'delete',
    args: ['--payload-base64', encoded],
    errorLabel: 'V2 five-step audit API',
  });
}

async function restoreV2FiveStepAudit(config, payload) {
  const encoded = Buffer.from(JSON.stringify(payload || {}), 'utf8').toString('base64');
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_FIVE_STEP_AUDIT_BRIDGE_FILE,
    command: 'restore',
    args: ['--payload-base64', encoded],
    errorLabel: 'V2 five-step audit API',
  });
}

module.exports = {
  deleteV2FiveStepAudit,
  getV2FiveStepAudit,
  getV2FiveStepAudits,
  restoreV2FiveStepAudit,
  reviseV2FiveStepAudit,
  saveV2FiveStepAudit,
};
