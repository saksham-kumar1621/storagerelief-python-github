# Security Checklist: StorageRelief Windows Storage Optimizer

## 1. Scope & Methodology

This checklist evaluates the complete codebase, architecture, frontend, backend IPC, file system operations, dependencies, deployment configuration, and data flows of the **StorageRelief** desktop application.

Every finding is evaluated against actual code evidence and categorized into:
- **Confirmed Vulnerability**: A verifiable flaw that directly undermines a security boundary.
- **Security Weakness**: An architectural, design, or implementation gap that increases the risk of compromise.
- **Missing Control**: A defense-in-depth mechanism that is standard for this architecture but absent.
- **Potential Risk Requiring Verification**: An operational assumption that could manifest under edge-case runtime conditions.
- **Recommendation**: Proactive defensive enhancement to harden the application posture.

---

## 2. Comprehensive Domain Audit Checklist

### 2.1 Authentication
- [x] **Local Standalone Architecture**: No user login or credentials required.
- [ ] **IPC Caller Authentication**: No verification of caller identity between WebView2 and Python host.
- [x] **Zero Hardcoded Application Credentials**: Verified 0 hardcoded keys or passwords in repository.

### 2.2 Authorization & RBAC
- [x] **Operating System Privilege Model**: Runs under current Windows user context.
- [x] **Least Privilege Installer**: `installer.iss:24` sets `PrivilegesRequired=lowest`.
- [ ] **IPC Method Authorization**: Any script executing in WebView can call all 8 backend API methods.

### 2.3 Session & Token Security
- [x] **Stateless IPC Design**: No persistent session tokens to steal or forge.
- [ ] **Lack of Scan Session Validation**: API methods accept direct raw paths rather than referencing active scan session IDs.

### 2.4 Input Validation
- [x] **Drive Identifier Normalization**: `core/scanner.py:193-200` validates and normalizes drive letters.
- [x] **Path Normalization**: Uses `os.path.normpath` and `os.path.abspath`.
- [ ] **Target Path Whitelisting**: `clean_selected_items` does not validate paths against the active scan item set.

### 2.5 Injection (Command & Path)
- [x] **Parameterized Subprocess Calls**: `cleaner.py:358-360` uses array arguments `["explorer.exe", ...]` without `shell=True`.
- [x] **Drive Parameter Win32 Validation**: Drive letters checked against `ctypes` Win32 API boundaries.
- [ ] **Explorer Subprocess Target Validation**: `open_in_file_explorer` does not restrict target paths to scanned items.

### 2.6 Cross-Site Scripting (XSS) & CSRF
- [x] **HTML Entity Sanitization**: `ui/web/main.js:1173-1181` (`escapeHtml`) encodes `&`, `<`, `>`, `"`, `'`.
- [x] **Zero CSRF Exposure**: No web server or remote HTTP endpoints exist.
- [ ] **Missing Content Security Policy (CSP)**: `ui/web/index.html` lacks `<meta http-equiv="Content-Security-Policy">`.

### 2.7 API Security
- [x] **Type Coercion Safeguards**: Handlers in `main.py` handle both `dict` and `list`/`str` parameter shapes.
- [x] **Exception Containment**: Bridge functions wrap logic in `try-except` blocks.
- [ ] **Unbounded Deletion Capability**: Python API permits deletion of any non-blacklisted file system path.

### 2.8 Rate Limiting & Abuse Prevention
- [x] **Single-User Desktop Model**: Remote network request flooding is non-applicable.
- [x] **Directory Traversal Depth Bounds**: `max_depth=4` in `get_dir_size_safe`, `depth > 15` in duplicate scanner.

### 2.9 File Uploads & Local Intake
- [x] **Zero Remote Upload Endpoints**: No file upload facilities exist.
- [x] **Chunked File Hashing**: Duplicate detection streams file bytes in 64 KB chunks (`core/duplicates.py:169`) to avoid memory exhaustion.

### 2.10 Database Security
- [x] **Database-Free Architecture**: No SQL or NoSQL database used.
- [x] **Zero SQL Injection Risk**: No database engines or query builders present.

### 2.11 Secrets Management
- [x] **Zero Embedded API Keys**: No secrets found across codebase.
- [x] **Defensive Signature Blacklist**: `core/cleaner.py` protects browser credentials (`login data`, `cookies`, `key4.db`) and SSH keys.
- [ ] **Incomplete `.gitignore`**: Secret file formats (`*.pfx`, `*.pem`, `.env`) are omitted from `.gitignore`.

