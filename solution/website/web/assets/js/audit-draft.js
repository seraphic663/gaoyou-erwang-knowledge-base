/* Storage is scoped to this browser tab and V2 case identity, never submitted automatically. */
window.AuditDraft = {
  key(caseId) { return 'gaoyou-audit-draft:v1:' + caseId; },
  read(caseId) { try { return JSON.parse(sessionStorage.getItem(this.key(caseId)) || 'null'); } catch { return null; } },
  write(caseId, data) { try { sessionStorage.setItem(this.key(caseId), JSON.stringify({ version:1, caseId, ...data })); return true; } catch { return false; } },
  clear(caseId) { try { sessionStorage.removeItem(this.key(caseId)); } catch {} },
};
