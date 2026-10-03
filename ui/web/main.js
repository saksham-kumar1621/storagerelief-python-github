// StorageRelief Frontend Controller
// Interacts with Python Native Backend (pywebview / Edge WebView2)

// Universal bridge: supports pywebview (Python), Tauri v2 (Rust), or mock browser fallback
const invoke = async (cmd, args = {}) => {
  if (window.pywebview && window.pywebview.api) {
    try {
      if (cmd === 'get_available_drives') {
        return await window.pywebview.api.get_available_drives();
      } else if (cmd === 'get_drive_info') {
        return await window.pywebview.api.get_drive_info(args.drive_letter || 'C:\\');
      } else if (cmd === 'scan_storage') {
        return await window.pywebview.api.scan_storage(args.drive_letter || 'C:\\');
      } else if (cmd === 'clean_selected_items') {
        return await window.pywebview.api.clean_selected_items(args.paths || []);
      } else if (cmd === 'open_item_path') {
        return await window.pywebview.api.open_item_path(args.path || '');
      } else if (cmd === 'get_duplicate_scan_targets') {
        return await window.pywebview.api.get_duplicate_scan_targets(args.drive_letter || 'C:\\');
      } else if (cmd === 'scan_duplicates') {
        return await window.pywebview.api.scan_duplicates(args);
      } else if (cmd === 'pick_custom_folder') {
        return await window.pywebview.api.pick_custom_folder();
      }
    } catch (e) {
      console.error(`[Python API Error] ${cmd}:`, e);
      throw e;
    }
  } else if (window.__TAURI__ && window.__TAURI__.core) {
    return await window.__TAURI__.core.invoke(cmd, args);
  } else {
    console.log(`[Mock Runtime Call] ${cmd}`, args);
    return getMockData(cmd, args);
  }
};

// Application State
let state = {
  activeView: 'cleaner', // 'cleaner' | 'duplicates'
  availableDrives: [],
  activeDrive: 'C:\\',
  driveInfo: { total_gb: 447.4, free_gb: 150.2, used_gb: 297.2, percent_free: 33.6 },
  
  // System Cleaner State
  items: [],
  selectedIds: new Set(),
  activeCategory: 'all',
  searchQuery: '',
  isScanning: false,

  // Duplicate Hunter State
  duplicateTargets: [],
  duplicateMinSizeMb: 1.0,
  duplicateResult: null,
  duplicateSelectedIds: new Set(),
  duplicateFilesMap: new Map(), // id -> DuplicateFile
  isDupScanning: false,
};