### 2.12 Encryption & Cryptographic Integrity
- [x] **Secure Hashing**: Duplicate detection uses SHA-256 for full file verification (`hashlib.sha256()`).
- [x] **Safe Optimization**: Head/tail MD5 used only as an intermediate filter before SHA-256 validation.

### 2.13 Cross-Origin Resource Sharing (CORS)
- [x] **Non-Applicable**: No HTTP server or REST endpoints deployed.

### 2.14 Dependency Security & Supply Chain
- [x] **Minimal Dependency Tree**: Only 5 direct dependencies in `requirements.txt`.
- [ ] **Unpinned Package Versions**: Uses `>=` without fixed version pins or SHA-256 hash checking.
- [ ] **Automated Vulnerability Scanning**: No automated dependency vulnerability scanner (e.g. `pip-audit`, Dependabot) in CI.

### 2.15 Logging & Monitoring
- [x] **Zero Remote Telemetry**: Operates strictly local.
- [ ] **File Path Emission in Stderr**: Full absolute file paths and usernames emitted during exception logging.

### 2.16 Admin Security & Privilege Escalation
- [x] **Default Non-Elevated Execution**: Manifest does not force administrative UAC elevation.
- [x] **Critical Windows Root Protection**: `core/cleaner.py:159-185` blocks deletion of `System32`, `Windows`, `Program Files`.

### 2.17 Deployment & Infrastructure
- [x] **Automated CI Workflow**: `.github/workflows/build-release.yml` automates builds and testing.
- [ ] **Missing Code Signing (Authenticode)**: Binaries and installer are built without digital signatures.
- [ ] **Incorrect Script Path in CI**: Workflow line 42 references non-existent `.\scripts\build.ps1`.

### 2.18 Data Privacy & Anti-Fingerprinting
- [ ] **External CDN Font Requests**: `ui/web/index.html` loads fonts from Google CDN, conflicting with offline privacy policy.

### 2.19 Error Handling & Fault Tolerance
- [x] **Non-Blocking File Traversal**: `scanner.py` tolerates `PermissionError` and `OSError` without crashing.
- [ ] **Misleading Deletion Reporting**: `cleaner.py:314` returns success when folder deletion is only partial.

### 2.20 Backup, Recovery & Data Safety
- [x] **TOCTOU Duplicate Verification**: `verify_duplicate_integrity_before_delete` prevents deleting unique copies.
- [x] **Reparse Point Guard**: Does not recurse through NTFS junctions or symlinks.
- [ ] **No Recycle Bin Staging**: Deletions use permanent unlinking (`os.remove`, `shutil.rmtree`) rather than Windows Recycle Bin (`SHFileOperationW`).

---

## 3. Important Findings: Detailed Breakdown

### 3.1 Confirmed Vulnerabilities

#### Finding VULN-01: Arbitrary File Deletion Acceptance in IPC API Bridge
* **Severity**: **High**
* **Evidence**:
  * Location: `main.py:90-106` and `core/cleaner.py:325-348`
  * Code:
    ```python
    # main.py
    def clean_selected_items(self, paths: Union[List[str], Dict[str, Any]] = None) -> Dict[str, Any]:
        target_paths = paths if isinstance(paths, list) else paths.get("paths", [])
        deleted, errors = clean_selected_paths(target_paths)
        return {"deleted": deleted, "errors": errors}
    ```
* **Risk**: The backend deletion API receives string paths directly from the JavaScript client without validating that the paths were originally discovered during an authorized scan. While `is_path_protected_by_firewall` enforces a blacklist of sensitive system roots and credential filenames, **any arbitrary non-blacklisted file on the system (e.g. personal documents in user folders) will be permanently deleted** if supplied in the IPC request.
* **Affected location**: `main.py:90-106`, `core/cleaner.py:325-348`
* **Why it matters**: A desktop storage optimizer must ensure that deletion targets originate exclusively from legitimate scanner output, rather than trusting unverified client-side inputs.
* **Recommended fix**: Maintain an in-memory session cache of scanned items on the Python backend. Have the client pass only item IDs (e.g. `["item_1", "item_4"]`). Resolve paths strictly on the backend against the active scan cache.

---

### 3.2 Security Weaknesses

