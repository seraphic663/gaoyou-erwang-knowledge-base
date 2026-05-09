const fs = require('fs');

function compact(value, maxLength = 180) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function readAnnotationSnapshot(config) {
  if (!fs.existsSync(config.ANNOTATION_SNAPSHOT_FILE)) {
    return null;
  }

  return JSON.parse(fs.readFileSync(config.ANNOTATION_SNAPSHOT_FILE, 'utf8').replace(/^\uFEFF/, ''));
}

function caseText(item) {
  return [
    item.case_title,
    item.source_work,
    item.target_text,
    item.problem,
    item.claim,
    item.conclusion,
    ...(item.method_tags || []),
    ...(item.terms || []).flatMap((term) => [term.term, term.related_term, term.relation_type, term.note]),
    ...(item.evidences || []).flatMap((evidence) => [evidence.work, evidence.quote, evidence.role]),
    ...(item.process_steps || []).flatMap((step) => [step.step_type, step.text]),
  ].join(' ');
}

function scoreText(text, query) {
  const normalizedText = text.toLowerCase();
  const normalizedQuery = query.toLowerCase();
  const tokens = normalizedQuery
    .split(/[\s,，。；;、]+/)
    .map((item) => item.trim())
    .filter((item) => item.length >= 2);
  const cjkTokens = Array.from(new Set((normalizedQuery.match(/[\u3400-\u9fff]/g) || [])));

  let score = normalizedText.includes(normalizedQuery) ? 8 : 0;
  tokens.forEach((token) => {
    if (normalizedText.includes(token)) score += 2;
  });
  cjkTokens.forEach((token) => {
    if (normalizedText.includes(token)) score += 1;
  });
  return score;
}

function queryTokens(query) {
  const normalizedQuery = String(query || '').toLowerCase();
  return [
    normalizedQuery,
    ...normalizedQuery.split(/[\s,，。；;、？！?]+/),
    ...(normalizedQuery.match(/[\u3400-\u9fff]/g) || []),
  ]
    .map((item) => item.trim())
    .filter((item, index, items) => item && items.indexOf(item) === index);
}

function textMatchesQuery(values, tokens) {
  const text = values.join(' ').toLowerCase();
  return tokens.some((token) => token && text.includes(token));
}

function pickRelevantEvidences(item, query) {
  const tokens = queryTokens(query);
  const evidences = item.evidences || [];
  const matched = evidences.filter((evidence) => textMatchesQuery([
    evidence.term,
    evidence.work,
    evidence.quote,
    evidence.role,
  ], tokens));

  return (matched.length ? matched : evidences).slice(0, 5).map((evidence) => ({
    work: evidence.work || '',
    quote: compact(evidence.quote, 180),
    role: evidence.role || evidence.evidence_type || '',
  }));
}

function pickRelevantSteps(item, query) {
  const tokens = queryTokens(query);
  return (item.process_steps || [])
    .filter((step) => textMatchesQuery([step.step_type, step.text], tokens))
    .slice(0, 3)
    .map((step) => compact(`${step.step_type || '步骤'}：${step.text}`, 180));
}

