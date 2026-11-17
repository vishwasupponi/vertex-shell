let currentPage = 'home';
let currentPalette = 'Monochrome Black';
let currentMode = 'dark';

// =========================================================================
// UNIVERSAL APP STATE & 24/7 GLOBAL PROGRESS LISTENERS
// =========================================================================
window.VERTEX_STATE = window.VERTEX_STATE || {
  gst_processor: {
    isRunning: false,
    progressPct: 0,
    statusText: 'Ready to process GST returns. Check System Logs for details.',
    statusColor: 'var(--text-secondary)',
    statusHtml: '',
    mode: 'folder',
    srcPath: '',
    selectedFiles: [],
    destPath: '',
    lastOutputDir: '',
    tasks: {
      master_report: true,
      gstr2a: true,
      gstr2b: true,
      organize: true
    }
  },
  gst_downloader: {
    isRunning: false,
    statusText: '',
    statusColor: '',
    username: '',
    password: '',
    fy: '2026-27',
    destPath: '',
    selectedMonths: ['April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December', 'January', 'February', 'March'],
    selectedForms: ['GSTR-1', 'GSTR-2A', 'GSTR-2B', 'GSTR-3B']
  },
  excel_consolidator: {
    isRunning: false,
    progressPct: 0,
    statusText: '',
    statusColor: '',
    statusHtml: '',
    selectedFiles: [],
    uniqueSheets: []
  },
  bank_converter: {
    isRunning: false,
    progressPct: 0,
    progressMsg: '',
    statusText: '',
    statusColor: '',
    statusHtml: '',
    selectedFiles: [],
    cropRects: {},
    cropStatusText: 'Extraction Area Selection: None (Parses whole document)',
    useGemini: false,
    apiKey: '',
    useOcr: true,
    autoOrganize: true,
    pwd: '',
    applyAll: true
  }
};

// 1. GST Processor Listeners
window.onGstProcProgress = function(pct, msg) {
  if (window.VERTEX_STATE && window.VERTEX_STATE.gst_processor) {
    const st = window.VERTEX_STATE.gst_processor;
    st.progressPct = pct;
    st.statusText = msg;
    st.statusColor = 'var(--accent)';
    st.statusHtml = '';
  }
  if (typeof renderGstProcessorState === 'function') renderGstProcessorState();
};

window.onGstProcFinished = function(success, resultData) {
  if (window.VERTEX_STATE && window.VERTEX_STATE.gst_processor) {
    const st = window.VERTEX_STATE.gst_processor;
    st.isRunning = false;
    if (success) {
      st.lastOutputDir = resultData || '';
      st.progressPct = 100;
      st.statusColor = '#10B981';
      st.statusHtml = `✓ GST Processing finished successfully! Output saved in: <strong>${escapeHtml(resultData)}</strong>`;
      st.statusText = `✓ GST Processing finished successfully! Output saved in: ${resultData}`;
    } else {
      st.progressPct = 0;
      st.statusColor = '#EF4444';
      st.statusHtml = '';
      st.statusText = `⚠ Processing Error: ${resultData || 'Unknown error occurred.'}`;
    }
  }
  if (typeof renderGstProcessorState === 'function') renderGstProcessorState();
};

// 2. Excel Consolidator Listeners
window.onExcelProgress = function(pct, msg) {
  if (window.VERTEX_STATE && window.VERTEX_STATE.excel_consolidator) {
    const st = window.VERTEX_STATE.excel_consolidator;
    st.progressPct = pct;
    st.statusText = msg || (pct >= 100 ? "Finalizing workbook..." : "Consolidating files...");
  }
  if (typeof renderExcelConsolidatorState === 'function') renderExcelConsolidatorState();
};

window.onExcelFinished = function(success, resultPath, errMsg) {
  if (window.VERTEX_STATE && window.VERTEX_STATE.excel_consolidator) {
    const st = window.VERTEX_STATE.excel_consolidator;
    st.isRunning = false;
    if (success) {
      st.progressPct = 100;
      st.statusColor = '#10B981';
      st.statusHtml = `✓ Successfully consolidated ${st.selectedFiles.length} files into: <strong>${escapeHtml(resultPath)}</strong>`;
    } else {
      st.progressPct = 0;
      st.statusColor = '#EF4444';
      st.statusText = `⚠ Consolidation Error: ${errMsg || 'Unknown error'}`;
    }
  }
  if (typeof renderExcelConsolidatorState === 'function') renderExcelConsolidatorState();
};

