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

const CJK_STOP_TOKENS = new Set('为什么可以是否如何之其而以为与及或在中于了的是也者则并和将把被从需须未已只均等本该');

function queryTokens(query) {
  const normalizedQuery = String(query || '').toLowerCase();
  return [
    normalizedQuery,
    ...normalizedQuery.split(/[\s,，。；;、？！?]+/),
    ...(normalizedQuery.match(/[\u3400-\u9fff]/g) || []),
  ]
    .map((item) => item.trim())
    .filter((item) => item.length > 1 || !CJK_STOP_TOKENS.has(item))
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

  return (matched.length ? matched : evidences).slice(0, 8).map((evidence) => ({
    work: evidence.work || '',
    quote: compact(evidence.quote, 220),
    role: evidence.role || evidence.evidence_type || '',
  }));
}

function pickRelevantSteps(item, query) {
  const tokens = queryTokens(query);
  return (item.process_steps || [])
    .filter((step) => textMatchesQuery([step.step_type, step.text], tokens))
    .slice(0, 5)
    .map((step) => compact(`${step.step_type || '步骤'}：${step.text}`, 240));
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
      claim: compact(item.claim || item.problem || item.conclusion, 360),
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
    `用户问题：${question}`,
    '',
    `人工标注灰度库材料：${JSON.stringify(annotationCases, null, 2)}`,
    '',
    `主数据库补充材料：${JSON.stringify(mainCases, null, 2)}`,
  ].join('\n');
}

function buildSystemPrompt() {
  return [
    '你是“高邮二王考据过程知识库”的一次性释证助手。当前任务没有上下文记忆，必须完全依赖本次输入的数据库材料。',
    '',
    '总原则：',
    '1. 只基于给定的“人工标注灰度库材料”和“主数据库补充材料”作答，不得虚构书名、引文、作者、术语、声韵关系或数据库中没有的证据。',
    '2. 优先使用人工标注灰度库；只有人工库不足时，才使用主数据库补充。',
    '3. 必须区分“父案例/词群总案支持”和“单字词独立证明”。如果材料来自《广雅疏证》某个词群父案例，不能把父案例的所有方法无差别套给用户问的单个字。',
    '4. 对高邮二王训诂、校勘、通假、声训、同义互证等术语要谨慎。能说“材料支持”就不要说“已经最终证明”；能说“仍需核对”就不要强行定论。',
    '5. 用户通常问一个字词或一句话。你要先判断数据库材料是否直接命中，再给出证据链，再给释证草案。',
    '',
    '输出质量要求：',
    '1. 判断必须清楚，不要只说“成立”。要说明成立的根据和边界，例如“父案例支持，但单字独立论证仍需核对”。',
    '2. 可用证据必须逐条列出，优先使用与用户问题直接相关的材料。每条包含来源、引文或步骤、作用。不要列与问题无关的同组字词。',
    '3. 解析草案必须像学术释证提纲，不要像聊天回答。建议按“立论—取证—释理—结论”组织。',
    '4. 仍需人工核对处必须具体，指出需要核对原文、通假方向、声韵条件、父子案例粒度、是否有直接训释等。',
    '5. 如果证据不足，要明确说不足；不要补造材料。',
    '',
    'JSON 输出硬性要求：',
    '1. 只返回一个 JSON object，不要 Markdown，不要代码块，不要额外解释。',
    '2. 必须包含四个字段：judgment, evidences, draft, reviewNotes。',
    '3. judgment 是字符串，长度 80-220 字。',
    '4. evidences 是字符串数组，3-6 条；每条应包含来源和该证据的作用。',
    '5. draft 是字符串数组，3-5 条；必须呈现释证过程，而不是一句话摘要。',
    '6. reviewNotes 是字符串数组，2-4 条；必须具体可执行。',
    '7. 如果某栏材料不足，也必须返回该字段，并写明“本次材料不足，需人工补证……”，不能留空数组。',
    '',
    '字段示例：',
    '{"judgment":"……","evidences":["《某书》：……，作用是……"],"draft":["立论：……","取证：……","释理：……"],"reviewNotes":["需核对……"]}',
  ].join('\n');
}

function parseModelJson(value) {
  const text = String(value || '')
    .trim()
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/i, '');
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  const candidates = [
    text,
    start >= 0 && end > start ? text.slice(start, end + 1) : '',
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === 'object') return parsed;
    } catch {
      continue;
    }
  }

  return null;
}

function normalizeStructuredAnswer(value) {
  if (!value || typeof value !== 'object') return null;

  const toArray = (item, fallback) => {
    if (Array.isArray(item)) {
      const values = item.map((entry) => String(entry || '').trim()).filter(Boolean);
      return values.length ? values : [fallback];
    }
    const text = String(item || '').trim();
    return text ? [text] : [fallback];
  };

  return {
    judgment: String(value.judgment || '').trim() || '本次模型未返回明确判断，需人工依据下列材料补写。',
    evidences: toArray(value.evidences, '本次模型未返回可用证据条目，需回到人工标注库核对。'),
    draft: toArray(value.draft, '本次模型未返回解析草案，需人工按“立论—取证—释理—结论”补写。'),
    reviewNotes: toArray(value.reviewNotes, '本次模型未返回核对事项，需人工复核原文、证据方向与案例粒度。'),
  };
}

async function requestDeepSeek(config, prompt, apiKey) {
  const requestBody = {
    model: config.DEEPSEEK_MODEL,
    response_format: { type: 'json_object' },
    messages: [
      { role: 'system', content: buildSystemPrompt() },
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
          structuredAnswer: normalizeStructuredAnswer(parseModelJson(payload.choices?.[0]?.message?.content)),
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
