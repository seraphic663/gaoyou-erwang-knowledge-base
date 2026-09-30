const { runPythonJsonBridge } = require('./python-bridge');

async function getV2Acceptance(config, command, args = []) {
  return runPythonJsonBridge(config, {
    bridgeFile: config.V2_ACCEPTANCE_BRIDGE_FILE,
    command,
    args,
    errorLabel: 'V2 acceptance API',
  });
}

module.exports = { getV2Acceptance };