#### Finding WEAK-01: Pre-Audit Bypass in Directory Deletion Fallback Routine
* **Severity**: **Medium**
* **Evidence**:
  * Location: `core/cleaner.py:289-311`
  * Code:
    ```python
    try:
        shutil.rmtree(abs_path, onerror=_handle_remove_readonly)
        return True, ""
    except Exception as rmtree_err:
        for entry in os.scandir(abs_path):
            if entry.is_file() or entry.is_symlink():
                os.remove(entry.path)
            elif entry.is_dir():
                shutil.rmtree(entry.path, onerror=_handle_remove_readonly)
    ```
* **Risk**: When `shutil.rmtree` fails, the exception fallback routine iterates over child entries using `os.scandir` and executes `os.remove()` and `shutil.rmtree()` **without re-evaluating `is_path_protected_by_firewall(entry.path)`**. If a sensitive file was locked or created concurrently, the fallback bypasses the firewall inspection performed during the pre-audit walk.
* **Affected location**: `core/cleaner.py:296-310`
* **Why it matters**: Security boundaries must be consistently applied across primary and fallback code paths.
* **Recommended fix**: Explicitly call `is_path_protected_by_firewall(entry.path)` on each child item inside the fallback loop before calling `os.remove` or recursive `shutil.rmtree`.

#### Finding WEAK-02: False Positive Success Reporting on Incomplete Directory Removal
* **Severity**: **Medium**
* **Evidence**:
  * Location: `core/cleaner.py:314`
  * Code:
    ```python
    if not os.path.lexists(abs_path) or partial_deleted > 0:
        return True, ""
    ```
* **Risk**: If a directory contains 100 locked files and 1 unlocked file, `partial_deleted` becomes 1. The function returns `(True, "")`. The frontend treats the directory as successfully deleted, marks it as cleaned, and credits the full multi-gigabyte capacity in the celebration statistics, misleading the user about actual disk state.
* **Affected location**: `core/cleaner.py:313-317`
* **Why it matters**: Cleaners must provide accurate accounting; reporting locked directories as deleted obscures persistent storage issues.
* **Recommended fix**: Return `(False, "Directory in use: some files could not be removed")` whenever `os.path.lexists(abs_path)` remains true after deletion attempts.

#### Finding WEAK-03: External CDN Font Loading Violating Offline Policy
* **Severity**: **Low**
* **Evidence**:
  * Location: `ui/web/index.html:7-12`
  * Code:
    ```html
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
    ```
* **Risk**: The application initiates outbound HTTPS connections to Google servers on launch, transmitting the user's IP address and client timestamp. This directly contradicts `SECURITY.md:11` ("No Telemetry / No Phone-Home: StorageRelief operates 100% offline"). It also causes broken typography or startup latency when the host is disconnected from the internet.
* **Affected location**: `ui/web/index.html:7-12`
* **Why it matters**: Preserving user privacy claims and offline self-containment.
* **Recommended fix**: Bundle font files (`.woff2`) locally in `ui/web/assets/fonts/` and reference them via local `@font-face` definitions in `styles.css`.

---

### 3.3 Missing Controls

#### Finding CTRL-01: Missing Content Security Policy (CSP) in Frontend
* **Severity**: **Medium**
* **Evidence**:
  * Location: `ui/web/index.html:1-17`
  * Observation: No `<meta http-equiv="Content-Security-Policy">` header is defined.
* **Risk**: If an attacker manages to introduce HTML or script content via crafted file names or paths, Edge WebView2 will execute it without CSP restrictions on inline scripts or external network connections.
* **Affected location**: `ui/web/index.html:1-17`
* **Why it matters**: A strict CSP is a critical defense-in-depth measure in desktop webview applications to prevent DOM-to-native privilege escalation.
* **Recommended fix**: Add a strict CSP meta tag restricting scripts to `'self'`, styles to `'self' 'unsafe-inline'`, and disallowing external network connections.

#### Finding CTRL-02: Missing Authenticode Code Signing Certificate Pipeline
* **Severity**: **Medium**
* **Evidence**:
  * Location: `build.ps1:18-42`, `installer.iss:9-26`, `.github/workflows/build-release.yml:41-51`
  * Observation: Binaries are compiled and packaged without digital signatures.
* **Risk**: Windows SmartScreen blocks application execution on new computers with untrusted publisher alerts; users cannot verify binary integrity or authenticity.
* **Affected location**: Build scripts and GitHub Actions workflow
* **Why it matters**: Standard distribution requirement for native Windows software.
* **Recommended fix**: Integrate an Authenticode code-signing step using `signtool.exe` with a valid certificate stored in GitHub Actions secrets.

