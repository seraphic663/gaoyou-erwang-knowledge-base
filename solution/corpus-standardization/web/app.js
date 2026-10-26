'use strict';

(() => {
  const $ = (id) => document.getElementById(id);
  const cp = (value) => Array.from(String(value ?? ''));
  const slice = (value, start, end) => cp(value).slice(start, end).join('');
  const count = (value) => typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('zh-CN') : '未提供';
  const show = (value) => value === null || value === undefined ? '未提供' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  const flagLabels = { replacement_marker: '缺字／替代符', private_use: '私用区字', supplementary_codepoint: '扩展字符', markup: '原始标记', bracket_marker: '括注标记', chunk_bracket_boundary: '切点在括注内', reading_bracket_truncated: '阅读窗未包含完整括注', unmatched_bracket: '括号未配对', source_bracket_context_uncertain: '原文件有未配对括号', reading_start_hard_boundary: '起点未落在句界', reading_end_hard_boundary: '终点未落在句界', unterminated_frontmatter: '元数据头未闭合', empty_body: '正文为空' };
  const flags = (value) => (Array.isArray(value) ? value.map(String) : value && typeof value === 'object' ? Object.entries(value).filter(([, v]) => Boolean(v)).map(([k]) => k) : value ? [String(value)] : []).map((key) => flagLabels[key] || key);
  const collectionName = (value) => ({ external: '外部典籍', external_high: '外典·高频', external_mid: '外典·中频', external_low: '外典·低频', wang: '二王原著' }[value] || value || '未提供');
  const state = { source: null, chunk: null, sourcePage: 1, chunkPage: 1, mappingPage: 1, sources: [], sourceTotal: 0, chunks: [], chunkTotal: 0, selectedMapping: null, sourceRequest: 0, chunkRequest: 0, listRequest: 0, chunkListRequest: 0, comparison: null, comparisonIndex: 0 };

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
  function run(action) { return Promise.resolve().then(action).catch((error) => notice(`读取未完成：${error.message}。可重试当前操作。`)); }
  async function api(path, params = {}) {
    const url = new URL(path, window.location.origin);
    for (const [key, value] of Object.entries(params)) if (value !== '' && value !== null && value !== undefined) url.searchParams.set(key, value);
    const response = await fetch(url, { cache: 'no-store', headers: { Accept: 'application/json' } });
    let payload;
    try { payload = await response.json(); } catch { throw new Error(`接口没有返回 JSON（HTTP ${response.status}）`); }
    if (!response.ok || payload.ok === false) throw new Error(payload.message || payload.error || `HTTP ${response.status}`);
    return payload;
  }
  function details(label, value) {
    const node = el('details', null, 'meta-more');
    node.append(el('summary', label), el('pre', JSON.stringify(value, null, 2), 'json-view'));
    return node;
  }
  function badge(text, warning = false) { return el('span', text, `chip${warning ? ' warn' : ''}`); }
  function setHash(view = 'browse') {
    const params = new URLSearchParams();
    if (view !== 'browse') params.set('view', view);
    if (state.source) params.set('source', state.source.source_id);
    if (state.chunk) params.set('chunk', state.chunk.chunk_id);
    if (state.source) params.set('page', state.chunkPage);
    const hash = params.toString();
    if (window.location.hash.substring(1) !== hash) history.pushState(null, '', `${window.location.pathname}${window.location.search}${hash ? '#' + hash : ''}`);
  }
  function setView(view) {
    const chosen = ['browse', 'quality', 'comparison'].includes(view) ? view : 'browse';
    for (const name of ['browse', 'quality', 'comparison']) $(`${name}-view`).hidden = name !== chosen;
    for (const [id, active] of [['browse-tab', chosen === 'browse'], ['quality-tab', chosen === 'quality'], ['comparison-tab', chosen === 'comparison']]) {
      $(id).classList.toggle('active', active);
      if (active) $(id).setAttribute('aria-current', 'page'); else $(id).removeAttribute('aria-current');
    }
  }
  function setPanel(panel) {
    for (const name of ['raw', 'normalized', 'mapping']) {
      $(`${name}-panel`).hidden = name !== panel;
      $(`${name}-tab`).classList.toggle('active', name === panel);
      $(`${name}-tab`).setAttribute('aria-selected', String(name === panel));
    }
  }
  function releaseLink(label, href) {
    const link = el('a', label);
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  }
  function renderReleaseStatus(build = {}) {
    const node = $('release-status');
    const mode = build.segmentation_mode;
    const cleanupNote = typeof build.source_cleanup_note === 'string' ? build.source_cleanup_note.trim() : '';
    const cleaned = mode === 'structure-clean' && Boolean(cleanupNote);
    const labels = {
      fixed: 'v1 定长窗口历史版',
      structure: 'v2 结构切分历史版',
      'structure-v2': 'v2 结构切分历史版',
      'structure-v3': 'v3 结构实验历史版',
      'structure-clean': '清理版结构切分',
    };
    node.classList.toggle('is-clean', cleaned);
    node.classList.toggle('is-history', !cleaned);
    if (cleaned) {
      node.replaceChildren(
        el('strong', '已清理字号标签，文字保留。位置对应本版原文；旧版定位请使用历史入口。'),
        el('div', null, 'release-links'),
      );
      node.lastElementChild.append(
        releaseLink('历史 v3 定位与对比 · 3266', 'http://127.0.0.1:3266/#view=comparison'),
        releaseLink('历史 v2 定位与对比 · 3267', 'http://127.0.0.1:3267/#view=comparison'),
      );
      return;
    }
    if (mode === 'structure-clean') {
      node.replaceChildren(
        el('strong', 'structure-clean 通用切分 · 当前输入快照'),
        el('p', '本页位置按当前输入快照解释；发布清理记录未核验。'),
        el('div', null, 'release-links'),
      );
      node.lastElementChild.append(
        releaseLink('历史 v3 定位与对比 · 3266', 'http://127.0.0.1:3266/#view=comparison'),
        releaseLink('历史 v2 定位与对比 · 3267', 'http://127.0.0.1:3267/#view=comparison'),
      );
      return;
    }
    const label = labels[mode] || (mode ? `历史发布 · ${mode}` : '本地语料发布');
    node.replaceChildren(
      el('strong', `${label} · 历史快照冻结`),
      el('p', '本页位置对应此历史发布；清理后的原著使用独立入口。'),
      el('div', null, 'release-links'),
    );
    const links = node.lastElementChild;
    links.append(releaseLink('清理后原著审阅 · 3269', 'http://127.0.0.1:3269/'));
    if (mode !== 'structure-v3') links.append(releaseLink('历史 v3 比较 · 3266', 'http://127.0.0.1:3266/#view=comparison'));
    if (mode !== 'structure' && mode !== 'structure-v2') links.append(releaseLink('历史 v2 比较 · 3267', 'http://127.0.0.1:3267/#view=comparison'));
  }
  async function loadSummary() {
    const data = await api('/api/summary');
    const quality = data.quality || {};
    const sourceCount = typeof data.sources === 'object' ? data.sources?.total : data.sources;
    const chunkCount = typeof data.chunks === 'object' ? data.chunks?.total : data.chunks;
    const metrics = [
      ['来源文件', sourceCount, Object.entries(data.collections || {}).map(([k, v]) => `${collectionName(k)} ${count(typeof v === 'object' ? v.sources ?? v.count : v)}`).join(' · ')],
      ['文本片段', chunkCount, '全库统一切分'],
      ['有标记的块', quality.warning_chunks, '缺字等标记不等于文本错误'],
      ['映射检查错误', quality.mapping_errors, '检查文字保存与位置对应'],
    ];
    $('overview').replaceChildren(...metrics.map(([label, value, note]) => { const node = el('div', null, 'metric'); node.append(el('p', label, 'metric-label'), el('span', count(value), 'metric-value'), el('p', note || '集合统计未提供', 'metric-note')); return node; }));
    const build = data.build || {};
    renderReleaseStatus(build);
    const dateValue = build.created_at_utc ?? build.created_at ?? build.generated_at;
    const dateLabel = dateValue && !Number.isNaN(Date.parse(dateValue)) ? new Date(dateValue).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : show(dateValue);
    $('build-label').textContent = `${show(build.build_id ?? build.id ?? dateLabel)} · ${build.status === 'complete' ? '结构检查通过' : show(build.status)}`;
    $('build-label').title = JSON.stringify(build, null, 2);
  }
  function renderSources() {
    const condition = $('flag-filter').value;
    const items = state.sources.filter((source) => !condition || (flags(source.flags).length > 0) === (condition === 'flagged'));
    $('source-count').textContent = `${count(state.sourceTotal)} 份来源`;
    $('source-list').replaceChildren(...items.map((source) => {
      const button = el('button', null, 'source-item');
      button.classList.toggle('active', source.source_id === state.source?.source_id);
      button.setAttribute('aria-pressed', String(source.source_id === state.source?.source_id));
      button.append(el('span', source.title || '未命名文献', 'source-title'), el('span', `${collectionName(source.collection)} · ${count(source.chunk_count)} 块`, 'source-subtitle'));
      button.title = source.relpath || source.source_id;
      const basename = String(source.relpath || '').split('/').pop();
      if (basename && basename !== `${source.title}.md`) button.append(el('span', basename, 'chunk-id'));
      for (const flag of flags(source.flags).slice(0, 3)) button.append(el('span', flag, 'source-tag warn'));
      button.addEventListener('click', () => run(() => loadSource(source.source_id)));
      return button;
    }));
    if (!items.length) $('source-list').append(el('p', condition ? '本页没有符合标记条件的文献。可切换页码或标记条件。' : '没有匹配的书目。', 'blank-message'));
    $('sources-page').textContent = `${state.sourcePage} / ${Math.max(1, Math.ceil(state.sourceTotal / 30))}`;
    $('sources-prev').disabled = state.sourcePage <= 1;
    $('sources-next').disabled = state.sourcePage * 30 >= state.sourceTotal;
  }
  async function loadSources(page = 1) {
    const request = ++state.listRequest;
    const data = await api('/api/sources', { q: $('search').value.trim(), collection: $('collection').value, page, page_size: 30 });
    if (request !== state.listRequest) return;
    state.sources = data.items || [];
    state.sourceTotal = data.total ?? state.sources.length;
    state.sourcePage = data.page ?? page;
    renderSources();
  }
  function renderSource() {
    const source = state.source;
    $('empty-state').hidden = true;
    $('source-workspace').hidden = false;
    const line = el('div', null, 'meta-line');
    for (const text of [collectionName(source.collection), `${count(source.codepoints)} codepoints`, `${count(source.line_count)} 行`, `${count(source.byte_size)} 字节`, `${count(source.chunk_count)} 检索块`]) line.append(el('span', text));
    const sourceMeta = { source_id: source.source_id, relpath: source.relpath, body_start: source.body_start ?? source.body_start_cp, body_end: source.body_end ?? source.body_end_cp, metadata: source.metadata ?? '未提供', flags: source.flags ?? '未提供' };
    $('source-detail').replaceChildren(el('h2', source.title || '未命名文献'), el('p', source.relpath || source.source_id, 'path'), line, details('查看书目信息与正文位置', sourceMeta));
    renderSources();
  }
  async function loadSource(id, options = {}) {
    notice();
    const request = ++state.sourceRequest;
    ++state.chunkRequest;
    ++state.chunkListRequest;
    state.chunk = null;
    $('reader-content').hidden = true;
    $('chunk-detail').replaceChildren(el('p', '正在读取文献…', 'helper'));
    const data = await api('/api/source', { id });
    if (request !== state.sourceRequest) return;
    state.source = data.source || data;
    state.chunkPage = options.page || 1;
    state.selectedMapping = null;
    renderSource();
    await loadChunks(state.chunkPage, { selectFirst: !options.chunkId, updateHash: options.updateHash !== false });
    if (request !== state.sourceRequest) return;
    if (options.chunkId) await loadChunk(options.chunkId, { updateHash: options.updateHash !== false });
  }
  function renderChunks() {
    $('chunk-count').textContent = `${count(state.chunkTotal)} 块`;
    $('chunk-list').replaceChildren(...state.chunks.map((chunk) => {
      const button = el('button', null, 'chunk-item');
      button.classList.toggle('active', state.chunk?.chunk_id === chunk.chunk_id);
      button.setAttribute('aria-pressed', String(state.chunk?.chunk_id === chunk.chunk_id));
      button.append(el('span', `行 ${show(chunk.line_start)}–${show(chunk.line_end)}`), el('span', `[${show(chunk.start_cp)}, ${show(chunk.end_cp)})`, 'chunk-id'));
      const structure = structureLabel(chunk.structure);
      if (structure) button.append(el('span', structure, 'chunk-structure'));
      button.append(el('span', slice(chunk.preview || '', 0, 90) || '预览未提供', 'chunk-preview'));
      for (const flag of flags(chunk.flags).slice(0, 2)) button.append(el('span', flag, 'source-tag warn'));
      button.addEventListener('click', () => run(() => loadChunk(chunk.chunk_id)));
      return button;
    }));
    if (!state.chunks.length) $('chunk-list').append(el('p', '此文献没有可读取的检索块。', 'blank-message'));
    $('chunks-page').textContent = `${state.chunkPage} / ${Math.max(1, Math.ceil(state.chunkTotal / 20))}`;
    $('chunks-prev').disabled = state.chunkPage <= 1;
    $('chunks-next').disabled = state.chunkPage * 20 >= state.chunkTotal;
  }
  async function loadChunks(page = 1, { selectFirst = true, updateHash = true } = {}) {
    const sourceId = state.source?.source_id;
    if (!sourceId) return;
    const request = ++state.chunkListRequest;
    const data = await api('/api/chunks', { source_id: sourceId, page, page_size: 20 });
    if (request !== state.chunkListRequest || state.source?.source_id !== sourceId) return;
    state.chunks = data.items || [];
    state.chunkTotal = data.total ?? state.chunks.length;
    state.chunkPage = data.page ?? page;
    renderChunks();
    if (selectFirst && state.chunks.length) await loadChunk(state.chunks[0].chunk_id, { updateHash });
    else if (!state.chunks.length) {
      state.chunk = null;
      $('reader-content').hidden = true;
      $('chunk-detail').replaceChildren(el('p', '此页没有检索块。', 'helper'));
      if (updateHash) setHash();
    }
  }
  function glyphInfo(char) {
    const n = char.codePointAt(0);
    if ('□\uFFFD'.includes(char)) return ['glyph-issue', `缺字或替代符 U+${n.toString(16).toUpperCase()}`];
    if ((n >= 0xE000 && n <= 0xF8FF) || (n >= 0xF0000 && n <= 0xFFFFD) || (n >= 0x100000 && n <= 0x10FFFD)) return ['glyph-issue', `私用区字符 U+${n.toString(16).toUpperCase()}；字形取决于字体`];
    if ((n >= 0x3400 && n <= 0x4DBF) || (n >= 0x20000 && n <= 0x323AF)) return ['glyph-rare', `扩展区汉字 U+${n.toString(16).toUpperCase()}；标记不代表错字`];
    return ['', ''];
  }
  function headingPathLabel(path) {
    return (Array.isArray(path) ? path : path ? [path] : []).map((part) => {
      if (typeof part === 'string') return part;
      if (!part || typeof part !== 'object') return '';
      const candidate = part.title ?? part.text ?? part.heading;
      const title = typeof candidate === 'string' ? candidate : '';
      const start = part.start_cp ?? part.start, end = part.end_cp ?? part.end;
      return `${title}${Number.isInteger(start) && Number.isInteger(end) ? ` [${start}, ${end})` : ''}`;
    }).filter(Boolean).join(' › ');
  }
  const roleLabels = { entry: '条目', chapter: '章段', paragraph: '自然段', mixed: '含正文／注释标记', toc: '目录', closure: '段尾标记', paratext: '序跋等前后文', notes: '注释' };
  const associationLabels = { quote_explanation: '引文与解释', attached_note: '正文与注释' };
  const associationName = (basis) => associationLabels[basis] || String(basis || '关联依据未提供');
  function associationNotes(structure) {
    if (!structure || typeof structure !== 'object') return [];
    const notes = [];
    const links = Array.isArray(structure.association_links) ? structure.association_links : [];
    for (const link of links) {
      const sourceRange = Number.isInteger(link.range_start_cp) && Number.isInteger(link.range_end_cp)
        ? `；关联原文区间 ${range(link.range_start_cp, link.range_end_cp)}` : '';
      const limit = link.within_limit === false ? '；关联整体超过单片上限' : '';
      notes.push(`片内关联候选：原文位置 ${show(link.at_cp)}，${associationName(link.basis)}${sourceRange}${limit}`);
    }
    if (structure.association_continued_from_previous) notes.push(`承接前片的关联候选：${associationName(structure.association_continued_from_previous)}`);
    if (structure.association_continues_next) notes.push(`关联候选续至后片：${associationName(structure.association_continues_next)}`);
    return notes;
  }
  function structureLabel(structure) {
    if (!structure || typeof structure !== 'object') return '';
    const path = headingPathLabel(structure.heading_path ?? structure.headings ?? structure.heading);
    const parent = Number.isInteger(structure.parent_start_cp) && Number.isInteger(structure.parent_end_cp) ? `所属条 [${structure.parent_start_cp}, ${structure.parent_end_cp})` : '';
    const part = structure.part_index ?? structure.part;
    const total = structure.part_count ?? structure.parts;
    const suffix = part !== undefined && part !== null ? `第 ${part}${total ? `/${total}` : ''} 段` : '';
    const links = Array.isArray(structure.association_links) && structure.association_links.length ? `关联候选 ${structure.association_links.length} 处` : '';
    const fromPrevious = structure.association_continued_from_previous ? '承接前片关联' : '';
    const toNext = structure.association_continues_next ? '关联续至后片' : '';
    return [path, parent, suffix, links, fromPrevious, toNext].filter(Boolean).join(' · ');
  }
  function renderRaw() {
    const chunk = state.chunk;
    const start = chunk.reading_start_cp ?? chunk.start_cp;
    const text = chunk.reading_text ?? chunk.raw_text ?? '';
    const chars = cp(text);
    const end = chunk.reading_end_cp ?? start + chars.length;
    $('raw-range').textContent = `阅读窗口 [${start}, ${end}) · 检索块 [${chunk.start_cp}, ${chunk.end_cp}) · 窗口外文字未加载。${chunk.reading_notice || '阅读扩展不保证整条论争完整。'}`;
    const fragment = document.createDocumentFragment();
    let previous = null;
    let previousClass = '';
    let previousTitle = '';
    chars.forEach((char, index) => {
      const pos = start + index;
      const [glyphClass, title] = glyphInfo(char);
      const inside = pos >= chunk.start_cp && pos < chunk.end_cp;
      const selected = state.selectedMapping && pos >= state.selectedMapping.raw_start && pos < state.selectedMapping.raw_end;
      const className = `${inside ? 'in-chunk' : 'raw-context'} ${selected ? 'raw-selection' : ''} ${glyphClass}`.trim();
      if (!previous || className !== previousClass || title !== previousTitle) {
        previous = el('span', '', className);
        if (title) previous.title = `${title} · cp ${pos}`;
        fragment.append(previous);
        previousClass = className;
        previousTitle = title;
      }
      previous.append(document.createTextNode(char));
    });
    $('raw-text').replaceChildren(fragment);
  }
  function usableMappings() {
    return (state.chunk?.mapping || []).map((segment, index) => ({ ...segment, index })).filter((segment) => ['norm_start', 'norm_end', 'raw_start', 'raw_end'].every((key) => Number.isFinite(segment[key])));
  }
  function renderNormalized() {
    const chunk = state.chunk;
    const text = cp(chunk.normalized_text || '');
    const mapping = usableMappings();
    const fragment = document.createDocumentFragment();
    let cursor = 0;
    for (const segment of mapping) {
      if (segment.norm_start > cursor) fragment.append(document.createTextNode(text.slice(cursor, segment.norm_start).join('')));
      const value = text.slice(segment.norm_start, segment.norm_end).join('');
      if (value) {
        const oneToOne = segment.norm_end - segment.norm_start === segment.raw_end - segment.raw_start && /^(identity|copy|unchanged|equal|raw)$/i.test(segment.kind || '');
        const parts = oneToOne ? cp(value).map((char, offset) => ({ ...segment, norm_start: segment.norm_start + offset, norm_end: segment.norm_start + offset + 1, raw_start: segment.raw_start + offset, raw_end: segment.raw_start + offset + 1, value: char })) : [{ ...segment, value }];
        for (const part of parts) {
          const button = el('button', part.value, `norm-segment${oneToOne ? '' : ' changed'}`);
          button.title = `规范化 [${part.norm_start}, ${part.norm_end}) → 原文 [${part.raw_start}, ${part.raw_end}) · ${part.kind || '未提供类型'}`;
          button.setAttribute('aria-label', button.title);
          button.addEventListener('click', () => selectMapping(part));
          fragment.append(button);
        }
      }
      cursor = Math.max(cursor, segment.norm_end);
    }
    if (cursor < text.length) fragment.append(document.createTextNode(text.slice(cursor).join('')));
    if (!text.length) fragment.append(el('p', '规范化文本为空。', 'helper'));
    $('normalized-text').replaceChildren(fragment);
  }
  function renderMappings() {
    const mappings = usableMappings();
    const pageSize = 35;
    const rows = mappings.slice((state.mappingPage - 1) * pageSize, state.mappingPage * pageSize);
    $('mapping-list').replaceChildren(...rows.map((segment) => {
      const button = el('button', null, 'mapping-row');
      button.classList.toggle('active', state.selectedMapping?.index === segment.index);
      button.append(el('span', `#${segment.index + 1} · ${segment.kind || '未提供类型'} · norm [${segment.norm_start}, ${segment.norm_end}) → raw [${segment.raw_start}, ${segment.raw_end})`), el('span', slice(state.chunk.normalized_text, segment.norm_start, Math.min(segment.norm_end, segment.norm_start + 90)) || '（无规范化字符／删除段）', 'mapping-excerpt'));
      button.addEventListener('click', () => selectMapping(segment));
      return button;
    }));
    if (!rows.length) $('mapping-list').append(el('p', '映射记录未提供。', 'blank-message'));
    $('mapping-page').textContent = `${state.mappingPage} / ${Math.max(1, Math.ceil(mappings.length / pageSize))} · ${mappings.length} 段`;
    $('mapping-prev').disabled = state.mappingPage <= 1;
    $('mapping-next').disabled = state.mappingPage * pageSize >= mappings.length;
  }
  function selectMapping(segment) {
    state.selectedMapping = segment;
    const chunk = state.chunk;
    const readingStart = chunk.reading_start_cp ?? chunk.start_cp;
    const raw = slice(chunk.reading_text ?? chunk.raw_text, segment.raw_start - readingStart, segment.raw_end - readingStart);
    const normalized = slice(chunk.normalized_text, segment.norm_start, segment.norm_end);
    const box = $('selection-detail');
    box.hidden = false;
    box.replaceChildren(el('strong', `映射 ${segment.index + 1} · ${segment.kind || '未提供类型'}`), el('p', `原文 [${segment.raw_start}, ${segment.raw_end}) ↔ 规范化 [${segment.norm_start}, ${segment.norm_end})`), el('pre', `原文：${raw || '（空）'}\n规范化：${normalized || '（空）'}`));
    const locate = el('button', '在原文中定位');
    locate.addEventListener('click', () => { setPanel('raw'); renderRaw(); $('raw-text').querySelector('.raw-selection')?.scrollIntoView({ block: 'center', behavior: 'smooth' }); });
    const clear = el('button', '清除选区');
    clear.addEventListener('click', () => { state.selectedMapping = null; box.hidden = true; renderRaw(); renderMappings(); });
    box.append(locate, clear);
    renderRaw();
    renderMappings();
  }
  async function loadChunk(id, { updateHash = true } = {}) {
    const request = ++state.chunkRequest;
    notice();
    const data = await api('/api/chunk', { id });
    if (request !== state.chunkRequest) return;
    const chunk = data.chunk || data;
    if (state.source && chunk.source_id !== state.source.source_id) throw new Error('检索块与当前文献不一致，请重新选择来源');
    state.chunk = chunk;
    state.mappingPage = 1;
    state.selectedMapping = null;
    $('selection-detail').hidden = true;
    const reading = chunk.reading_text ?? chunk.raw_text;
    const offset = chunk.start_cp - (chunk.reading_start_cp ?? chunk.start_cp);
    const rawMatches = typeof chunk.raw_text === 'string' && typeof reading === 'string' && slice(reading, offset, offset + chunk.end_cp - chunk.start_cp) === chunk.raw_text && cp(chunk.raw_text).length === chunk.end_cp - chunk.start_cp;
    const row = el('div', null, 'chip-row');
    row.append(badge(roleLabels[chunk.role] || '角色未判别'), badge(`行 ${show(chunk.line_start)}–${show(chunk.line_end)}`));
    const check = badge(typeof chunk.raw_text !== 'string' ? '窗口回读：未提供' : rawMatches ? '窗口回读一致' : '窗口回读不一致', !rawMatches);
    if (rawMatches) check.classList.add('good');
    check.title = '片段文字与阅读上下文中的对应位置一致。';
    row.append(check);
    const structure = structureLabel(chunk.structure);
    if (structure) row.append(badge(structure));
    for (const flag of flags(chunk.flags)) row.append(badge(flag, true));
    $('chunk-detail').replaceChildren(el('h3', `片段 ${show(chunk.ordinal)}`), el('p', `原文 [${chunk.start_cp}, ${chunk.end_cp}) · 检索块 ${count(cp(chunk.raw_text || '').length)} 字 · 阅读窗 ${count(cp(chunk.reading_text || '').length)} 字`, 'helper'), row,
      ...associationNotes(chunk.structure).map((note) => el('p', note, 'helper')),
      details('查看切片标识与结构', { chunk_id: chunk.chunk_id, source_id: chunk.source_id, structure: chunk.structure || '未提供' }));
    $('reader-content').hidden = false;
    renderChunks();
    renderRaw();
    renderNormalized();
    renderMappings();
    if (Number.isInteger(chunk.ordinal) && chunk.ordinal >= 1) {
      const targetPage = Math.floor((chunk.ordinal - 1) / 20) + 1;
      if (targetPage !== state.chunkPage) await loadChunks(targetPage, { selectFirst: false, updateHash: false });
    }
    if (request !== state.chunkRequest) return;
    if (updateHash) setHash();
  }
  const fieldLabels = { mapping_errors: '映射错误', coverage_errors: '覆盖错误', source_hash_mismatches: '源文件哈希不一致', warning_chunks: '有标记的块', sources: '来源数', chunks: '检索块数', checked: '已检查', checked_sources: '检查来源数', checked_chunks: '检查片段数', source_count_discovered: '白名单来源数', failed_source_count: '处理失败来源数', raw_hash_errors: '保存原文哈希错误', window_errors: '窗口范围错误', source_coordinate_errors: '来源坐标错误', line_coordinate_errors: '行坐标错误', foreign_key_errors: '关联错误', sqlite_integrity_errors: '派生库完整性错误', empty_body_sources: '空正文来源数', status: '状态', validation_passed: '机械校验通过', passed: '通过', failed: '失败', total: '总计', raw_roundtrip_errors: '原文回读错误', unknown: '未知', pua: '私用区字符', replacement: '替代符', missing_glyphs: '缺字标记', ...flagLabels };
  function scalarCard(title, object) {
    const card = el('section', null, 'quality-card');
    card.append(el('h3', title));
    if (object === null || object === undefined) { card.append(el('p', '未提供')); return card; }
    if (typeof object !== 'object') { card.append(el('p', show(object))); return card; }
    for (const [key, value] of Object.entries(object)) {
      if (value !== null && typeof value === 'object') continue;
      const line = el('div', null, 'quality-field');
      const shown = key === 'scope' ? '机械结构检查；非语义审定或模型效果' : typeof value === 'boolean' ? (value ? '是' : '否') : typeof value === 'number' && !Number.isInteger(value) ? value.toFixed(3) : key === 'status' ? ({passed:'通过',failed:'未通过'}[value] || show(value)) : show(value);
      line.append(el('span', fieldLabels[key] || key), el('span', shown));
      card.append(line);
    }
    card.append(details('查看完整字段', object));
    return card;
  }
  async function loadQuality() {
    $('quality-content').replaceChildren(el('p', '正在读取质量报告…', 'helper'));
    const data = await api('/api/quality');
    const report = data.report || data;
    const grid = el('div', null, 'quality-grid');
    grid.append(scalarCard('结构检查', {
      '来源文件': report.checked_sources,
      '文本片段': report.checked_chunks,
      '处理失败': report.failed_source_count,
      '原文保存错误': report.raw_hash_errors,
      '位置映射错误': report.mapping_errors,
      '正文遗漏': report.coverage_errors,
      '阅读范围错误': report.window_errors,
      '原文件发生变化': report.source_hash_mismatches,
    }));
    grid.append(scalarCard('字形与切分提示（可重叠）', report.chunk_flag_counts));
    grid.append(details('查看完整检查记录', report));
    const sampleGrid = el('div', null, 'quality-grid');
    const samples = data.samples || report.samples || report.deterministic_samples || [];
    if (Array.isArray(samples)) for (const [index, sample] of samples.entries()) {
      const card = el('section', null, 'quality-card');
      card.append(el('h3', sample.title || `样本 ${index + 1}`), el('p', '每组固定抽取3份来源中的片段', 'helper'));
      if (sample.collection) card.append(el('p', collectionName(sample.collection), 'helper'));
      const row = el('div', null, 'chip-row');
      for (const flag of flags(sample.flags)) row.append(badge(flag, true));
      card.append(row);
      if (sample.source_id || sample.chunk_id) {
        const button = el('button', '打开原文样本');
        button.addEventListener('click', () => run(async () => {
          setView('browse');
          let sourceId = sample.source_id;
          if (!sourceId) { const chunk = await api('/api/chunk', { id: sample.chunk_id }); sourceId = (chunk.chunk || chunk).source_id; }
          await loadSource(sourceId, { chunkId: sample.chunk_id, page: sample.page || sample.chunk_page || 1 });
        }));
        card.append(button);
      }
      card.append(details('样本记录', sample));
      sampleGrid.append(card);
    }
    if (!sampleGrid.childNodes.length) sampleGrid.append(el('p', '接口未提供确定性样本。此处不补造样本。', 'blank-message'));
    $('quality-content').replaceChildren(grid, el('h3', `抽读样本 · ${Array.isArray(samples) ? samples.length : '未提供'}`, 'quality-section'), sampleGrid, details('完整质量报告', data));
  }
  const verdictNames = { improved: '改善', regressed: '退步', tied: '持平', undetermined: '未定' };
  function verdictOf(item) {
    const value = item?.annotation?.verdict;
    return Object.hasOwn(verdictNames, value) ? value : 'undetermined';
  }
  function range(start, end) {
    return Number.isInteger(start) && Number.isInteger(end) ? `[${start}, ${end})` : '位置未提供';
  }
  function compareContext(item) {
    const block = el('section', null, 'comparison-context');
    block.append(el('h3', '同一处原文'), el('p', `${item.path || '路径未提供'} · 锚点 ${show(item.anchor)} · 上下文起点 ${show(item.context_start)}`, 'path'));
    const raw = item.source_context;
    if (typeof raw !== 'string') { block.append(el('p', '原文上下文未提供。', 'blank-message')); return block; }
    const chars = cp(raw);
    const start = item.context_start;
    const body = el('pre', null, 'source-text comparison-source');
    if (!Number.isInteger(start)) body.textContent = raw;
    else {
      const old = item.old || {}, newer = item.new || {};
      const boundaries = [0, chars.length];
      for (const span of [old, newer]) for (const pos of [span.start, span.end]) if (Number.isInteger(pos) && pos > start && pos < start + chars.length) boundaries.push(pos - start);
      const ordered = [...new Set(boundaries)].sort((a, b) => a - b);
      for (let i = 0; i < ordered.length - 1; i++) {
        const from = ordered[i], to = ordered[i + 1], at = start + from;
        const inOld = Number.isInteger(old.start) && Number.isInteger(old.end) && at >= old.start && at < old.end;
        const inNew = Number.isInteger(newer.start) && Number.isInteger(newer.end) && at >= newer.start && at < newer.end;
        body.append(el('span', chars.slice(from, to).join(''), inOld && inNew ? 'comparison-both' : inOld ? 'comparison-old' : inNew ? 'comparison-new' : ''));
      }
    }
    block.append(el('p', '原文仅供判断上下文；底色标记旧块、新块及重合部分。', 'helper'), body);
    return block;
  }
  function scoreView(scores) {
    const box = el('div', null, 'comparison-scores');
    if (!scores || typeof scores !== 'object' || !Object.keys(scores).length) { box.append(el('span', '评分未提供')); return box; }
    const labels = { missing_heading: '缺条头', cut_note: '断注', detached_note: '正文注释脱离', unrelated: '无关条混入', cut_body: '正文截断' };
    for (const [name, value] of Object.entries(scores)) box.append(badge(`${labels[name] || name}：${show(value)}`));
    return box;
  }
  function textDetails(label, value) {
    const node = el('details', null, 'meta-more');
    node.append(el('summary', label), el('pre', value, 'source-text comparison-reading'));
    return node;
  }
  function compareSide(label, side, annotation) {
    const panel = el('section', null, 'comparison-side');
    const span = side && typeof side === 'object' ? side : {};
    const note = annotation && typeof annotation === 'object' ? annotation : {};
    const heading = headingPathLabel(span.heading) || structureLabel(span.structure);
    panel.append(el('h3', label), el('p', `检索块 ${range(span.start, span.end)} · ${typeof span.text === 'string' ? count(cp(span.text).length) : '未提供'} 字${span.role ? ` · 角色候选：${roleLabels[span.role] || span.role}` : ''}`, 'helper'));
    if (span.source_title) panel.append(el('p', `本版标题：${span.source_title}`, 'comparison-heading'));
    if (heading) panel.append(el('p', `识别的章条：${heading}`, 'comparison-heading'));
    if (span.structure && typeof span.structure === 'object') panel.append(details('结构位置', span.structure));
    for (const note of associationNotes(span.structure)) panel.append(el('p', note, 'helper'));
    panel.append(el('pre', typeof span.text === 'string' ? span.text : '片段原文未提供', 'source-text comparison-text'));
    panel.append(el('p', `阅读窗 ${range(span.reading_start, span.reading_end)} · ${typeof span.reading_text === 'string' ? count(cp(span.reading_text).length) : '未提供'} 字`, 'helper'));
    if (typeof span.reading_text === 'string') panel.append(textDetails('展开阅读窗口', span.reading_text));
    panel.append(el('h3', '切分评注'), scoreView(note.scores), el('p', note.reason || '评分理由未提供', 'comparison-reason'));
    return panel;
  }
  function renderComparisonItem(item) {
    const box = $('comparison-detail');
    if (!item || typeof item !== 'object') { box.replaceChildren(el('p', '对比记录未提供。', 'blank-message')); return; }
    const verdict = verdictOf(item);
    const heading = el('div', null, 'comparison-item-heading');
    heading.append(el('h2', `${item.id || ''} · ${item.title || '未命名对比'}`), badge(verdictNames[verdict], verdict === 'regressed'));
    const annotation = item.annotation || {};
    const review = item.review || {};
    const decision = el('section', null, 'comparison-decision');
    decision.append(el('h3', '复核结论'), el('p', `判定：${verdictNames[verdict]} · ${annotation.reason || '总评理由未提供'}`));
    if (Object.keys(review).length) decision.append(details('查看复核记录', review));
    if (item.initial_annotation) decision.append(details('查看初次 AI 标注', item.initial_annotation));
    box.replaceChildren(heading, compareContext(item));
    const sides = el('div', null, 'comparison-sides');
    sides.append(compareSide('旧切分', item.old, annotation.old), compareSide('新切分', item.new, annotation.new));
    box.append(sides, decision);
  }
  function threewayVerdict(item, reference) {
    const value = item?.annotation?.comparisons?.[reference]?.verdict;
    return Object.hasOwn(verdictNames, value) ? value : 'undetermined';
  }
  function compareContextThreeway(item) {
    const block = el('section', null, 'comparison-context');
    block.append(el('h3', '同一处原文'), el('p', `${item.path || '路径未提供'} · 锚点 ${show(item.anchor)} · 上下文 ${range(item.context_start, item.context_end)}`, 'path'));
    const raw = item.source_context;
    if (typeof raw !== 'string') { block.append(el('p', '原文上下文未提供。', 'blank-message')); return block; }
    const body = el('pre', null, 'source-text comparison-source');
    const chars = cp(raw);
    const offset = Number.isInteger(item.anchor) && Number.isInteger(item.context_start) ? item.anchor - item.context_start : -1;
    if (offset >= 0 && offset < chars.length) {
      body.append(document.createTextNode(chars.slice(0, offset).join('')),
                  el('span', chars[offset], 'comparison-anchor'),
                  document.createTextNode(chars.slice(offset + 1).join('')));
    } else body.textContent = raw;
    block.append(el('p', '高亮字符是三种方法共同的原文锚点；各列展示覆盖该锚点的检索块。', 'helper'), body);
    return block;
  }
  function renderThreewayItem(item) {
    const box = $('comparison-detail');
    if (!item || typeof item !== 'object') { box.replaceChildren(el('p', '对比记录未提供。', 'blank-message')); return; }
    const annotation = item.annotation || {}, review = item.review || {};
    const heading = el('div', null, 'comparison-item-heading');
    heading.append(el('h2', `${item.id || ''} · ${item.title || '未命名对比'}`));
    for (const [reference, name] of [['v2', '相对 v2'], ['baseline', '相对 600字基线']]) {
      const verdict = threewayVerdict(item, reference);
      heading.append(badge(`${name}：${verdictNames[verdict]}`, verdict === 'regressed'));
    }
    const sides = el('div', null, 'comparison-sides threeway-sides');
    for (const [method, label] of [['baseline', '600字基线'], ['v2', 'v2 结构版'], ['v3', 'v3 新版']]) {
      sides.append(compareSide(label, item.methods?.[method], annotation.methods?.[method]));
    }
    const decision = el('section', null, 'comparison-decision');
    decision.append(el('h3', '当前判定与复核'));
    for (const [reference, name] of [['v2', 'v3 相对 v2'], ['baseline', 'v3 相对 600字基线']]) {
      const result = annotation.comparisons?.[reference] || {};
      decision.append(el('p', `${name}：${verdictNames[threewayVerdict(item, reference)]} · ${result.reason || '理由未提供'}`));
    }
    decision.append(el('p', `复核状态：${review.status || '未提供'}${review.note ? ` · ${review.note}` : ''}`));
    if (annotation.reading_note) decision.append(el('p', `阅读窗口备注：${annotation.reading_note}`));
    if (item.initial_annotation?.pairwise) decision.append(details('查看匿名初评的三组两两判定', item.initial_annotation.pairwise));
    if (Object.keys(review).length) decision.append(details('查看复核记录', review));
    if (item.initial_annotation) decision.append(details('查看匿名初评', item.initial_annotation));
    box.replaceChildren(heading, compareContextThreeway(item), sides, decision);
  }
  function renderThreeway() {
    const data = state.comparison;
    const items = Array.isArray(data?.items) ? data.items : [];
    const summary = el('section', null, 'comparison-summary');
    summary.append(el('p', `三方对比 ${items.length} 处 · 数量按当前判定统计，未复核项仍为匿名初评`, 'helper'));
    const previous = el('a', '上一轮32处对比 ↗', 'comparison-prior');
    previous.href = 'http://127.0.0.1:3267/#view=comparison';
    previous.target = '_blank'; previous.rel = 'noopener noreferrer';
    summary.append(previous);
    for (const [reference, name] of [['v2', 'v3 相对 v2'], ['baseline', 'v3 相对 600字基线']]) {
      const totals = { improved: 0, regressed: 0, tied: 0, undetermined: 0 };
      for (const item of items) totals[threewayVerdict(item, reference)]++;
      const counts = el('div', null, 'comparison-counts');
      counts.append(el('strong', name));
      for (const [key, label] of Object.entries(verdictNames)) counts.append(el('span', `${label} ${totals[key]}`, `comparison-count ${key}`));
      summary.append(counts);
    }
    if (data.methodology) summary.append(details('样本与判定方法', data.methodology));
    if (data.summary) summary.append(details('对比文件附带汇总', data.summary));
    const layout = el('div', null, 'comparison-layout');
    const catalog = el('aside', null, 'comparison-catalog');
    const filters = {};
    for (const [reference, label] of [['v2', 'v3 相对 v2'], ['baseline', 'v3 相对 600字基线']]) {
      const field = el('div', null, 'comparison-filter-field');
      const selectLabel = el('label', `${label}的结论`);
      const filter = el('select'); filter.id = `comparison-filter-${reference}`;
      selectLabel.htmlFor = filter.id;
      for (const [value, name] of [['', '全部结论'], ...Object.entries(verdictNames)]) {
        const option = el('option', name); option.value = value; filter.append(option);
      }
      field.append(selectLabel, filter); catalog.append(field); filters[reference] = filter;
    }
    const list = el('div', null, 'comparison-list'); list.id = 'comparison-list';
    const selected = (item) => Object.entries(filters).every(([reference, filter]) =>
      !filter.value || threewayVerdict(item, reference) === filter.value);
    const renderList = () => {
      list.replaceChildren(...items.map((item, index) => {
        if (!selected(item)) return null;
        const button = el('button', null, 'comparison-list-item');
        button.classList.toggle('active', index === state.comparisonIndex);
        button.append(el('strong', `${item.id || index + 1} · ${item.title || '对比'}`),
                      el('span', `对 v2 ${verdictNames[threewayVerdict(item, 'v2')]} · 对基线 ${verdictNames[threewayVerdict(item, 'baseline')]}`, 'muted'));
        button.addEventListener('click', () => { state.comparisonIndex = index; renderList(); renderThreewayItem(item); });
        return button;
      }).filter(Boolean));
      if (!list.childNodes.length) list.append(el('p', items.length ? '当前筛选没有对比项。' : '对比文件没有记录。', 'blank-message'));
    };
    for (const filter of Object.values(filters)) filter.addEventListener('change', () => {
      state.comparisonIndex = items.findIndex(selected);
      renderList(); renderThreewayItem(items[state.comparisonIndex]);
    });
    catalog.append(list);
    const detail = el('article', null, 'comparison-detail'); detail.id = 'comparison-detail';
    layout.append(catalog, detail);
    $('comparison-content').replaceChildren(summary, layout);
    if (!items[state.comparisonIndex]) state.comparisonIndex = 0;
    renderList(); renderThreewayItem(items[state.comparisonIndex]);
  }
  function renderComparison() {
    const data = state.comparison;
    if (data?.schema === 'threeway.v1') { renderThreeway(); return; }
    const items = Array.isArray(data?.items) ? data.items : [];
    const totals = { improved: 0, regressed: 0, tied: 0, undetermined: 0 };
    for (const item of items) totals[verdictOf(item)]++;
    const summary = el('section', null, 'comparison-summary');
    summary.append(el('p', `本次对比 ${items.length} 项 · 以下数量按各项复核后的结论统计`, 'helper'));
    const counts = el('div', null, 'comparison-counts');
    for (const [key, label] of Object.entries(verdictNames)) counts.append(el('span', `${label} ${totals[key]}`, `comparison-count ${key}`));
    summary.append(counts);
    if (data.methodology) summary.append(details('样本与判定方法', data.methodology));
    if (data.summary) summary.append(details('对比文件附带汇总', data.summary));
    const layout = el('div', null, 'comparison-layout');
    const catalog = el('aside', null, 'comparison-catalog');
    const selectLabel = el('label', '按结论筛选');
    selectLabel.htmlFor = 'comparison-filter';
    const filter = el('select'); filter.id = 'comparison-filter';
    for (const [value, label] of [['', '全部结论'], ...Object.entries(verdictNames)]) {
      const option = el('option', label); option.value = value; filter.append(option);
    }
    const list = el('div', null, 'comparison-list'); list.id = 'comparison-list';
    const renderList = () => {
      const chosen = filter.value;
      list.replaceChildren(...items.map((item, index) => {
        if (chosen && verdictOf(item) !== chosen) return null;
        const button = el('button', null, 'comparison-list-item');
        button.classList.toggle('active', index === state.comparisonIndex);
        button.append(el('strong', `${item?.id || index + 1} · ${item?.title || '对比'}`), el('span', `${verdictNames[verdictOf(item)]} · ${item?.path || '路径未提供'}`, 'muted'));
        button.addEventListener('click', () => { state.comparisonIndex = index; renderList(); renderComparisonItem(item); });
        return button;
      }).filter(Boolean));
      if (!list.childNodes.length) list.append(el('p', items.length ? '当前筛选没有对比项。' : '对比文件没有记录。', 'blank-message'));
    };
    filter.addEventListener('change', () => {
      const first = items.findIndex((item) => !filter.value || verdictOf(item) === filter.value);
      if (first >= 0) state.comparisonIndex = first;
      renderList();
      renderComparisonItem(items[first]);
    });
    catalog.append(selectLabel, filter, list);
    const detail = el('article', null, 'comparison-detail'); detail.id = 'comparison-detail';
    layout.append(catalog, detail);
    $('comparison-content').replaceChildren(summary, layout);
    renderList();
    renderComparisonItem(items[state.comparisonIndex]);
  }
  async function loadComparison() {
    if (state.comparison) { renderComparison(); return; }
    $('comparison-content').replaceChildren(el('p', '正在读取对比文件…', 'helper'));
    try { state.comparison = await api('/api/comparison'); renderComparison(); }
    catch (error) { $('comparison-content').replaceChildren(el('p', error.message, 'blank-message')); }
  }
  async function restoreHash() {
    const hash = new URLSearchParams(window.location.hash.substring(1));
    const view = hash.get('view');
    setView(view);
    if (view === 'quality') { await loadQuality(); return; }
    if (view === 'comparison') { await loadComparison(); return; }
    let sourceId = hash.get('source');
    const chunkId = hash.get('chunk');
    if (!sourceId && chunkId) { const chunk = await api('/api/chunk', { id: chunkId }); sourceId = (chunk.chunk || chunk).source_id; }
    if (sourceId) await loadSource(sourceId, { chunkId, page: Math.max(1, Number(hash.get('page')) || 1), updateHash: false });
  }
  let debounce;
  $('search').addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(() => run(() => loadSources(1)), 240); });
  $('collection').addEventListener('change', () => run(() => loadSources(1)));
  $('flag-filter').addEventListener('change', renderSources);
  $('sources-prev').addEventListener('click', () => run(() => loadSources(state.sourcePage - 1)));
  $('sources-next').addEventListener('click', () => run(() => loadSources(state.sourcePage + 1)));
  $('chunks-prev').addEventListener('click', () => run(() => loadChunks(state.chunkPage - 1)));
  $('chunks-next').addEventListener('click', () => run(() => loadChunks(state.chunkPage + 1)));
  $('mapping-prev').addEventListener('click', () => { state.mappingPage--; renderMappings(); });
  $('mapping-next').addEventListener('click', () => { state.mappingPage++; renderMappings(); });
  document.querySelectorAll('[data-panel]').forEach((button) => button.addEventListener('click', () => setPanel(button.dataset.panel)));
  $('browse-tab').addEventListener('click', () => { setView('browse'); setHash(); });
  $('quality-tab').addEventListener('click', () => run(async () => { setView('quality'); setHash('quality'); await loadQuality(); }));
  $('comparison-tab').addEventListener('click', () => run(async () => { setView('comparison'); setHash('comparison'); await loadComparison(); }));
  $('quality-refresh').addEventListener('click', () => run(loadQuality));
  window.addEventListener('hashchange', () => run(restoreHash));
  window.addEventListener('popstate', () => { /* hashchange restores hash-based navigation. */ });
  run(async () => {
    const results = await Promise.allSettled([loadSummary(), loadSources(), restoreHash()]);
    const errors = results.filter((result) => result.status === 'rejected').map((result) => result.reason.message);
    if (errors.length) notice(`部分数据尚未载入：${errors.join('；')}。请确认本地服务及构建结果可用。`);
  });
})();