function pickAnnotationCases(snapshot, query) {
  return (snapshot?.cases || [])
    .map((item) => ({ item, score: scoreText(caseText(item), query) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
    .map(({ item }) => ({
      title: item.case_title || '未题名案例',
      document: item.source_document?.source_file_name || '未标注文档',
      sourceWork: item.source_work || '',
      claim: compact(item.claim || item.problem || item.conclusion, 220),
      methods: item.method_tags || [],
      relevantSteps: pickRelevantSteps(item, query),
      evidences: pickRelevantEvidences(item, query),
    }));
}

function pickMainCases(dataSource, query) {
  try {
    const result = dataSource.search(query);
    return (result.cases || []).slice(0, 4).map((item) => ({
      title: item.displayTitle || item.title || '未题名案例',
      subtitle: item.displaySubtitle || '',
      term: item.termLabel || item.termName || '',
      method: item.method || '',
      conclusion: compact(item.conclusion || item.preview || item.problem, 220),
      evidences: item.evidenceQuotes || [],
    }));
  } catch {
    return [];
  }
}

function buildPrompt(question, annotationCases, mainCases) {
  return [
    '你是“高邮二王考据过程知识库”的释证助手。请只基于给定材料分析，不要虚构来源。',
    '优先使用“人工标注灰度库”；不足时再使用“主数据库补充”。',
    '不要把父案例的全部方法无差别套到单个字词；必须区分“材料明确支持”和“仍需人工核对”。',
    '只返回 JSON，不要 Markdown，不要代码块。字段必须为：judgment, evidences, draft, reviewNotes。',
    'judgment 为字符串，须直接回答能否成立及理由边界。',
    'evidences、draft、reviewNotes 均为字符串数组；证据充分但不冗长，优先列出与用户问题直接相关的书证、步骤和方法。',
    '如果材料只来自父案例，必须说明“父案例支持”与“单字词仍需核对”的差别。',
    '',
    `用户问题：${question}`,
    '',
    `人工标注灰度库材料：${JSON.stringify(annotationCases, null, 2)}`,
    '',
    `主数据库补充材料：${JSON.stringify(mainCases, null, 2)}`,
  ].join('\n');
}

async function requestDeepSeek(config, prompt, apiKey) {
  const requestBody = {
    model: config.DEEPSEEK_MODEL,
    messages: [
      { role: 'system', content: '你重视证据边界，必须区分数据库材料与AI推断。' },
      { role: 'user', content: prompt },
    ],
  };

  if (config.DEEPSEEK_MODEL !== 'deepseek-reasoner') {
    requestBody.temperature = 0.2;
  }

  const response = await fetch('https://api.deepseek.com/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(requestBody),
  });

  const payload = await response.json().catch(() => ({}));
  return { response, payload };
}

async function callDeepSeek(config, prompt) {
  const apiKeys = [
    config.DEEPSEEK_ANALYSIS_API_KEY,
    config.DEEPSEEK_PARSE_API_KEY,
  ].filter(Boolean);

  if (!apiKeys.length) {
    return {
      ok: false,
      status: 501,
      payload: {
        ok: false,
        message: '未配置 DEEPSEEK_ANALYSIS_API_KEY，AI 解析未启用。',
      },
    };
  }

  let lastError = null;

  for (const [index, apiKey] of apiKeys.entries()) {
    const { response, payload } = await requestDeepSeek(config, prompt, apiKey);
    if (response.ok) {
      return {
        ok: true,
        status: 200,
        payload: {
          ok: true,
          answer: payload.choices?.[0]?.message?.content || '',
          model: payload.model || config.DEEPSEEK_MODEL,
          keySlot: index === 0 ? 'analysis' : 'parse-fallback',
        },
      };
    }

    lastError = {
      status: response.status,
      message: payload.error?.message || `DeepSeek 请求失败：${response.status}`,
    };

    if (![401, 402, 429, 500, 502, 503, 504].includes(response.status)) {
      break;
    }
  }

  return {
    ok: false,
    status: lastError?.status || 502,
    payload: {
      ok: false,
      message: lastError?.message || 'DeepSeek 请求失败。',
    },
  };
}

async function analyzeWithAnnotationAi(config, dataSource, question) {
  const normalizedQuestion = compact(question, 900);
  if (normalizedQuestion.length < 2) {
    return { status: 400, payload: { ok: false, message: '请输入需要解析的字词、句子或问题。' } };
  }

  const annotationSnapshot = readAnnotationSnapshot(config);
  const annotationCases = pickAnnotationCases(annotationSnapshot, normalizedQuestion);
  const mainCases = annotationCases.length >= 3 ? [] : pickMainCases(dataSource, normalizedQuestion);
  const prompt = buildPrompt(normalizedQuestion, annotationCases, mainCases);
  const aiResult = await callDeepSeek(config, prompt);

  return {
    status: aiResult.status,
    payload: {
      ...aiResult.payload,
      sources: {
        annotation: annotationCases,
        main: mainCases,
      },
    },
  };
}

module.exports = { analyzeWithAnnotationAi };