// Category Icons Mapping (SVG paths, strictly no emojis)
const categoryIcons = {
  ghost_apps: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a7 7 0 0 0-7 7v11l3.5-2 3.5 2 3.5-2 3.5 2V9a7 7 0 0 0-7-7z"/><circle cx="9" cy="9" r="1.2" fill="currentColor"/><circle cx="15" cy="9" r="1.2" fill="currentColor"/></svg>`,
  media_gaming: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="6" width="20" height="12" rx="4"/><line x1="6" y1="12" x2="10" y2="12"/><line x1="8" y1="10" x2="8" y2="14"/><circle cx="15" cy="13" r="1" fill="currentColor"/><circle cx="18" cy="11" r="1" fill="currentColor"/></svg>`,
  browser_caches: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>`,
  system_bloat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`,
  caches: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
  archives: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
  dev_junk: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`,
  virtual_disks: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`,
};

// DOM References
const el = {
  // Navigation
  navModeCleaner: document.getElementById('nav-mode-cleaner'),
  navModeDuplicates: document.getElementById('nav-mode-duplicates'),
  navDupBadge: document.getElementById('nav-dup-badge'),
  viewCleaner: document.getElementById('view-cleaner'),
  viewDuplicates: document.getElementById('view-duplicates'),
  btnScanLabel: document.getElementById('btn-scan-label'),

  // Header Actions
  btnScan: document.getElementById('btn-scan'),
  scanIcon: document.querySelector('.icon-spin-target'),
  statusText: document.getElementById('status-text'),
  scanningOverlay: document.getElementById('scanning-overlay'),

  // Multi-Drive Selector
  driveSelectorWrapper: document.getElementById('drive-selector-wrapper'),
  driveSelectorTrigger: document.getElementById('drive-selector-trigger'),
  driveTriggerIcon: document.getElementById('drive-trigger-icon'),
  activeDriveDisplay: document.getElementById('active-drive-display'),
  activeDriveLabel: document.getElementById('active-drive-label'),
  driveDropdown: document.getElementById('drive-dropdown'),
  driveDropdownList: document.getElementById('drive-dropdown-list'),
  btnRefreshDrives: document.getElementById('btn-refresh-drives'),
  activeDriveTypeBadge: document.getElementById('active-drive-type-badge'),
  activeDriveFsBadge: document.getElementById('active-drive-fs-badge'),

  // System Cleaner Drive Gauge & Stats
  gaugePercent: document.getElementById('gauge-percent'),
  gaugeFill: document.getElementById('gauge-fill'),
  statFree: document.getElementById('stat-free'),
  statUsed: document.getElementById('stat-used'),
  statTotal: document.getElementById('stat-total'),
  linearProgress: document.getElementById('drive-linear-progress'),
  totalReclaimText: document.getElementById('total-reclaim-text'),
  itemsFoundCount: document.getElementById('items-found-count'),
  countSafe: document.getElementById('count-safe'),
  countReview: document.getElementById('count-review'),
  countCaution: document.getElementById('count-caution'),
  btnSelectAllSafe: document.getElementById('btn-select-all-safe'),
  btnDeselectAll: document.getElementById('btn-deselect-all'),
  filterTabs: document.querySelectorAll('.filter-tab'),
  filterSearch: document.getElementById('filter-search'),
  tabAllCount: document.getElementById('tab-all-count'),
  tabGhostCount: document.getElementById('tab-ghost-count'),
  tabGamingCount: document.getElementById('tab-gaming-count'),
  tabBrowserCount: document.getElementById('tab-browser-count'),
  tabSystemCount: document.getElementById('tab-system-count'),
  tabCacheCount: document.getElementById('tab-cache-count'),
  tabArchiveCount: document.getElementById('tab-archive-count'),
  tabDevCount: document.getElementById('tab-dev-count'),
  tabVmCount: document.getElementById('tab-vm-count'),
  itemsContainer: document.getElementById('items-container'),

  // Duplicate Hunter
  dupTargetChips: document.getElementById('dup-target-chips'),
  btnAddFolder: document.getElementById('btn-add-folder'),
  btnRunDupScan: document.getElementById('btn-run-dup-scan'),
  btnDupScanText: document.getElementById('btn-dup-scan-text'),
  dupThresholdBtns: document.querySelectorAll('.threshold-btn'),
  dupClustersCount: document.getElementById('dup-clusters-count'),
  dupTotalReclaimText: document.getElementById('dup-total-reclaim-text'),
  dupScannedStats: document.getElementById('dup-scanned-stats'),
  dupSelectedCount: document.getElementById('dup-selected-count'),
  btnDupSelectAll: document.getElementById('btn-dup-select-all'),
  btnDupDeselectAll: document.getElementById('btn-dup-deselect-all'),
  duplicateGroupsContainer: document.getElementById('duplicate-groups-container'),

  // Footer
  footerSelectedCount: document.getElementById('footer-selected-count'),
  footerSelectedSize: document.getElementById('footer-selected-size'),
  btnClean: document.getElementById('btn-clean'),
  btnCleanText: document.getElementById('btn-clean-text'),

  // Modal
  cleanModal: document.getElementById('clean-modal'),
  modalItemsList: document.getElementById('modal-items-list'),
  modalTotalSize: document.getElementById('modal-total-size'),
  btnCancelClean: document.getElementById('btn-cancel-clean'),
  btnConfirmClean: document.getElementById('btn-confirm-clean'),
  modalClose: document.getElementById('modal-close'),

  // Celebration
  successModal: document.getElementById('success-modal'),
  celebrationReclaimedText: document.getElementById('celebration-reclaimed-text'),
  btnCelebrationClose: document.getElementById('btn-celebration-close'),
};

// Format Bytes
function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Initial Boot
let appInitialized = false;
let listenersSetup = false;

function ensureEventListeners() {
  if (listenersSetup) return;
  listenersSetup = true;
  setupEventListeners();
}

async function initializeApp() {
  if (appInitialized) return;
  appInitialized = true;
  ensureEventListeners();

  try {
    await loadAvailableDrives();
    await loadDuplicateTargets(state.activeDrive);
  } catch (e) {
    console.warn('Initial queries notice:', e);
  }

  // Slight delay to ensure window paint completes before scan kicks off
  setTimeout(async () => {
    await runScan(state.activeDrive);
    // Pre-cache duplicate files in background so counts display instantly
    runDuplicateScan();
  }, 250);
}

window.addEventListener('pywebviewready', () => {
  console.log('[StorageRelief] PyWebView API Ready');
  initializeApp();
});

window.addEventListener('DOMContentLoaded', () => {
  ensureEventListeners();
  if (window.pywebview && window.pywebview.api) {
    initializeApp();
  } else if (window.__TAURI__) {
    initializeApp();
  } else {
    setTimeout(() => {
      if (!appInitialized) {
        console.log('[StorageRelief] Fallback preview initialized');
        initializeApp();
      }
    }, 1200);
  }
});

// Setup Listeners
function setupEventListeners() {
  // Mode Navigation
  el.navModeCleaner.addEventListener('click', () => switchView('cleaner'));
  el.navModeDuplicates.addEventListener('click', () => switchView('duplicates'));

  // Header Scan Button (contextual)
  el.btnScan.addEventListener('click', () => {
    if (state.activeView === 'cleaner') {
      runScan(state.activeDrive);
    } else {
      runDuplicateScan();
    }
  });

  // Multi-Drive Selector Trigger
  if (el.driveSelectorTrigger) {
    el.driveSelectorTrigger.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleDriveDropdown();
    });
  }

  // Rescan Drives Button
  if (el.btnRefreshDrives) {
    el.btnRefreshDrives.addEventListener('click', async (e) => {
      e.stopPropagation();
      el.btnRefreshDrives.classList.add('spinning');
      await loadAvailableDrives();
      setTimeout(() => {
        el.btnRefreshDrives.classList.remove('spinning');
        showToast('Storage partition list updated', 'info');
      }, 500);
    });
  }

  // Close dropdown on outside click or escape
  document.addEventListener('click', (e) => {
    if (el.driveSelectorWrapper && !el.driveSelectorWrapper.contains(e.target)) {
      closeDriveDropdown();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeDriveDropdown();
    }
  });

  // Cleaner Filter Tabs
  el.filterTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      if (tab.dataset.category === 'duplicates') {
        switchView('duplicates');
        return;
      }
      el.filterTabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');
      state.activeCategory = tab.dataset.category;
      renderItemsList();
    });
  });

  // Cleaner Search
  el.filterSearch.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    renderItemsList();
  });

  // Cleaner Selection Controls
  el.btnSelectAllSafe.addEventListener('click', () => {
    state.items.forEach((item) => {
      if (item.risk_level === 'safe') {
        state.selectedIds.add(item.id);
      }
    });
    updateSelectedSummary();
    renderItemsList();
  });

  el.btnDeselectAll.addEventListener('click', () => {
    state.selectedIds.clear();
    updateSelectedSummary();
    renderItemsList();
  });

  // Duplicate Hunter Controls
  el.btnRunDupScan.addEventListener('click', () => runDuplicateScan());

  el.btnAddFolder.addEventListener('click', async () => {
    try {
      const folder = await invoke('pick_custom_folder');
      if (folder) {
        // Add to duplicate targets
        const customId = `custom_${Date.now()}`;
        state.duplicateTargets.push({
          id: customId,
          name: folder.split('\\').pop() || folder,
          path: folder,
          enabled: true,
        });
        renderDuplicateTargetChips();
        showToast(`Added folder: ${folder}`, 'success');
      }
    } catch (err) {
      console.error('Folder pick error:', err);
    }
  });

  // Threshold buttons
  el.dupThresholdBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      el.dupThresholdBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.duplicateMinSizeMb = parseFloat(btn.dataset.mb) || 1.0;
    });
  });

  // Duplicate Selection Controls
  el.btnDupSelectAll.addEventListener('click', () => {
    selectAllDuplicates();
  });

  el.btnDupDeselectAll.addEventListener('click', () => {
    state.duplicateSelectedIds.clear();
    updateDuplicateSelectionSummary();
    renderDuplicateGroups();
  });

  // Footer & Modals
  el.btnClean.addEventListener('click', () => openCleanModal());
  el.btnCancelClean.addEventListener('click', () => closeCleanModal());
  el.modalClose.addEventListener('click', () => closeCleanModal());
  el.btnConfirmClean.addEventListener('click', () => executeClean());
  el.btnCelebrationClose.addEventListener('click', () => {
    el.successModal.classList.add('hidden');
  });
}

// Switch between System Cleaner & Duplicate Hunter
function switchView(viewName) {
  state.activeView = viewName;

  if (viewName === 'cleaner') {
    el.navModeCleaner.classList.add('active');
    el.navModeDuplicates.classList.remove('active');
    el.viewCleaner.classList.remove('hidden');
    el.viewDuplicates.classList.add('hidden');
    const displayLetter = (state.driveInfo && state.driveInfo.display_letter) || 'C:';
    el.btnScanLabel.textContent = `Scan Drive (${displayLetter})`;
    updateSelectedSummary();
  } else {
    el.navModeDuplicates.classList.add('active');
    el.navModeCleaner.classList.remove('active');
    el.viewDuplicates.classList.remove('hidden');
    el.viewCleaner.classList.add('hidden');
    el.btnScanLabel.textContent = 'Find Duplicates';

    if (!state.duplicateResult && !state.isDupScanning) {
      // Auto-trigger duplicate scan on first visit if target folders are ready
      setTimeout(() => runDuplicateScan(), 100);
    } else {
      updateDuplicateSelectionSummary();
    }
  }
}

// ==========================================================================
// Multi-Drive Controller
// ==========================================================================

function getDriveSvgIcon(driveType) {
  if (driveType === 'removable') {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13v-3a2 2 0 0 1 4 0v3"/><rect x="7" y="13" width="10" height="8" rx="1"/><line x1="12" y1="10" x2="12" y2="3"/><line x1="9.5" y1="5.5" x2="14.5" y2="5.5"/></svg>`;
  } else if (driveType === 'network') {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2"/><path d="M6 10v4M18 10v4M2 18h20M12 14v4"/></svg>`;
  }
  // Default NVMe / Fixed Disk
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2" /><rect x="2" y="14" width="20" height="8" rx="2" ry="2" /><line x1="6" y1="6" x2="6.01" y2="6" /><line x1="6" y1="18" x2="6.01" y2="18" /></svg>`;
}

