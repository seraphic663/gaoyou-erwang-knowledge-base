const path = require('path');
const { runPythonJsonBridge } = require('./python-bridge');
async function getAuditTargets(config, source, ids) {
  if (!['main', 'annotation', 'v2'].includes(source)) throw new Error('invalid_source');
  return runPythonJsonBridge(config, {
    bridgeFile: path.join(config.ROOT_DIR, 'scripts', 'site_identity_bridge.py'),
    command: 'map',
    args: ['--payload-base64', Buffer.from(JSON.stringify({ source, ids })).toString('base64')],
    errorLabel: 'Case identity lookup',
  });
}
module.exports = { getAuditTargets };