#### Finding CTRL-03: Incomplete `.gitignore` Secret Exclusions
* **Severity**: **Low**
* **Evidence**:
  * Location: `.gitignore:1-29`
  * Observation: Ignores build artifacts and logs, but does not list `.env`, `*.pfx`, `*.pem`, `*.key`.
* **Risk**: High risk of accidental commit if developers introduce local certificates or environment configuration files.
* **Affected location**: `.gitignore:1-29`
* **Why it matters**: Prevents accidental leakage of cryptographic keys and configuration secrets.
* **Recommended fix**: Add standard certificate and environment exclusions (`.env*`, `*.pfx`, `*.p12`, `*.pem`, `*.key`) to `.gitignore`.

#### Finding CTRL-04: Permanent Deletion Without Recycle Bin Safety Net
* **Severity**: **Low**
* **Evidence**:
  * Location: `core/cleaner.py:235-260`
  * Code uses `os.remove()` and `shutil.rmtree()`, permanently unlinking files from disk.
* **Risk**: If a user accidentally selects an important personal video or archive (e.g. from the Heavy Media category), the file is permanently unrecoverable without specialized data recovery tools.
* **Affected location**: `core/cleaner.py:235-290`
* **Why it matters**: Windows desktop utilities typically support moving files to the Recycle Bin (`$Recycle.Bin`) via Win32 `SHFileOperationW` or `IFileOperation` as a safety net.
* **Recommended fix**: Provide an optional or default "Move to Recycle Bin" mode using `shell32.SHFileOperationW` (flag `FOF_ALLOWUNDO`) for non-cache user files.

---

### 3.4 Potential Risks Requiring Verification

#### Finding RISK-01: CI/CD Build Script Path Discrepancy
* **Severity**: **Low**
* **Evidence**:
  * Location: `.github/workflows/build-release.yml:42`
  * Code: `run: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build.ps1`
  * Reality: The repository contains `build.ps1` at the root, not inside a `scripts` folder.
* **Risk**: Automated release builds triggered by git tags will fail in GitHub Actions with "file not found".
* **Affected location**: `.github/workflows/build-release.yml:42`
* **Why it matters**: Impedes release engineering and CI pipeline automation.
* **Recommended fix**: Change path to `.\build.ps1`.

#### Finding RISK-02: Unpinned Dependency Constraints
* **Severity**: **Low**
* **Evidence**:
  * Location: `requirements.txt:1-5`
  * Packages specified with `>=` constraints: `pywebview>=5.0.0`, `psutil>=5.9.0`, etc.
* **Risk**: Builds are subject to non-deterministic upstream updates and supply-chain drift.
* **Affected location**: `requirements.txt`
* **Why it matters**: Software integrity requires reproducible and verifiable dependency resolution.
* **Recommended fix**: Pin dependencies to exact versions (`==`) and implement hash verification.

---

## 4. Recommendations Summary Table

| Category | Finding ID | Severity | Action Item |
| :--- | :--- | :--- | :--- |
| **API Security** | VULN-01 | **High** | Implement server-side path whitelisting in `clean_selected_items` using scan session IDs. |
| **Cleaner Engine** | WEAK-01 | **Medium** | Re-evaluate `is_path_protected_by_firewall()` inside `cleaner.py` exception fallback loop. |
| **Integrity & UX** | WEAK-02 | **Medium** | Prevent returning success when target folder still exists after partial deletion. |
| **Content Security**| CTRL-01 | **Medium** | Add strict `<meta http-equiv="Content-Security-Policy">` to `index.html`. |
| **Code Signing** | CTRL-02 | **Medium** | Integrate Authenticode signing with `signtool.exe` into `build.ps1` and CI. |
| **Data Privacy** | WEAK-03 | **Low** | Download Google Fonts into `ui/web/assets/fonts/` for true 100% offline execution. |
| **Version Control** | CTRL-03 | **Low** | Add `*.pfx`, `*.pem`, `*.key`, `.env*` to `.gitignore`. |
| **Data Safety** | CTRL-04 | **Low** | Introduce optional Recycle Bin deletion mode via Win32 `SHFileOperationW`. |
| **CI/CD Pipeline** | RISK-01 | **Low** | Correct `build-release.yml` script path from `.\scripts\build.ps1` to `.\build.ps1`. |
| **Supply Chain** | RISK-02 | **Low** | Pin dependencies with hashes in `requirements.txt`. |
