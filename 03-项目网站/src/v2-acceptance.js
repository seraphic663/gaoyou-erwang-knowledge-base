const { execFile } = require('child_process');

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function runBridge(config, command, args = []) {
  const candidates = unique([
    process.env.V2_PYTHON_BIN,
    config.PYTHON_BIN,
    'python3',
    'python',
  ]);

  return new Promise((resolve, reject) => {
    const attempt = (index, lastError = null) => {
      if (index >= candidates.length) {
        reject(lastError || new Error('No Python interpreter available for V2 acceptance API'));
        return;
      }

      const python = candidates[index];
      execFile(
        python,
        [config.V2_ACCEPTANCE_BRIDGE_FILE, command, ...args, '--db', config.V2_DB_FILE],
        {
          cwd: config.WORKSPACE_ROOT,
          maxBuffer: 8 * 1024 * 1024,
          windowsHide: true,
        },
        (error, stdout, stderr) => {
          if (error && error.code === 'ENOENT') {
            attempt(index + 1, error);
            return;
          }

          if (error) {
            const detail = String(stderr || error.message || '').trim();
            reject(new Error(detail || `V2 bridge failed with ${error.code || 'unknown error'}`));
            return;
          }

          try {
            const payload = JSON.parse(stdout);
            resolve(payload);
          } catch (parseError) {
            reject(new Error(`Invalid V2 bridge response: ${parseError.message}`));
          }
        },
      );
    };

    attempt(0);
  });
}

async function getV2Acceptance(config, command, args = []) {
  return runBridge(config, command, args);
}

module.exports = { getV2Acceptance };
