# Threat Model: StorageRelief Windows Storage Optimizer

## 1. Executive Summary & Architecture Overview

StorageRelief is a native Windows storage optimization and duplicate detection utility. It utilizes a hybrid architecture combining a local Python backend (integrating directly with Windows Win32 APIs, NTFS file system calls, and cryptographic hashing routines) and a Microsoft Edge WebView2 (Chromium-based) front-end communicating over a local Inter-Process Communication (IPC) bridge (`pywebview`).

Because StorageRelief operates directly upon the user's filesystem with capabilities to recursively delete directories, strip read-only attributes, and bypass reparse points, its primary security mandate is **data integrity, non-destructive operation, and defensive privilege separation**.

---

## 2. Assets

| Asset ID | Asset Description | Sensitivity | Impact of Compromise |
| :--- | :--- | :--- | :--- |
| **AST-01** | **User Personal Files** (Documents, Photos, Videos, Code Repositories, Backups) | Critical | Permanent data loss, financial/operational disruption, catastrophic user harm. |
| **AST-02** | **Browser Profile & Credential Databases** (`Login Data`, `Cookies`, `Web Data`, `History`, `Sessions`, `key4.db`) | Critical | Credential theft, session hijacking, identity compromise across user web accounts. |
| **AST-03** | **Host Identity & SSH Keys** (`id_rsa`, `id_ed25519`, `.ssh/`, `.aws/credentials`) | Critical | Host compromise, unauthorized access to remote servers, code repositories, and cloud infrastructure. |
| **AST-04** | **Windows Operating System Integrity** (`C:\Windows`, `System32`, `bootmgr`, `pagefile.sys`, Registry) | Critical | Operating system crash, unbootable Windows installation, Blue Screen of Death (BSOD). |
| **AST-05** | **Storage Metrics & Scan State Accuracy** (Reclaimable space calculations, scan summaries, duplicate groups) | Medium | Misleading statistics, user confusion, accidental selection of non-expendable files. |
| **AST-06** | **Process Execution Boundary** (Integrity of the Python host process and WebView container) | High | Arbitrary code execution (RCE) on the local workstation under the executing user's privileges. |

---

## 3. Trust Boundaries

```
[ External Internet / CDNs ] (Google Fonts CDN: fonts.googleapis.com)
            | (Outbound HTTPS - Unauthenticated)
            v
+-----------------------------------------------------------------------------------+
| TRUST BOUNDARY 1: Web Presentation Layer (Microsoft Edge WebView2 Engine)        |
|  - HTML5 / CSS3 / JavaScript (ui/web/index.html, styles.css, main.js)             |
|  - In-memory UI State (state.items, state.duplicateFilesMap)                      |
|  - DOM Event Handlers & Local Mock Generators                                     |
+-----------------------------------------------------------------------------------+
                                    |
                                    | TRUST BOUNDARY 2: Bidirectional PyWebView IPC Bridge
                                    | (window.pywebview.api.* <---> StorageReliefAPI in main.py)
                                    v
+-----------------------------------------------------------------------------------+
| TRUST BOUNDARY 3: Python Native Application Runtime                               |
|  - main.py (StorageReliefAPI Bridge Controller)                                   |
|  - core/scanner.py (NTFS & Volume Inspection Engine)                              |
|  - core/cleaner.py (Security Firewall & Safe Deletion Subsystem)                  |
|  - core/duplicates.py (Cryptographic Hashing & Smart Original Scoring Engine)     |
+-----------------------------------------------------------------------------------+
            |                                           |
            | TRUST BOUNDARY 4: Win32 API               | TRUST BOUNDARY 5: File System I/O
            v                                           v
[ Windows Kernel / kernel32.dll / shell32.dll ]     [ Local Storage Partitions (NTFS / FAT32) ]
(GetDiskFreeSpaceExW, GetVolumeInformationW)        (User Profiles, %TEMP%, AppData, Program Files)
```

1. **TB-1: External Network vs. Local WebView**: `index.html` fetches web fonts from `https://fonts.googleapis.com` and `https://fonts.gstatic.com`. All other UI assets are local file resources.
2. **TB-2: WebView JavaScript Context vs. Python Native Host**: The Edge WebView2 JavaScript environment communicates with the Python process via `window.pywebview.api`. The bridge does not implement an authentication token, mutual cryptographic handshake, or per-command origin verification.
3. **TB-3: Python Application Logic vs. Windows Filesystem**: The deletion engine executes direct file system operations (`os.remove`, `shutil.rmtree`, `os.unlink`, `os.chmod`) across local partitions.
4. **TB-4: Application Process vs. Windows Subsystem (`subprocess`)**: The application invokes external Windows binaries (`explorer.exe`) to display paths in File Explorer.
5. **TB-5: User Process vs. Operating System Elevation**: The application runs under the security token of the launching Windows user. It does not enforce UAC elevation by default, but inherits high privileges if run as administrator.