// 3. Bank Converter Listeners
window.onBankProgress = function(pct, msg) {
  if (window.VERTEX_STATE && window.VERTEX_STATE.bank_converter) {
    const st = window.VERTEX_STATE.bank_converter;
    st.progressPct = pct;
    st.progressMsg = msg;
    st.statusText = msg;
  }
  if (typeof renderBankConverterState === 'function') renderBankConverterState();
};

window.onBankFinished = function(success, count, errMsg) {
  if (window.VERTEX_STATE && window.VERTEX_STATE.bank_converter) {
    const st = window.VERTEX_STATE.bank_converter;
    st.isRunning = false;
    if (success) {
      st.progressPct = 100;
      st.statusColor = '#10B981';
      st.statusHtml = `✓ Extracted ${count} transactions! Transaction Editor opened.`;
    } else {
      st.progressPct = 0;
      st.statusColor = '#EF4444';
      st.statusText = `⚠ Extraction Notice: ${errMsg || 'No transactions extracted.'}`;
    }
  }
  if (typeof renderBankConverterState === 'function') renderBankConverterState();
};

// 4. GST Downloader Listeners
window.onGstDownloadProgress = function(msg) {
  if (window.VERTEX_STATE && window.VERTEX_STATE.gst_downloader) {
    const st = window.VERTEX_STATE.gst_downloader;
    st.statusText = msg;
    st.statusColor = 'var(--accent)';
  }
  if (typeof renderGstDownloaderState === 'function') renderGstDownloaderState();
};

window.onGstDownloadFinished = function(success, errMsg) {
  if (window.VERTEX_STATE && window.VERTEX_STATE.gst_downloader) {
    const st = window.VERTEX_STATE.gst_downloader;
    st.isRunning = false;
    if (success) {
      st.statusColor = '#10B981';
      st.statusText = "✓ GST Returns download session finished successfully!";
    } else {
      st.statusColor = '#EF4444';
      st.statusText = `⚠ Download Notice: ${errMsg || 'Session stopped or completed.'}`;
    }
  }
  if (typeof renderGstDownloaderState === 'function') renderGstDownloaderState();
};

// Universal dynamic module state helper (automatically manages any new addon module)
window.getModuleState = function(moduleId, defaultInitialState = {}) {
  if (!window.VERTEX_STATE[moduleId]) {
    window.VERTEX_STATE[moduleId] = Object.assign({
      isRunning: false,
      progressPct: 0,
      statusText: '',
      statusColor: 'var(--text-secondary)',
      statusHtml: '',
      data: {}
    }, defaultInitialState);
  }
  return window.VERTEX_STATE[moduleId];
};

window.addEventListener('pywebviewready', async () => {
  await initDevApp();
});

document.addEventListener('DOMContentLoaded', () => {
  if (!window.pywebview) {
    setTimeout(initDevApp, 100);
  }
  setupSash();
});

async function initDevApp() {
  if (window.pywebview && window.pywebview.api) {
    try {
      const settings = await window.pywebview.api.get_settings();
      if (settings) {
        currentPalette = settings.active_palette || settings.palette || 'Monochrome Black';
        const savedPalette = settings.saved_palette || currentPalette;
        if (settings.mode) currentMode = settings.mode;
        
        document.documentElement.setAttribute('data-palette', currentPalette);
        document.documentElement.setAttribute('data-saved-palette', savedPalette);
        document.documentElement.setAttribute('data-mode', currentMode);
      }
    } catch (e) {}
  }
  // 1. Immediately render Home page with zero delay!
  loadPage('home');

  // 2. Synchronize sidebar modules asynchronously
  setTimeout(syncSidebarModules, 10);

  // 3. Initialize unread notifications count badge
  setTimeout(updateNotificationsBadge, 300);
  setInterval(updateNotificationsBadge, 15000);

  // 4. Initialize sidebar hover auto-peek
  initSidebarHoverAutoPeek();

  // 5. Silently prime notifications feed in background
  if (window.pywebview && window.pywebview.api && window.pywebview.api.refresh_notifications_feed) {
    setTimeout(() => {
      window.pywebview.api.refresh_notifications_feed().catch(() => {});
      setTimeout(updateNotificationsBadge, 2500);
    }, 1500);
  }

  // 6. Silently check for application updates in background
  setTimeout(checkApplicationUpdateSilently, 2000);
}