async function loadAvailableDrives() {
  try {
    const drives = await invoke('get_available_drives');
    if (drives && drives.length > 0) {
      state.availableDrives = drives;

      // Select active drive or default to system drive / first drive
      let current = drives.find((d) => d.letter === state.activeDrive);
      if (!current) {
        current = drives.find((d) => d.is_system) || drives[0];
        state.activeDrive = current.letter;
      }
      state.driveInfo = current;

      updateDriveSelectorUI(current);
      renderDriveSelectorDropdown();
      updateDriveUI();
    }
  } catch (err) {
    console.error('Failed to load available drives:', err);
  }
}

function updateDriveSelectorUI(drive) {
  if (!drive) return;
  if (el.activeDriveDisplay) el.activeDriveDisplay.textContent = `Drive (${drive.display_letter})`;
  if (el.activeDriveLabel) el.activeDriveLabel.textContent = drive.label || (drive.is_system ? 'OS' : 'Data');
  if (el.activeDriveTypeBadge) el.activeDriveTypeBadge.textContent = drive.drive_type_label || (drive.is_system ? 'System NVMe' : 'Local Disk');
  if (el.activeDriveFsBadge) el.activeDriveFsBadge.textContent = drive.file_system || 'NTFS';
  if (el.driveTriggerIcon) el.driveTriggerIcon.innerHTML = getDriveSvgIcon(drive.drive_type);
  if (el.btnScanLabel && state.activeView === 'cleaner') {
    el.btnScanLabel.textContent = `Scan Drive (${drive.display_letter})`;
  }
}

function renderDriveSelectorDropdown() {
  if (!el.driveDropdownList) return;
  el.driveDropdownList.innerHTML = '';

  state.availableDrives.forEach((drive) => {
    const isActive = drive.letter === state.activeDrive;
    const usedPercent = 100 - drive.percent_free;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `drive-option ${isActive ? 'active' : ''}`;
    btn.setAttribute('role', 'option');
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');

    btn.innerHTML = `
      <div class="drive-option-top">
        <div class="drive-option-left">
          <div class="drive-option-icon">${getDriveSvgIcon(drive.drive_type)}</div>
          <span class="drive-option-title">${escapeHtml(drive.display_letter)} [${escapeHtml(drive.label)}]</span>
          <span class="drive-option-badge">${escapeHtml(drive.drive_type_label)}</span>
        </div>
        <svg class="drive-option-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
      <div class="drive-option-bottom">
        <span>${drive.free_gb.toFixed(1)} GB Free (${drive.percent_free.toFixed(0)}%)</span>
        <span>${drive.total_gb.toFixed(1)} GB Total</span>
      </div>
      <div class="drive-mini-bar">
        <div class="drive-mini-fill" style="width: ${Math.min(100, Math.max(0, usedPercent))}%;"></div>
      </div>
    `;

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      selectDrive(drive.letter);
    });

    el.driveDropdownList.appendChild(btn);
  });
}

async function selectDrive(driveLetter) {
  state.activeDrive = driveLetter;
  closeDriveDropdown();

  let drive = state.availableDrives.find((d) => d.letter === driveLetter);
  if (!drive) {
    try {
      drive = await invoke('get_drive_info', { drive_letter: driveLetter });
    } catch (e) {
      console.error(e);
    }
  }

  if (drive) {
    state.driveInfo = drive;
    updateDriveSelectorUI(drive);
    renderDriveSelectorDropdown();
    updateDriveUI();
  }

  showToast(`Target set to ${drive ? drive.display_letter : driveLetter} [${drive ? drive.label : ''}]`, 'info');

  // Trigger real-time scanner on newly selected drive
  await runScan(driveLetter);

  // Sync duplicate hunter target library folders for this drive
  await loadDuplicateTargets(driveLetter);
}