---

## 4. Actors & Threat Sources

| Actor | Profile & Motivation | Capabilities |
| :--- | :--- | :--- |
| **Actor 1: Legitimate User** | Non-technical or technical workstation owner seeking storage recovery. | Executes scans, views items, reviews duplicate clusters, clicks clean button. |
| **Actor 2: Malicious Local Software / Malware** | Low-privilege software or script co-located on the workstation attempting privilege abuse or permanent data destruction. | Can write files to disk, create symbolic links/junctions, manipulate files in `%TEMP%` or user folders. |
| **Actor 3: Malicious File Crafter (Indirect)** | Untrusted third-party providing downloaded archives, repositories, or media files. | Can craft directory names or file names with special characters, directory traversal sequences, or HTML tags. |
| **Actor 4: Network Man-in-the-Middle (MitM)** | Active or passive network observer monitoring outbound connections. | Can intercept unauthenticated external requests (e.g. Google Font CDN queries) if TLS is bypassed or forged. |
| **Actor 5: Compromised Upstream Dependency** | Malicious package maintainer or compromised PyPI repository for third-party libraries (`pywebview`, `pythonnet`, `psutil`, `PySide6`). | Can execute arbitrary code during installation or runtime within the application process. |

---

## 5. Entry Points

| Entry Point ID | Component | Interface / Function | Input Data Format |
| :--- | :--- | :--- | :--- |
| **EP-01** | `main.py` | `StorageReliefAPI.clean_selected_items` | Array of path strings `List[str]` or dictionary `{paths: List[str]}` from JavaScript. |
| **EP-02** | `main.py` | `StorageReliefAPI.open_item_path` | Target path string `str` or dictionary `{path: str}` from JavaScript. |
| **EP-03** | `main.py` | `StorageReliefAPI.scan_storage` | Drive letter string `str` (e.g., `"C:\\"`). |
| **EP-04** | `main.py` | `StorageReliefAPI.scan_duplicates` | Options dictionary `{target_dirs: List[str], min_size_mb: float}`. |
| **EP-05** | `main.py` | `StorageReliefAPI.pick_custom_folder` | Windows File Dialog interaction via `tkinter.filedialog`. |
| **EP-06** | `core/scanner.py` | File system directory enumeration (`os.scandir`, `os.walk`) | Raw directory and file metadata on target drives. |
| **EP-07** | `core/duplicates.py`| File hashing routines (`get_quick_partial_hash`, `get_full_hash`) | Raw binary byte contents of user files on disk. |
| **EP-08** | `ui/web/index.html`| External CDN stylesheet loading (`<link rel="stylesheet">`) | Remote CSS and WOFF2 font files from Google CDN. |

---

## 6. Threats (STRIDE Classification)

### 6.1 Spoofing (S)
* **T-01: IPC Caller Spoofing**: Because `window.pywebview.api` has no authentication token or origin validation, any script capable of executing within the WebView context can invoke backend methods as if it were the authentic UI controller.

### 6.2 Tampering (T)
* **T-02: Arbitrary Target Path Tampering in `clean_selected_items`**: The frontend sends an arbitrary array of paths to `clean_selected_items(paths)`. The backend checks each path against `is_path_protected_by_firewall()`, but does **not** check whether the path was actually discovered during a scan. If an attacker or malicious script manipulates the IPC payload, arbitrary non-blacklisted files (e.g., `C:\Users\<User>\Documents\Taxes\report.pdf`) can be deleted.
* **T-03: TOCTOU (Time-of-Check to Time-of-Use) Symlink Race**: An attacker or concurrent process could replace a verified harmless temporary file with a junction or symbolic link pointing to a critical system or personal folder immediately after the pre-deletion check passes.

### 6.3 Repudiation (R)
* **T-04: Lack of Persistent Audit Logging**: Deletions performed by `clean_selected_paths` are returned to the frontend and logged only to transient `sys.stderr` or browser console upon error. No permanent on-disk audit log records which files were deleted, when, or under what user context.

