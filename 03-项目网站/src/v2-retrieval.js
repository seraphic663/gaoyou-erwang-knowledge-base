const { runPythonJsonBridge } = require('./python-bridge');

function unique(values) {
  return [...new Set(values.map((value) => String(value || '').trim()).filter(Boolean))];
}

function buildRetrievalQuery(item) {
  const terms = (item?.terms || [])
    .flatMap((term) => [term.source_term, term.target_term])
    .filter((value) => Array.from(String(value || '').trim()).length >= 2);
  return unique([
    item?.target_text || item?.case_title,
    ...terms,
  ]).slice(0, 8).join(' ');
}

async function retrieveFromCorpus(config, {
  query,
  workKey = '',
  limit = 8,
} = {}) {
  const args = ['--query', query || '', '--limit', String(limit)];
  if (workKey) args.push('--work-key', workKey);
  const payload = await runPythonJsonBridge(config, {
    bridgeFile: config.V2_RETRIEVAL_BRIDGE_FILE,
    command: 'retrieve',
    args,
    dbFile: config.V2_CORPUS_DB_FILE,
    errorLabel: 'V2 passage retrieval API',
  });
  return {
    ...payload,
    corpus_db: config.V2_CORPUS_DB_FILE,
    work_key: workKey,
    query: query || '',
  };
}

async function retrieveForCase(config, item, { limit = 8 } = {}) {
  const query = buildRetrievalQuery(item);
  const workKey = item?.source_passage?.work_key || item?.target_passage?.work_key || '';
  const sameWork = await retrieveFromCorpus(config, { query, workKey, limit });
  if (sameWork.items?.length || !workKey) return sameWork;

  const fallback = await retrieveFromCorpus(config, { query, limit });
  return {
    ...fallback,
    trace: {
      ...(fallback.trace || {}),
      fallback_from_work_key: workKey,
      fallback_reason: 'same_work_no_match',
    },
  };
}

module.exports = {
  buildRetrievalQuery,
  retrieveForCase,
  retrieveFromCorpus,
};
