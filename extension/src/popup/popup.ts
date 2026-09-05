import { PageScanResult } from '../types/schema';

document.addEventListener('DOMContentLoaded', () => {
  const contentEl = document.getElementById('popup-content')!;
  const rescanBtn = document.getElementById('rescan-btn')!;

  function loadScanData(triggerRescan = false): void {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const activeTab = tabs[0];
      if (!activeTab || !activeTab.id) {
        contentEl.innerHTML = '<div class="loading">No active webpage found.</div>';
        return;
      }

      const msgType = triggerRescan ? 'TRIGGER_PAGE_SCAN' : 'GET_PAGE_SCAN';

      chrome.tabs.sendMessage(activeTab.id, { type: msgType }, (response) => {
        if (chrome.runtime.lastError || !response || !response.success) {
          contentEl.innerHTML = `
            <div class="loading" style="color:#f87171">
              Could not communicate with page.<br>
              <small style="color:#94a3b8">Refresh the webpage or ensure it is an HTTP/HTTPS or local page.</small>
            </div>
          `;
          return;
        }

        renderScan(response.data as PageScanResult);
      });
    });
  }

  function renderScan(scan: PageScanResult): void {
    const totalFields = scan.totalFieldCount;
    const formsCount = scan.forms.length;
    const orphanCount = scan.orphanFields.length;

    let formsHtml = '';
    for (const f of scan.forms) {
      formsHtml += `
        <div class="form-item">
          <span class="form-name">${escapeHtml(f.title || f.formId)}</span>
          <span class="form-count">${f.fieldCount} fields</span>
        </div>
      `;
    }

    if (orphanCount > 0) {
      formsHtml += `
        <div class="form-item">
          <span class="form-name" style="color:#93c5fd">Orphan Inputs (No &lt;form&gt;)</span>
          <span class="form-count">${orphanCount} fields</span>
        </div>
      `;
    }

    if (totalFields === 0) {
      formsHtml = '<div class="loading">No form fields detected on this page.</div>';
    }

    contentEl.innerHTML = `
      <div class="stat-grid">
        <div class="stat-card">
          <div class="stat-val">${formsCount}</div>
          <div class="stat-label">HTML Forms</div>
        </div>
        <div class="stat-card">
          <div class="stat-val">${totalFields}</div>
          <div class="stat-label">Total Fields</div>
        </div>
      </div>
      <div class="form-list">
        ${formsHtml}
      </div>
    `;
  }

  rescanBtn.addEventListener('click', () => {
    contentEl.innerHTML = '<div class="loading">Rescanning page...</div>';
    loadScanData(true);
  });

  loadScanData(false);
});

function escapeHtml(str: string): string {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