### 6.4 Information Disclosure (I)
* **T-05: Local Directory Structure & Username Leaks in Logs**: File paths containing local user account names, sensitive project names, or confidential folder names are logged to `sys.stderr` or browser developer console during runtime errors.
* **T-06: Outbound Network Information Leak via Google Fonts CDN**: When `index.html` loads fonts from `fonts.googleapis.com` and `fonts.gstatic.com`, the user's IP address, User-Agent, and workstation launch time are transmitted to external Google servers, conflicting with the "100% offline / Zero Telemetry" security claim in `SECURITY.md`.

### 6.5 Denial of Service (DoS)
* **T-07: Deep Directory Traversal / Pathological Directory Nesting**: Scanning directory structures with unbounded recursion or deeply nested paths can cause high CPU utilization, memory exhaustion, or long unresponsiveness.
* **T-08: Partial Deletion False Positive Reporting**: In `core/cleaner.py` line 314, if `shutil.rmtree` fails but any child file was removed (`partial_deleted > 0`), the function returns `(True, "")`. The frontend treats the entire folder as deleted and celebrates the full reclaimed capacity, even though the folder still occupies disk space.

### 6.6 Elevation of Privilege (EoP)
* **T-09: Uncontrolled Execution via Explorer Process Invocation**: In `core/cleaner.py` line 358-360, `subprocess.Popen(["explorer.exe", f"/select,{norm_path}"])` is invoked on user click. If path validation allows crafted arguments or malicious protocol handlers, unexpected behavior could be triggered in the Windows Shell.
* **T-10: Insecure Installer Directory / DLL Hijacking Risk**: `installer.iss` uses `DefaultDirName={autopf}\{#MyAppName}` with `PrivilegesRequired=lowest`. When installed under local user AppData by a non-admin, non-elevated applications can write into the folder, creating potential DLL hijacking surfaces if Python loads runtime DLLs from the application directory.

---

## 7. Concrete Attack Scenarios

### Scenario 1: Arbitrary File Deletion via IPC Bridge Manipulation
1. **Pre-condition**: StorageRelief is running.
2. **Attack Vector**: An adversary leverages an XSS flaw, injected script, or debugging bridge to execute:
   ```javascript
   window.pywebview.api.clean_selected_items({
     paths: ["C:\\Users\\Victim\\Documents\\Confidential_Financial_Model.xlsx"]
   });
   ```
3. **Execution**:
   - `main.py` unpacks `target_paths`.
   - `safe_delete_path` calls `is_path_protected_by_firewall`.
   - The path is NOT in `FORBIDDEN_CRITICAL_FILES` (it is an Excel file, not `login data` or `id_rsa`).
   - The path is NOT a root folder (it is inside a subfolder of `Documents`, not `Documents` itself).
   - `os.remove` is executed.
4. **Impact**: Permanent, unrecoverable data loss of non-blacklisted user documents.

### Scenario 2: Symlink / Junction Substitution (TOCTOU)
1. **Pre-condition**: User scans secondary drive or temp directory.
2. **Attack Vector**: A malicious local script creates a temporary file in `%TEMP%\innocent.tmp`. The scanner detects it. Before the user clicks "Proceed with Clean", the attacker deletes `innocent.tmp` and creates a junction `innocent.tmp` pointing to `C:\Users\Victim\AppData\Local\MySensitiveApp`.
3. **Execution**:
   - In `core/cleaner.py`: `os.path.islink(abs_path)` checks for symlinks, but Windows directory junctions created via `mklink /J` might not be flagged by standard Python `os.path.islink` on older Python runtimes without `follow_symlinks=False` handling.
   - If `os.path.isdir` is entered, `os.walk(followlinks=False)` protects against traversal, but `shutil.rmtree` could remove files if reparse point checks fail.

### Scenario 3: Untrusted File Name XSS in WebView
1. **Pre-condition**: StorageRelief scans a directory containing a file named:
   `<img src=x onerror="alert(document.domain)">.zip`
2. **Attack Vector**:
   - `scanner.py` captures `entry.name`.
   - Data is serialized and sent to frontend.
   - Frontend calls `escapeHtml(item.name)` which replaces `<`, `>`, `"`, `'`, `&`.
3. **Execution & Mitigation Assessment**:
   - Existing mitigation: `escapeHtml` prevents execution in `item-title`.
   - Residual Risk: If any dynamic field (`item.size_formatted`, `item.category`, or future attributes) bypasses `escapeHtml`, stored XSS in WebView2 context could occur, escalating to native IPC command execution.

---

## 8. Risk Assessment Matrix

