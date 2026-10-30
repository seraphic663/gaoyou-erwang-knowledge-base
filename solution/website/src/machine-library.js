const fs = require('fs');
const { runPythonJsonBridge } = require('./python-bridge');

const WORK_KEYS = new Set(['dushu_zazhi', 'guangya_shuzheng', 'jingyi_shuwen', 'jingzhuan_shici', 'none']);
const TYPES = new Set(['', 'all', 'gloss', 'loan', 'reading', 'emendation', 'emendation_phrase']);
const responseCache = new Map();

function machineQuery(parsedUrl) {
  const values = parsedUrl.query || {};
  const q = String(values.q || '').normalize('NFKC').trim();
  if (Array.from(q).length > 1000) throw new Error('检索词不能超过 1,000 字');
  const view = values.view || 'terms';
  const match = values.match || 'all';
  const position = values.position || 'any';
  const relationType = values.type || values.relation_type || '';
  if (!['terms', 'cases'].includes(view)) throw new Error('无效的展示方式');
  if (!['all', 'any'].includes(match)) throw new Error('无效的多词匹配方式');
  if (!['any', 'source', 'target'].includes(position)) throw new Error('无效的检索位置');
  if (!TYPES.has(relationType)) throw new Error('无效的关系类型');
  const pageValue = String(values.page || '1');
  if (!/^\d+$/.test(pageValue) || Number(pageValue) < 1 || !Number.isSafeInteger(Number(pageValue))) {
    throw new Error('页码须为正整数');
  }
  const workKeys = [...new Set(parsedUrl.queryValues?.work_key || (values.work_key ? [values.work_key] : []))];
  if (workKeys.some(key => !WORK_KEYS.has(key))) throw new Error('无效的来源书');
  return {
    q, view, match, position, relation_type: relationType === 'all' ? '' : relationType,
    work_keys: workKeys, page: Number(pageValue), page_size: 10,
    include_mentions: values.include_mentions !== '0',
  };
}

async function getMachineLibrary(config, command, args = []) {
  let stat;
  try { stat = fs.statSync(config.MACHINE_LIBRARY_DB_FILE); } catch {
    return { available: false, ok: false, message: '机器字词与案例库尚未安装。' };
  }
  const key = JSON.stringify([config.MACHINE_LIBRARY_DB_FILE, stat.mtimeMs, stat.size, command, args]);
  if (responseCache.has(key)) return responseCache.get(key);
  const pending = runPythonJsonBridge(config, {
    bridgeFile: config.MACHINE_LIBRARY_BRIDGE_FILE,
    command, args, dbFile: config.MACHINE_LIBRARY_DB_FILE,
    errorLabel: 'machine library', maxBuffer: 32 * 1024 * 1024,
  });
  responseCache.set(key, pending);
  while (responseCache.size > 32) responseCache.delete(responseCache.keys().next().value);
  try { return await pending; } catch (error) { responseCache.delete(key); throw error; }
}

async function searchMachineLibrary(config, query) {
  let payload = await getMachineLibrary(config, 'search', ['--query-json', JSON.stringify(query)]);
  const lastPage = Math.max(1, Number(payload.total_pages) || 1);
  if (payload.available !== false && query.page > lastPage) {
    payload = await getMachineLibrary(config, 'search', ['--query-json', JSON.stringify({ ...query, page: lastPage })]);
  }
  return payload;
}

module.exports = { machineQuery, getMachineLibrary, searchMachineLibrary };