// =========================================================================
// COLLAPSIBLE SIDEBAR WITH EDGE HOVER AUTO-PEEK
// =========================================================================
let _isSidebarCollapsed = false;
let _peekTimer = null;

function toggleSidebarCollapse(e) {
  if (e && e.stopPropagation) e.stopPropagation();
  const sidebar = document.getElementById('sidebar');
  const sash = document.getElementById('sash');
  const trigger = document.getElementById('sidebar-hover-trigger');
  const btn = document.getElementById('sidebar-collapse-btn');
  if (!sidebar) return;

  if (_peekTimer) clearTimeout(_peekTimer);

  _isSidebarCollapsed = !_isSidebarCollapsed;

  if (_isSidebarCollapsed) {
    sidebar.classList.remove('sidebar-peeking');
    sidebar.classList.add('collapsed');
    if (sash) sash.classList.add('collapsed');
    if (trigger) trigger.classList.add('active');
    if (btn) {
      btn.title = "Pin Sidebar Open";
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>`;
    }
  } else {
    sidebar.classList.remove('collapsed');
    sidebar.classList.remove('sidebar-peeking');
    if (sash) sash.classList.remove('collapsed');
    if (trigger) trigger.classList.remove('active');
    if (btn) {
      btn.title = "Collapse Sidebar";
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>`;
    }
  }
}
window.toggleSidebarCollapse = toggleSidebarCollapse;

function initSidebarHoverAutoPeek() {
  const sidebar = document.getElementById('sidebar');
  const trigger = document.getElementById('sidebar-hover-trigger');
  if (!sidebar || !trigger) return;

  trigger.addEventListener('mouseenter', () => {
    if (_isSidebarCollapsed) {
      clearTimeout(_peekTimer);
      sidebar.classList.add('sidebar-peeking');
    }
  });

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    if (_isSidebarCollapsed) {
      toggleSidebarCollapse();
    }
  });

  sidebar.addEventListener('mouseleave', () => {
    if (_isSidebarCollapsed && sidebar.classList.contains('sidebar-peeking')) {
      _peekTimer = setTimeout(() => {
        if (_isSidebarCollapsed) {
          sidebar.classList.remove('sidebar-peeking');
        }
      }, 250);
    }
  });

  sidebar.addEventListener('mouseenter', () => {
    if (_peekTimer) clearTimeout(_peekTimer);
  });

  // Clicking outside the sidebar while peeking closes it immediately
  document.addEventListener('click', (e) => {
    if (_isSidebarCollapsed && sidebar.classList.contains('sidebar-peeking')) {
      if (!sidebar.contains(e.target) && e.target !== trigger) {
        sidebar.classList.remove('sidebar-peeking');
      }
    }
  });
}

// =========================================================================
// UNREAD NOTIFICATIONS BADGE
// =========================================================================
async function updateNotificationsBadge() {
  const lbl = document.getElementById('nav-notifications-label');
  if (!lbl) return;

  if (window.pywebview && window.pywebview.api && window.pywebview.api.get_unread_notifications_count) {
    try {
      const count = await window.pywebview.api.get_unread_notifications_count();
      if (typeof count === 'number' && count > 0) {
        lbl.innerText = `🔔  Notifications (${count})`;
      } else {
        lbl.innerText = '🔔  Notifications';
      }
    } catch (e) {
      console.warn('[Notifications Badge Error]', e);
    }
  }
}
window.updateNotificationsBadge = updateNotificationsBadge;

