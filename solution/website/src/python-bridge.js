const { execFile } = require('child_process');
const fs = require('fs');
const path = require('path');

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function discoverWindowsPythonCandidates() {
  if (process.platform !== 'win32') return [];
  const candidates = [];
  const userProfile = process.env.USERPROFILE || '';
  const localAppData = process.env.LOCALAPPDATA || '';
  const programFiles = process.env.ProgramFiles || '';
  const virtualEnv = process.env.VIRTUAL_ENV || '';

  const addIfExists = (candidate) => {
    if (candidate && fs.existsSync(candidate)) candidates.push(candidate);
  };

  addIfExists(path.join(virtualEnv, 'Scripts', 'python.exe'));
  addIfExists(path.join(userProfile, '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'python.exe'));

  for (const root of [
    path.join(localAppData, 'Programs', 'Python'),
    path.join(programFiles, 'Python'),
  ]) {
    try {
      for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
        if (entry.isDirectory() && /^Python\d+$/i.test(entry.name)) {
          addIfExists(path.join(root, entry.name, 'python.exe'));
        }
      }
    } catch {
      // A missing or inaccessible conventional install directory is optional.
    }
  }
  return candidates;
}

function isUnavailablePythonError(error) {
  return error && (error.code === 'ENOENT' || error.code === 9009);
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
  dbFile = config.V2_DB_FILE,
  errorLabel = 'Python bridge',
  maxBuffer = 8 * 1024 * 1024,
}) {
  const candidates = unique([
    process.env.V2_PYTHON_BIN,
    config.PYTHON_BIN,
    ...discoverWindowsPythonCandidates(),
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
        [bridgeFile, command, ...args, '--db', dbFile],
        {
          cwd: config.WORKSPACE_ROOT,
          maxBuffer,
          windowsHide: true,
        },
        (error, stdout, stderr) => {
          if (isUnavailablePythonError(error)) {
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
