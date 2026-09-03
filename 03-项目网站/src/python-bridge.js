const { execFile } = require('child_process');

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

/**
 * Run a Python JSON bridge with the configured interpreter fallback order.
 * Business modules provide only the bridge-specific file, command and args;
 * process execution and response parsing stay in one place.
 */
function runPythonJsonBridge(config, {
  bridgeFile,
  command,
  args = [],
  errorLabel = 'Python bridge',
  maxBuffer = 8 * 1024 * 1024,
}) {
  const candidates = unique([
    process.env.V2_PYTHON_BIN,
    config.PYTHON_BIN,
    'python3',
    'python',
  ]);

  return new Promise((resolve, reject) => {
    const attempt = (index, lastError = null) => {
      if (index >= candidates.length) {
        reject(lastError || new Error(`No Python interpreter available for ${errorLabel}`));
        return;
      }

      execFile(
        candidates[index],
        [bridgeFile, command, ...args, '--db', config.V2_DB_FILE],
        {
          cwd: config.WORKSPACE_ROOT,
          maxBuffer,
          windowsHide: true,
        },
        (error, stdout, stderr) => {
          if (error && error.code === 'ENOENT') {
            attempt(index + 1, error);
            return;
          }

          if (error) {
            const detail = String(stderr || error.message || '').trim();
            reject(new Error(detail || `${errorLabel} failed with ${error.code || 'unknown error'}`));
            return;
          }

          try {
            resolve(JSON.parse(String(stdout || '').trim()));
          } catch (parseError) {
            reject(new Error(`Invalid ${errorLabel} response: ${parseError.message}`));
          }
        },
      );
    };

    attempt(0);
  });
}

module.exports = { runPythonJsonBridge };