function escapeHtml(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
window.escapeHtml = escapeHtml;

async function syncSidebarModules() {
  const stack = document.getElementById('module-nav-stack');
  if (!stack) return;

  if (window.pywebview && window.pywebview.api && window.pywebview.api.get_installed_modules) {
    try {
      const modules = await window.pywebview.api.get_installed_modules();
      if (!modules) return;

      let html = '';
      modules.forEach(mod => {
        if (mod.id === 'ocr_engine' || mod.is_ui_module === false) return;
        if (mod.enabled === false) return;

        let pageKey = mod.page_key || mod.id;
        if (mod.id === 'bank_statement_converter') pageKey = 'bank_converter';
        else if (mod.id === 'gst_portal_downloader') pageKey = 'gst_downloader';

        html += `
          <button class="nav-btn ${currentPage === pageKey ? 'active' : ''}" data-page="${pageKey}" onclick="loadPage('${pageKey}')">
            <span>${escapeHtml(mod.name)}</span>
          </button>
        `;
      });
      stack.innerHTML = html;
    } catch(e) {
      console.error('[SidebarSync Error]', e);
    }
  }
}

async function loadPage(pageName) {
  if (window.cleanupCurrentPage && typeof window.cleanupCurrentPage === 'function') {
    try {
      window.cleanupCurrentPage();
    } catch(err) {
      console.warn('[Page Cleanup Notice]', err);
    }
    window.cleanupCurrentPage = null;
  }

  currentPage = pageName;
  updateActiveNavButton(pageName);

  const viewport = document.getElementById('viewport');
  if (window.pywebview && window.pywebview.api) {
    try {
      const html = await window.pywebview.api.get_page_html(pageName);
      viewport.innerHTML = html;
      
      const scripts = Array.from(viewport.getElementsByTagName('script'));
      for (let i = 0; i < scripts.length; i++) {
        const s = document.createElement('script');
        s.text = scripts[i].text;
        document.body.appendChild(s);
        setTimeout(() => { try { s.remove(); } catch(e) {} }, 50);
      }
      
      // Always guarantee the sidebar navigation is synchronized on every tab switch
      if (typeof syncSidebarModules === 'function') {
        syncSidebarModules();
      }
    } catch (e) {
      viewport.innerHTML = `<div class='original-card' style='padding:20px;'><h3 style='color:var(--danger)'>Error loading page: ${e}</h3></div>`;
    }
  }
}

window.syncSidebarModules = syncSidebarModules;

function navigateToPage(pageName) {
  loadPage(pageName);
}

function updateActiveNavButton(pageName) {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    if (btn.getAttribute('data-page') === pageName) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

let _sashInitialized = false;
function setupSash() {
  if (_sashInitialized) return;
  const sash = document.getElementById('sash');
  const sidebar = document.getElementById('sidebar');
  if (!sash || !sidebar) return;
  _sashInitialized = true;

  let isResizing = false;
  sash.addEventListener('mousedown', () => {
    isResizing = true;
    document.body.style.cursor = 'col-resize';
  });

  window.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const newWidth = Math.max(210, Math.min(420, e.clientX));
    sidebar.style.width = newWidth + 'px';
  });

  window.addEventListener('mouseup', () => {
    isResizing = false;
    document.body.style.cursor = 'default';
  });
}

function escapeHtml(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// =========================================================================
// APPLICATION UPDATE NOTIFICATION & BANNER SYSTEM
// =========================================================================
window.appUpdateInfo = null;

async function checkApplicationUpdateSilently() {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.check_application_updates) return;
  try {
    const res = await window.pywebview.api.check_application_updates();
    if (res && res.has_update) {
      window.appUpdateInfo = res;
      
      // Update sidebar indicator dot
      const dot = document.getElementById('sidebar-update-dot');
      if (dot) dot.style.display = 'inline-block';

      // Check if banner was dismissed in this session
      const isDismissed = sessionStorage.getItem(`update_dismissed_${res.latest_version}`);
      if (!isDismissed) {
        showUpdateBanner(res);
      }
    }
  } catch(e) {
    console.warn('[UpdateChecker] Silent check notice:', e);
  }
}

function showUpdateBanner(info) {
  const banner = document.getElementById('app-update-banner');
  const textEl = document.getElementById('update-banner-text');
  const channelEl = document.getElementById('update-banner-channel');
  if (!banner || !textEl || !channelEl) return;

  const isBeta = info.channel === 'beta';
  channelEl.innerText = isBeta ? 'Beta Preview' : 'Official Stable';
  channelEl.className = `update-channel-badge ${isBeta ? 'beta' : ''}`;
  textEl.innerText = `Update Available: Vertex v${info.latest_version} (Current: v${info.current_version})`;

  banner.style.display = 'flex';
}

function dismissUpdateBanner() {
  const banner = document.getElementById('app-update-banner');
  if (banner) banner.style.display = 'none';
  if (window.appUpdateInfo && window.appUpdateInfo.latest_version) {
    sessionStorage.setItem(`update_dismissed_${window.appUpdateInfo.latest_version}`, '1');
  }
}

function onUpdateBannerAction(action) {
  if (!window.appUpdateInfo) return;
  if (action === 'view') {
    loadPage('notifications');
  } else if (action === 'download') {
    const url = window.appUpdateInfo.download_url || window.appUpdateInfo.release_url;
    if (url) {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.open_external_url) {
        window.pywebview.api.open_external_url(url);
      } else {
        window.open(url, '_blank');
      }
    }
  }
}