| Threat ID | Threat Name | Likelihood | Impact | Inherent Risk | Mitigations Present | Residual Risk |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **T-02** | Arbitrary Path Deletion via IPC | Low | Critical | **HIGH** | Blacklist firewall (`cleaner.py`) | **HIGH** |
| **T-08** | False Positive Reclaimed Space | Medium | Medium | **MEDIUM** | Partial file deletion fallback | **MEDIUM** |
| **T-06** | Outbound External Font CDN Calls | High | Low | **MEDIUM** | None | **MEDIUM** |
| **T-03** | Symlink / Junction Traversal | Low | Critical | **HIGH** | `is_reparse_point`, `followlinks=False` | **LOW** |
| **T-01** | IPC Bridge Tampering / Spoofing | Low | High | **MEDIUM** | Edge WebView2 isolation | **MEDIUM** |
| **T-05** | Local Path Disclosure in Logs | Medium | Low | **LOW** | `sys.stderr` only | **LOW** |
| **T-07** | Directory Traversal DoS | Low | Medium | **LOW** | `max_depth` recursion guards | **LOW** |
| **T-09** | Explorer Subprocess Execution | Low | Medium | **LOW** | Array arguments, `os.path.exists` check | **LOW** |
| **T-10** | Unsigned Binaries / SmartScreen | High | Medium | **MEDIUM** | Inno Setup packaging | **MEDIUM** |

---

## 9. Existing Security Mitigations

1. **Deletion Firewall (`core/cleaner.py`)**:
   - `FORBIDDEN_CRITICAL_FILES`: Hardcoded blacklist of 22 mission-critical file names (passwords, browser databases, SSH keys, kernel files).
   - `FORBIDDEN_BROWSER_PROFILE_FILES`: Protects `Local State`, `Bookmarks`, `Preferences` in real browser profile paths.
   - `FORBIDDEN_DIR_NAMES`: Protects `sessions`, `session storage`, `.ssh`, `token_service`.
   - `critical_roots`: Prevents deletion of drive roots (`C:\`), `System32`, `Program Files`, user profile roots (`Desktop`, `Documents`, `Downloads`).
2. **Reparse Point & Symlink Guards**:
   - `is_reparse_point()` in `core/scanner.py` and `core/duplicates.py` queries `kernel32.GetFileAttributesW` for `FILE_ATTRIBUTE_REPARSE_POINT` (0x0400) to avoid junction loops.
   - `followlinks=False` enforced across `os.walk` in `cleaner.py`.
   - `safe_delete_path` handles `os.path.islink` by unlinking the link without traversing into the target.
3. **TOCTOU Pre-Deletion Duplicate Verification**:
   - `verify_duplicate_integrity_before_delete` verifies that target duplicate still exists, size matches scan time, and at least one surviving sibling exists on disk before deletion.
4. **Front-End Sanitization**:
   - `escapeHtml()` utility escapes `&`, `<`, `>`, `"`, `'` before interpolating dynamic file paths and names into DOM template literals.
5. **No Telemetry / No Phone-Home Backend**:
   - The Python backend contains zero analytics, tracking, telemetry, or remote API network calls.

---

## 10. Missing Security Controls & Gaps

1. **Lack of Server-Side Path Whitelisting in IPC Deletion**:
   - `clean_selected_items` should only accept items referenced by server-generated scan session IDs or validate that paths exist in the active scan results set, rather than accepting arbitrary user/client-provided path strings.
2. **Sub-Item Firewall Check Missing in Cleanup Fallback**:
   - In `core/cleaner.py` lines 296-310, when `shutil.rmtree` raises an exception, the fallback loop iterates through `os.scandir(abs_path)` and removes child items without evaluating `is_path_protected_by_firewall(entry.path)`.
3. **Missing Content Security Policy (CSP)**:
   - `ui/web/index.html` has no `<meta http-equiv="Content-Security-Policy">` directive, leaving WebView2 open to unrestricted inline scripts and external resource loading.
4. **External Dependency on Google Fonts CDN**:
   - `index.html` links to `fonts.googleapis.com` and `fonts.gstatic.com`. Fonts should be bundled locally in `ui/web/assets/` to ensure 100% offline operation and privacy preservation.
5. **Lack of Authenticode Code Signing**:
   - Binaries (`StorageRelief.exe` and `StorageRelief_Setup.exe`) are unsigned, triggering Windows SmartScreen warnings and presenting vulnerability to tampering.
6. **Unpinned Dependency Ranges in `requirements.txt`**:
   - Dependencies use open-ended `>=` constraints without hash verification, introducing supply-chain build drift risks.
