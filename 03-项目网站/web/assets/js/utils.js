(() => {
  const storageKey = 'gaoyou-theme';
  const root = document.documentElement;

  function getStoredTheme() {
    try {
      return localStorage.getItem(storageKey);
    } catch (error) {
      return null;
    }
  }

  function storeTheme(theme) {
    try {
      localStorage.setItem(storageKey, theme);
    } catch (error) {
      // Ignore storage errors; the button still works for the current page.
    }
  }

  function resolveInitialTheme() {
    const stored = getStoredTheme();
    if (stored === 'light' || stored === 'dark') return stored;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme) {
    root.dataset.theme = theme;
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      const nextTheme = theme === 'dark' ? 'light' : 'dark';
      button.textContent = theme === 'dark' ? '☀' : '☾';
      button.setAttribute('aria-label', theme === 'dark' ? '切换到浅色主题' : '切换到深色主题');
      button.setAttribute('title', theme === 'dark' ? '浅色主题' : '深色主题');
      button.dataset.nextTheme = nextTheme;
    });
  }

  function mountThemeToggle() {
    document.querySelectorAll('.nav-links').forEach((navLinks) => {
      if (navLinks.querySelector('[data-theme-toggle]')) return;
      const button = document.createElement('button');
      button.className = 'theme-toggle';
      button.type = 'button';
      button.dataset.themeToggle = 'true';
      button.addEventListener('click', () => {
        const nextTheme = button.dataset.nextTheme === 'dark' ? 'dark' : 'light';
        storeTheme(nextTheme);
        applyTheme(nextTheme);
      });
      navLinks.appendChild(button);
    });
    applyTheme(root.dataset.theme || resolveInitialTheme());
  }

  applyTheme(resolveInitialTheme());
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountThemeToggle);
  } else {
    mountThemeToggle();
  }
})();

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function summarizeText(value, maxLength = 120) {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!text) return '';
  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1)}…`;
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightText(text, keyword) {
  const raw = String(text || '');
  const query = String(keyword || '').trim();
  if (!query) return escapeHtml(raw);
  const pattern = new RegExp(`(${escapeRegExp(query)})`, 'ig');
  return escapeHtml(raw).replace(pattern, '<mark class="match-mark">$1</mark>');
}

function buildMatchSnippet(candidates, keyword) {
  const query = String(keyword || '').trim().toLowerCase();
  if (!query) return '';
  const matchSource = candidates.find((item) => String(item || '').toLowerCase().includes(query));
  if (!matchSource) return '';
  const source = String(matchSource).replace(/\s+/g, ' ').trim();
  const matchIndex = source.toLowerCase().indexOf(query);
  const start = Math.max(0, matchIndex - 20);
  const end = Math.min(source.length, matchIndex + query.length + 24);
  const snippet = `${start > 0 ? '…' : ''}${source.slice(start, end)}${end < source.length ? '…' : ''}`;
  return highlightText(snippet, keyword);
}

function splitItems(items, visibleCount) {
  return {
    visible: items.slice(0, visibleCount),
    hidden: items.slice(visibleCount),
  };
}

function buildTermHref(id) {
  return `./term.html?id=${encodeURIComponent(String(id))}`;
}

function buildCaseHref(id) {
  return `./case.html?id=${encodeURIComponent(String(id))}`;
}

async function requestJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}
