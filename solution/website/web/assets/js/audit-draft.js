/* Only the current tab and case share a draft; restoring never submits it. */
window.AuditDraft = {
  key(caseId) {
    return 'gaoyou-audit-draft:v1:' + caseId;
  },

  read(caseId, fields) {
    try {
      const saved = JSON.parse(sessionStorage.getItem(this.key(caseId)) || 'null');
      if (!saved || saved.version !== 1 || saved.caseId !== caseId) return null;
      if (fields) {
        const validSteps = steps => Array.isArray(steps) && steps.length === fields.length
          && steps.every((step, index) => step?.field === fields[index]);
        if (!validSteps(saved.generation?.draft) || !validSteps(saved.reviewedSteps)) return null;
      }
      return saved;
    } catch {
      return null;
    }
  },

  write(caseId, data) {
    try {
      sessionStorage.setItem(this.key(caseId), JSON.stringify({ ...data, version: 1, caseId }));
      return true;
    } catch {
      return false;
    }
  },

  clear(caseId) {
    try {
      sessionStorage.removeItem(this.key(caseId));
    } catch {}
  },
};