function toggleDriveDropdown() {
  if (!el.driveDropdown) return;
  const isHidden = el.driveDropdown.classList.contains('hidden');
  if (isHidden) {
    openDriveDropdown();
  } else {
    closeDriveDropdown();
  }
}

function openDriveDropdown() {
  if (!el.driveDropdown) return;
  el.driveDropdown.classList.remove('hidden');
  if (el.driveSelectorWrapper) el.driveSelectorWrapper.classList.add('open');
  if (el.driveSelectorTrigger) el.driveSelectorTrigger.setAttribute('aria-expanded', 'true');
}

function closeDriveDropdown() {
  if (!el.driveDropdown) return;
  el.driveDropdown.classList.add('hidden');
  if (el.driveSelectorWrapper) el.driveSelectorWrapper.classList.remove('open');
  if (el.driveSelectorTrigger) el.driveSelectorTrigger.setAttribute('aria-expanded', 'false');
}

// Refresh Drive Info
async function refreshDriveInfo(targetDrive) {
  try {
    const driveLetter = targetDrive || state.activeDrive || 'C:\\';
    const info = await invoke('get_drive_info', { drive_letter: driveLetter });
    if (info) {
      state.driveInfo = info;
      updateDriveSelectorUI(info);
      updateDriveUI();
    }
  } catch (err) {
    console.error('Failed to get drive info:', err);
  }
}

// Update Drive UI
function updateDriveUI() {
  const { free_gb, total_gb, used_gb, percent_free } = state.driveInfo;
  el.gaugePercent.textContent = `${percent_free.toFixed(0)}%`;
  el.statFree.textContent = `${free_gb.toFixed(1)} GB`;
  el.statUsed.textContent = `${used_gb.toFixed(1)} GB`;
  el.statTotal.textContent = `${total_gb.toFixed(1)} GB`;

  // Circular gauge stroke animation
  el.gaugeFill.setAttribute('stroke-dasharray', `${percent_free.toFixed(1)}, 100`);

  // Progress Bar
  const usedPercent = 100 - percent_free;
  el.linearProgress.style.width = `${usedPercent.toFixed(1)}%`;

  // Color warning if full
  if (percent_free < 10) {
    el.gaugeFill.style.stroke = 'var(--accent-rose)';
    el.linearProgress.style.background = 'linear-gradient(90deg, #f43f5e, #e11d48)';
  } else if (percent_free < 20) {
    el.gaugeFill.style.stroke = 'var(--accent-amber)';
    el.linearProgress.style.background = 'linear-gradient(90deg, #f59e0b, #d97706)';
  } else {
    el.gaugeFill.style.stroke = 'var(--accent-cyan)';
    el.linearProgress.style.background = 'linear-gradient(90deg, var(--accent-cyan), var(--accent-emerald))';
  }
}

// Run Native Storage Scan
async function runScan(targetDrive) {
  if (state.isScanning) return;
  state.isScanning = true;
  el.scanIcon.classList.add('spin');
  const driveToScan = targetDrive || state.activeDrive || 'C:\\';
  const displayLetter = driveToScan.substring(0, 2);
  el.statusText.textContent = `Scanning ${displayLetter}...`;
  el.scanningOverlay.classList.remove('hidden');

  try {
    const res = await invoke('scan_storage', { drive_letter: driveToScan });
    if (res && res.items) {
      state.items = res.items;
      if (res.drive_info) {
        state.driveInfo = res.drive_info;
        updateDriveSelectorUI(res.drive_info);
      }

      // Auto-select safe items by default
      state.selectedIds.clear();
      state.items.forEach((item) => {
        if (item.selected) {
          state.selectedIds.add(item.id);
        }
      });

      updateDriveUI();
      updateCategoryCounts();
      updateSelectedSummary();
      renderItemsList();
    }
  } catch (err) {
    console.error('Scan failed:', err);
    showToast(`Scan issue: ${err}`, 'error');
  } finally {
    state.isScanning = false;
    el.scanIcon.classList.remove('spin');
    el.statusText.textContent = 'Ready';
    el.scanningOverlay.classList.add('hidden');
  }
}

// Update Badge Counts
function updateCategoryCounts() {
  const counts = {
    all: state.items.length,
    ghost_apps: 0,
    media_gaming: 0,
    browser_caches: 0,
    system_bloat: 0,
    caches: 0,
    archives: 0,
    dev_junk: 0,
    virtual_disks: 0,
  };

  let safeCount = 0;
  let reviewCount = 0;
  let cautionCount = 0;

  state.items.forEach((item) => {
    if (counts[item.category] !== undefined) {
      counts[item.category]++;
    }
    if (item.risk_level === 'safe') safeCount++;
    if (item.risk_level === 'review') reviewCount++;
    if (item.risk_level === 'caution') cautionCount++;
  });

  if (el.tabAllCount) el.tabAllCount.textContent = counts.all;
  if (el.tabGhostCount) el.tabGhostCount.textContent = counts.ghost_apps;
  if (el.tabGamingCount) el.tabGamingCount.textContent = counts.media_gaming;
  if (el.tabBrowserCount) el.tabBrowserCount.textContent = counts.browser_caches;
  if (el.tabSystemCount) el.tabSystemCount.textContent = counts.system_bloat;
  if (el.tabCacheCount) el.tabCacheCount.textContent = counts.caches;
  if (el.tabArchiveCount) el.tabArchiveCount.textContent = counts.archives;
  if (el.tabDevCount) el.tabDevCount.textContent = counts.dev_junk;
  if (el.tabVmCount) el.tabVmCount.textContent = counts.virtual_disks;

  el.itemsFoundCount.textContent = `${counts.all} Items Detected`;
  el.countSafe.textContent = `${safeCount} Zero-Risk`;
  el.countReview.textContent = `${reviewCount} User Review`;
  el.countCaution.textContent = `${cautionCount} Virtual Disks`;
}

