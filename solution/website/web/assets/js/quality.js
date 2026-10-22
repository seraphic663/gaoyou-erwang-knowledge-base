(async () => {
  const root = document.querySelector('#qualityMain');
  const reports = [
    { title: '主库结构', endpoint: '/api/schema' },
    { title: 'V2 质量报告', endpoint: '/api/v2/summary' },
  ];
  const results = await Promise.allSettled(reports.map(report => requestJson(report.endpoint)));

  root.innerHTML = results.map((entry, index) => {
    const heading = `<h2>${reports[index].title}</h2>`;
    if (entry.status === 'rejected') {
      return `<section class="card">${heading}<p>${escapeHtml(entry.reason.message)}</p></section>`;
    }
    const data = entry.value;
    const status = data.overall_status
      ? `<p>验收状态：${escapeHtml(data.overall_status)}；结构通过不代表人工审定。</p>`
      : '<p>主数据库的字词、案例和证据结构。</p>';
    const counts = Object.entries(data.counts || {}).map(([key, value]) =>
      `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd>`).join('');
    return `
      <section class="card">
        ${heading}${status}<dl>${counts}</dl>
        <details>
          <summary>完整报告与字段</summary>
          <pre class="site-raw">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
        </details>
      </section>
    `;
  }).join('');
})();