// Update Reclaim Summary & Action Buttons
function updateSelectedSummary() {
  if (state.activeView === 'duplicates') {
    updateDuplicateSelectionSummary();
    return;
  }

  let selectedBytes = 0;
  state.items.forEach((item) => {
    if (state.selectedIds.has(item.id)) {
      selectedBytes += item.size_bytes;
    }
  });

  const formatted = formatBytes(selectedBytes);
  el.totalReclaimText.textContent = formatted;
  el.footerSelectedCount.textContent = `${state.selectedIds.size} items`;
  el.footerSelectedSize.textContent = formatted;

  if (state.selectedIds.size > 0) {
    el.btnClean.disabled = false;
    el.btnCleanText.textContent = `Clean Selected (${formatted})`;
  } else {
    el.btnClean.disabled = true;
    el.btnCleanText.textContent = 'Clean Selected (0.00 GB)';
  }
}

// Render Storage Items List
function renderItemsList() {
  const filtered = state.items.filter((item) => {
    const matchesCat = state.activeCategory === 'all' || item.category === state.activeCategory;
    const matchesQuery = !state.searchQuery || 
      item.name.toLowerCase().includes(state.searchQuery) || 
      item.path.toLowerCase().includes(state.searchQuery);
    return matchesCat && matchesQuery;
  });

  if (filtered.length === 0) {
    el.itemsContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-graphic">
          <svg viewBox="0 0 100 100" fill="none" class="graphic-svg">
            <circle cx="50" cy="50" r="44" stroke="rgba(16, 185, 129, 0.2)" stroke-width="1.5" stroke-dasharray="3 3"/>
            <circle cx="50" cy="50" r="26" fill="rgba(16, 185, 129, 0.08)" stroke="var(--accent-emerald)" stroke-width="1.5"/>
            <polyline points="40 50 47 57 60 43" stroke="var(--accent-emerald)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h3>No storage waste found</h3>
        <p>This category is clean! Switch tabs or perform a fresh scan anytime.</p>
      </div>
    `;
    return;
  }

  el.itemsContainer.innerHTML = '';
  filtered.forEach((item) => {
    const card = document.createElement('div');
    const isChecked = state.selectedIds.has(item.id);
    card.className = `storage-item-card ${isChecked ? 'is-selected' : ''}`;

    const iconSvg = categoryIcons[item.category] || categoryIcons.caches;

    card.innerHTML = `
      <div class="item-left">
        <input type="checkbox" class="custom-checkbox" data-id="${item.id}" ${isChecked ? 'checked' : ''} />
        <div class="item-cat-icon ${item.category}">
          ${iconSvg}
        </div>
        <div class="item-details">
          <div class="item-title-row">
            <span class="item-title">${escapeHtml(item.name)}</span>
            <span class="item-badge-risk ${item.risk_level}">${item.risk_level}</span>
          </div>
          <span class="item-desc">${escapeHtml(item.description)}</span>
          <span class="item-path" title="${escapeHtml(item.path)}">${escapeHtml(item.path)}</span>
        </div>
      </div>

      <div class="item-right">
        <span class="item-size">${item.size_formatted}</span>
        <button class="btn-open-explorer" data-path="${escapeHtml(item.path)}" title="Open folder in File Explorer">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
            <polyline points="15 3 21 3 21 9"/>
            <line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </button>
      </div>
    `;

    // Checkbox toggle
    const checkbox = card.querySelector('.custom-checkbox');
    checkbox.addEventListener('change', (e) => {
      if (e.target.checked) {
        state.selectedIds.add(item.id);
        card.classList.add('is-selected');
      } else {
        state.selectedIds.delete(item.id);
        card.classList.remove('is-selected');
      }
      updateSelectedSummary();
    });

    // Explorer launch button
    const btnExplorer = card.querySelector('.btn-open-explorer');
    btnExplorer.addEventListener('click', (e) => {
      e.stopPropagation();
      invoke('open_item_path', { path: item.path });
    });

    el.itemsContainer.appendChild(card);
  });
}

// ==========================================================================
// Duplicate Hunter Functions
// ==========================================================================

async function loadDuplicateTargets(targetDrive) {
  try {
    const driveLetter = targetDrive || state.activeDrive || 'C:\\';
    const targets = await invoke('get_duplicate_scan_targets', { drive_letter: driveLetter });
    if (targets && targets.length > 0) {
      state.duplicateTargets = targets;
      renderDuplicateTargetChips();
    }
  } catch (err) {
    console.error('Failed to load duplicate targets:', err);
  }
}

function renderDuplicateTargetChips() {
  el.dupTargetChips.innerHTML = '';
  state.duplicateTargets.forEach((target) => {
    const chip = document.createElement('div');
    chip.className = `target-chip ${target.enabled ? 'active' : ''}`;
    chip.innerHTML = `
      <div class="target-chip-checkbox">
        ${target.enabled ? '<svg viewBox="0 0 24 24" fill="none" stroke="#000" stroke-width="3" style="width:10px;height:10px;"><polyline points="20 6 9 17 4 12"/></svg>' : ''}
      </div>
      <span>${escapeHtml(target.name)}</span>
    `;

    chip.addEventListener('click', () => {
      target.enabled = !target.enabled;
      renderDuplicateTargetChips();
    });

    el.dupTargetChips.appendChild(chip);
  });
}

async function runDuplicateScan() {
  if (state.isDupScanning) return;
  state.isDupScanning = true;

  const activeDirs = state.duplicateTargets
    .filter((t) => t.enabled)
    .map((t) => t.path);

  if (activeDirs.length === 0) {
    showToast('Please select at least one target folder to scan', 'error');
    state.isDupScanning = false;
    return;
  }

  el.btnDupScanText.textContent = 'Auditing Files...';
  el.statusText.textContent = 'Hunting Duplicates...';
  el.btnRunDupScan.disabled = true;

  try {
    const res = await invoke('scan_duplicates', {
      target_dirs: activeDirs,
      min_size_mb: state.duplicateMinSizeMb,
    });

    if (res) {
      state.duplicateResult = res;
      state.duplicateSelectedIds.clear();
      state.duplicateFilesMap.clear();

      // Populate file map & auto-select duplicates (keep original safe)
      res.groups.forEach((group) => {
        group.files.forEach((file) => {
          state.duplicateFilesMap.set(file.id, file);
          if (file.selected_for_delete) {
            state.duplicateSelectedIds.add(file.id);
          }
        });
      });

      // Update Header Badge
      if (res.duplicate_groups_count > 0) {
        el.navDupBadge.textContent = res.duplicate_groups_count;
        el.navDupBadge.classList.remove('hidden');
      } else {
        el.navDupBadge.classList.add('hidden');
      }

      const tabDupCount = document.getElementById('tab-dup-count');
      if (tabDupCount) {
        tabDupCount.textContent = res.duplicate_groups_count;
      }

      el.dupClustersCount.textContent = `${res.duplicate_groups_count} Clusters Found`;
      el.dupScannedStats.textContent = `${res.total_scanned_files.toLocaleString()} Files Scanned`;

      updateDuplicateSelectionSummary();
      renderDuplicateGroups();
      showToast(`Deduplication finished: ${res.duplicate_groups_count} clusters found!`, 'success');
    }
  } catch (err) {
    console.error('Duplicate scan error:', err);
    showToast(`Deduplication issue: ${err}`, 'error');
  } finally {
    state.isDupScanning = false;
    el.btnDupScanText.textContent = 'Find Duplicate Files';
    el.statusText.textContent = 'Ready';
    el.btnRunDupScan.disabled = false;
  }
}

function updateDuplicateSelectionSummary() {
  let selectedBytes = 0;
  state.duplicateSelectedIds.forEach((id) => {
    const file = state.duplicateFilesMap.get(id);
    if (file) {
      selectedBytes += file.size_bytes;
    }
  });

  const formatted = formatBytes(selectedBytes);
  el.dupTotalReclaimText.textContent = formatted;
  el.dupSelectedCount.textContent = `${state.duplicateSelectedIds.size} Copies Selected`;

  if (state.activeView === 'duplicates') {
    el.footerSelectedCount.textContent = `${state.duplicateSelectedIds.size} duplicates`;
    el.footerSelectedSize.textContent = formatted;

    if (state.duplicateSelectedIds.size > 0) {
      el.btnClean.disabled = false;
      el.btnCleanText.textContent = `Delete Duplicates (${formatted})`;
    } else {
      el.btnClean.disabled = true;
      el.btnCleanText.textContent = 'Delete Duplicates (0.00 GB)';
    }
  }
}

function selectAllDuplicates() {
  state.duplicateSelectedIds.clear();
  state.duplicateFilesMap.forEach((file, id) => {
    // Only select duplicates, always keep the original safe
    if (!file.is_original) {
      state.duplicateSelectedIds.add(id);
    }
  });
  updateDuplicateSelectionSummary();
  renderDuplicateGroups();
}

function renderDuplicateGroups() {
  if (!state.duplicateResult || state.duplicateResult.groups.length === 0) {
    el.duplicateGroupsContainer.innerHTML = `
      <div class="empty-state">
        <div class="empty-graphic">
          <svg viewBox="0 0 100 100" fill="none" class="graphic-svg">
            <circle cx="50" cy="50" r="44" stroke="rgba(16, 185, 129, 0.2)" stroke-width="1.5" stroke-dasharray="3 3"/>
            <circle cx="50" cy="50" r="26" fill="rgba(16, 185, 129, 0.08)" stroke="var(--accent-emerald)" stroke-width="1.5"/>
            <polyline points="40 50 47 57 60 43" stroke="var(--accent-emerald)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <h3>No duplicates detected!</h3>
        <p>Your target directories are clean and free of identical file redundancy.</p>
      </div>
    `;
    return;
  }

  el.duplicateGroupsContainer.innerHTML = '';
  state.duplicateResult.groups.forEach((group) => {
    const card = document.createElement('div');
    card.className = 'duplicate-group-card';

    // Ext clean
    const ext = (group.files[0]?.ext || '.file').replace('.', '');

    let filesHtml = '';
    group.files.forEach((file) => {
      const isChecked = state.duplicateSelectedIds.has(file.id);
      filesHtml += `
        <div class="group-file-row ${file.is_original ? 'is-original' : ''}">
          <div class="file-row-left">
            <input type="checkbox" class="custom-checkbox" data-dup-id="${file.id}" ${isChecked ? 'checked' : ''} />
            <div class="file-row-details">
              <span class="file-role-badge ${file.is_original ? 'original' : 'duplicate'}">
                ${file.is_original ? 'ORIGINAL (Oldest)' : 'DUPLICATE'}
              </span>
              <span class="file-row-path" title="${escapeHtml(file.path)}">${escapeHtml(file.path)}</span>
            </div>
          </div>
          <div class="file-row-right">
            <span class="file-row-date">${file.modified_formatted}</span>
            <button class="btn-open-explorer" data-path="${escapeHtml(file.path)}" title="Open folder in File Explorer">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                <polyline points="15 3 21 3 21 9"/>
                <line x1="10" y1="14" x2="21" y2="3"/>
              </svg>
            </button>
          </div>
        </div>
      `;
    });

    card.innerHTML = `
      <div class="group-header">
        <div class="group-title-col">
          <span class="group-ext-badge">${escapeHtml(ext)}</span>
          <span class="group-name" title="${escapeHtml(group.files[0]?.name || '')}">${escapeHtml(group.files[0]?.name || 'Duplicate Cluster')}</span>
        </div>
        <div class="group-stats">
          <span class="group-stat-copies">${group.files.length} Identical Copies (${group.file_size_formatted} each)</span>
          <span class="group-stat-wasted">+${group.wasted_formatted} Wasted</span>
        </div>
      </div>
      <div class="group-files-list">
        ${filesHtml}
      </div>
    `;

    // Listeners for checkboxes and explorer buttons
    card.querySelectorAll('input[data-dup-id]').forEach((cb) => {
      cb.addEventListener('change', (e) => {
        const fileId = e.target.dataset.dupId;
        if (e.target.checked) {
          state.duplicateSelectedIds.add(fileId);
        } else {
          state.duplicateSelectedIds.delete(fileId);
        }
        updateDuplicateSelectionSummary();
      });
    });

    card.querySelectorAll('.btn-open-explorer').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        invoke('open_item_path', { path: btn.dataset.path });
      });
    });

    el.duplicateGroupsContainer.appendChild(card);
  });
}

// Modal Handling
function openCleanModal() {
  el.modalItemsList.innerHTML = '';
  let totalBytes = 0;

  if (state.activeView === 'duplicates') {
    const selectedFiles = [];
    state.duplicateSelectedIds.forEach((id) => {
      const file = state.duplicateFilesMap.get(id);
      if (file) selectedFiles.push(file);
    });

    if (selectedFiles.length === 0) return;

    selectedFiles.forEach((file) => {
      totalBytes += file.size_bytes;
      const row = document.createElement('div');
      row.className = 'preview-row';
      row.innerHTML = `
        <span class="preview-name" title="${escapeHtml(file.path)}">${escapeHtml(file.name)}</span>
        <span class="preview-size">${file.size_formatted}</span>
      `;
      el.modalItemsList.appendChild(row);
    });
  } else {
    const selectedItems = state.items.filter((i) => state.selectedIds.has(i.id));
    if (selectedItems.length === 0) return;

    selectedItems.forEach((item) => {
      totalBytes += item.size_bytes;
      const row = document.createElement('div');
      row.className = 'preview-row';
      row.innerHTML = `
        <span class="preview-name" title="${escapeHtml(item.path)}">${escapeHtml(item.name)}</span>
        <span class="preview-size">${item.size_formatted}</span>
      `;
      el.modalItemsList.appendChild(row);
    });
  }

  el.modalTotalSize.textContent = formatBytes(totalBytes);
  el.cleanModal.classList.remove('hidden');
}

function closeCleanModal() {
  el.cleanModal.classList.add('hidden');
}

// Execute Clean
async function executeClean() {
  let paths = [];
  let totalReclaimed = 0;

  if (state.activeView === 'duplicates') {
    state.duplicateSelectedIds.forEach((id) => {
      const file = state.duplicateFilesMap.get(id);
      if (file) {
        paths.push(file.path);
        totalReclaimed += file.size_bytes;
      }
    });
  } else {
    const selectedItems = state.items.filter((i) => state.selectedIds.has(i.id));
    paths = selectedItems.map((i) => i.path);
    totalReclaimed = selectedItems.reduce((acc, i) => acc + i.size_bytes, 0);
  }

  if (paths.length === 0) return;

  el.btnConfirmClean.disabled = true;
  el.btnConfirmClean.textContent = 'Cleaning...';

  try {
    await invoke('clean_selected_items', { paths });
    closeCleanModal();

    // Show celebration modal
    el.celebrationReclaimedText.textContent = `+${formatBytes(totalReclaimed)}`;
    el.successModal.classList.remove('hidden');

    // Trigger fresh scan
    await refreshDriveInfo();
    if (state.activeView === 'duplicates') {
      await runDuplicateScan();
    } else {
      await runScan();
    }
  } catch (err) {
    console.error('Clean operation encountered an issue:', err);
    showToast(`Clean issue: ${err}`, 'error');
  } finally {
    el.btnConfirmClean.disabled = false;
    el.btnConfirmClean.textContent = 'Proceed with Clean';
  }
}

// In-App Toast Notification
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;

  const iconSvg = type === 'error'
    ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`
    : type === 'success'
    ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`
    : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`;

  toast.innerHTML = `${iconSvg}<span>${escapeHtml(String(message))}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(12px) scale(0.95)';
    setTimeout(() => toast.remove(), 250);
  }, 4500);
}

// Global safety net for webview stability
window.addEventListener('error', (e) => {
  console.warn('[StorageRelief UI Notice]:', e.error || e.message);
});
window.addEventListener('unhandledrejection', (e) => {
  console.warn('[StorageRelief UI Notice (Promise)]:', e.reason);
});

// Escape HTML utility
function escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Mock data generator for browser preview fallback
function getMockData(cmd, args) {
  if (cmd === 'get_available_drives') {
    return [
      {
        letter: 'C:\\',
        display_letter: 'C:',
        label: 'OS',
        drive_type: 'fixed',
        drive_type_label: 'System NVMe/SSD',
        file_system: 'NTFS',
        total_gb: 447.4,
        free_gb: 150.2,
        used_gb: 297.2,
        percent_free: 33.6,
        is_system: true,
      },
      {
        letter: 'D:\\',
        display_letter: 'D:',
        label: 'Gaming & Repacks',
        drive_type: 'fixed',
        drive_type_label: 'Local NVMe/SSD',
        file_system: 'NTFS',
        total_gb: 953.8,
        free_gb: 420.5,
        used_gb: 533.3,
        percent_free: 44.1,
        is_system: false,
      },
      {
        letter: 'E:\\',
        display_letter: 'E:',
        label: 'Samsung T7 USB',
        drive_type: 'removable',
        drive_type_label: 'Removable USB',
        file_system: 'exFAT',
        total_gb: 931.5,
        free_gb: 610.0,
        used_gb: 321.5,
        percent_free: 65.5,
        is_system: false,
      },
    ];
  }
  if (cmd === 'get_drive_info') {
    return {
      total_bytes: 480436977664,
      free_bytes: 161061273600,
      used_bytes: 319375704064,
      total_gb: 447.4,
      free_gb: 150.2,
      used_gb: 297.2,
      percent_free: 33.6,
      letter: 'C:\\',
      display_letter: 'C:',
      label: 'OS',
      drive_type: 'fixed',
      drive_type_label: 'System NVMe/SSD',
      file_system: 'NTFS',
      is_system: true,
    };
  }
  if (cmd === 'get_duplicate_scan_targets') {
    return [
      { id: 'downloads', name: 'Downloads', path: 'C:\\Users\\User\\Downloads', enabled: true },
      { id: 'videos', name: 'Videos', path: 'C:\\Users\\User\\Videos', enabled: true },
      { id: 'documents', name: 'Documents', path: 'C:\\Users\\User\\Documents', enabled: true },
    ];
  }
  if (cmd === 'scan_duplicates') {
    return {
      total_scanned_files: 1520,
      total_scanned_bytes: 12884901888,
      duplicate_groups_count: 2,
      total_wasted_bytes: 524288000,
      total_wasted_formatted: '500.00 MB',
      groups: [
        {
          group_id: 'group_1',
          hash_digest: 'mock_hash_1',
          file_size: 262144000,
          file_size_formatted: '250.00 MB',
          wasted_bytes: 262144000,
          wasted_formatted: '250.00 MB',
          files: [
            {
              id: 'dup_1_1',
              name: 'Installer_v2.iso',
              path: 'C:\\Users\\User\\Downloads\\Installer_v2.iso',
              size_bytes: 262144000,
              size_formatted: '250.00 MB',
              modified_formatted: 'Oct 01, 2026 12:00',
              is_original: true,
              selected_for_delete: false,
              ext: '.iso',
            },
            {
              id: 'dup_1_2',
              name: 'Installer_v2 (1).iso',
              path: 'C:\\Users\\User\\Downloads\\Installer_v2 (1).iso',
              size_bytes: 262144000,
              size_formatted: '250.00 MB',
              modified_formatted: 'Oct 02, 2026 15:30',
              is_original: false,
              selected_for_delete: true,
              ext: '.iso',
            }
          ]
        }
      ]
    };
  }
  if (cmd === 'scan_storage') {
    return {
      drive_info: {
        letter: 'C:\\',
        display_letter: 'C:',
        label: 'OS',
        drive_type: 'fixed',
        drive_type_label: 'System NVMe/SSD',
        file_system: 'NTFS',
        total_gb: 447.4,
        free_gb: 150.2,
        used_gb: 297.2,
        percent_free: 33.6,
        is_system: true,
      },
      items: [
        {
          id: 'item_1',
          name: 'NVIDIA DirectX Shader Cache',
          path: 'C:\\Users\\User\\AppData\\Local\\NVIDIA\\DXCache',
          size_bytes: 5368709120,
          size_formatted: '5.00 GB',
          category: 'media_gaming',
          category_label: 'Media & Gaming Cache',
          risk_level: 'safe',
          description: 'Precompiled DirectX shaders (auto-rebuilt on game launch)',
          selected: true,
        },
        {
          id: 'item_2',
          name: 'Discord Legacy vapp-1.0.9188',
          path: 'C:\\Users\\User\\AppData\\Local\\Discord\\app-1.0.9188',
          size_bytes: 276824064,
          size_formatted: '263.5 MB',
          category: 'ghost_apps',
          category_label: 'Ghost App Version',
          risk_level: 'safe',
          description: 'Obsolete previous version build of Discord left behind after auto-update',
          selected: true,
        },
        {
          id: 'item_3',
          name: 'Google Chrome Code Cache',
          path: 'C:\\Users\\User\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Code Cache',
          size_bytes: 329469952,
          size_formatted: '314.1 MB',
          category: 'browser_caches',
          category_label: 'Web Browser Cache',
          risk_level: 'safe',
          description: 'V8 compiled JavaScript and WebAssembly code cache',
          selected: true,
        },
        {
          id: 'item_4',
          name: 'Steam UI HTML Cache',
          path: 'C:\\Users\\User\\AppData\\Local\\Steam\\htmlcache',
          size_bytes: 324534272,
          size_formatted: '309.5 MB',
          category: 'media_gaming',
          category_label: 'Media & Gaming Cache',
          risk_level: 'safe',
          description: 'Embedded Chromium web cache for Steam store and library',
          selected: true,
        },
        {
          id: 'item_5',
          name: 'Google Chrome Browser Cache',
          path: 'C:\\Users\\User\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cache',
          size_bytes: 280911872,
          size_formatted: '267.9 MB',
          category: 'browser_caches',
          category_label: 'Web Browser Cache',
          risk_level: 'safe',
          description: 'Cached web pages, images, and network responses',
          selected: true,
        },
        {
          id: 'item_6',
          name: 'Discord Chat Media Cache',
          path: 'C:\\Users\\User\\AppData\\Roaming\\discord\\Cache',
          size_bytes: 257949696,
          size_formatted: '246.0 MB',
          category: 'media_gaming',
          category_label: 'Media & Gaming Cache',
          risk_level: 'safe',
          description: 'Cached images, avatars, and attachments from Discord servers',
          selected: true,
        },
        {
          id: 'item_7',
          name: 'User Temp Directory (%TEMP%)',
          path: 'C:\\Users\\User\\AppData\\Local\\Temp',
          size_bytes: 223870976,
          size_formatted: '213.5 MB',
          category: 'caches',
          category_label: 'Temp & Package Cache',
          risk_level: 'safe',
          description: 'Application temporary work files, installers, and logs',
          selected: true,
        },
        {
          id: 'item_8',
          name: 'Windows User Crash Dumps',
          path: 'C:\\Users\\User\\AppData\\Local\\CrashDumps',
          size_bytes: 212652032,
          size_formatted: '202.8 MB',
          category: 'system_bloat',
          category_label: 'Windows System Junk',
          risk_level: 'safe',
          description: 'Memory dumps created when applications crash (.dmp files)',
          selected: true,
        },
        {
          id: 'item_9',
          name: 'Discord Update Package Cache',
          path: 'C:\\Users\\User\\AppData\\Local\\Discord\\packages',
          size_bytes: 114923520,
          size_formatted: '109.6 MB',
          category: 'ghost_apps',
          category_label: 'Ghost App Version',
          risk_level: 'safe',
          description: 'Accumulated Discord Squirrel installer packages (.nupkg)',
          selected: true,
        },
        {
          id: 'item_10',
          name: 'WhatsApp Desktop Local Cache',
          path: 'C:\\Users\\User\\AppData\\Local\\Packages\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm\\LocalCache',
          size_bytes: 81682432,
          size_formatted: '77.9 MB',
          category: 'media_gaming',
          category_label: 'Media & Gaming Cache',
          risk_level: 'safe',
          description: 'Temporary media and thumbnail cache',
          selected: true,
        },
        {
          id: 'item_11',
          name: 'Windows Explorer Thumbnail Cache',
          path: 'C:\\Users\\User\\AppData\\Local\\Microsoft\\Windows\\Explorer',
          size_bytes: 64278528,
          size_formatted: '61.3 MB',
          category: 'system_bloat',
          category_label: 'Windows System Junk',
          risk_level: 'safe',
          description: 'Cached thumbnail database (.db) for images and videos in Explorer',
          selected: true,
        },
      ],
      total_reclaimable: 7511476224,
    };
  }
  return null;
}
