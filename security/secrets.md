# Secrets & Credential Management: StorageRelief

## 1. Executive Summary

A comprehensive, project-wide audit of the StorageRelief codebase was conducted to identify any presence, handling, or exposure of credentials, API keys, tokens, private keys, database connections, and secrets.

Because StorageRelief is designed as an offline native Windows desktop utility without a cloud backend, SaaS telemetry, or remote server authentication, the codebase contains **zero hardcoded API keys, tokens, or private secrets**. However, critical considerations exist regarding local file credentials handled by the filesystem scanner, code signing secrets in the CI/CD pipeline, and directory path exposure in diagnostic logs.

---

## 2. Where Secrets are Expected vs. Project Reality

| Category | Typical Expected Usage in Desktop Software | Actual StorageRelief Implementation | Status / Risk |
| :--- | :--- | :--- | :--- |
| **Cloud API Keys / Tokens** | Telemetry, analytics, cloud storage sync, update checking. | **None.** No outbound cloud services or analytics exist. | Safe (Zero Attack Surface) |
| **Database Credentials** | Local or remote DB connection strings (`user`, `password`, `host`). | **None.** Operates on in-memory data structures and direct Win32 filesystem calls. | Safe |
| **OAuth / Session Tokens** | User authentication, cloud account linking. | **None.** No user accounts or login systems exist. | Safe |
| **Code Signing Certificates** | Authenticode signing of `.exe` and setup installer binaries. | **Missing.** Binaries are built unsigned without a PFX certificate or private key. | Weakness (Authenticode Gap) |
| **CI/CD Deployment Secrets** | GitHub Personal Access Tokens (PAT) for release publishing. | Utilizes ephemeral `GITHUB_TOKEN` via `permissions: contents: write`. | Safe (Standard GitHub Action Practice) |
| **Local File System Secrets** | SSH private keys (`id_rsa`), AWS credentials, browser passwords on user disk. | Protected via hardcoded blacklists in `core/cleaner.py`. | Defended (Firewall Enforced) |

---

## 3. Environment & Configuration Handling

### 3.1 Environment Variable Audit
StorageRelief retrieves environment variables exclusively to resolve canonical Windows directory paths. The variables accessed in the project are:

1. `USERPROFILE`: Resolves user directories (`Downloads`, `Desktop`, `Videos`, `AppData`). (e.g., `core/scanner.py:278`, `core/duplicates.py:351`, `core/cleaner.py:85`).
2. `SystemDrive`: Identifies the system drive letter (typically `C:`). (e.g., `core/scanner.py:109`).
3. `SystemRoot`: Resolves Windows OS directory (typically `C:\Windows`). (e.g., `core/scanner.py:800`, `core/cleaner.py:159`).
4. `ProgramFiles` & `ProgramFiles(x86)`: Resolves application installations. (e.g., `core/scanner.py:595`, `core/cleaner.py:160-161`).
5. `ProgramData`: Resolves shared system application data (typically `C:\ProgramData`). (e.g., `core/scanner.py:596`, `core/cleaner.py:162`).
6. `TEMP` & `TMP`: Resolves user and system scratch directories. (e.g., `core/cleaner.py:87-88`, `core/cleaner.py:117`, `core/cleaner.py:138`).

### 3.2 Configuration Files
* No `.env`, `config.ini`, `settings.json`, or `.secrets` files are loaded or required by the runtime.
* The application is self-contained and derives all operational parameters from system Win32 API calls (`GetDiskFreeSpaceExW`, `GetVolumeInformationW`).

---

## 4. Hardcoded-Secret Risks & Source Code Audit

A full regex search was performed across all project files (`.py`, `.js`, `.html`, `.css`, `.bat`, `.ps1`, `.iss`, `.yml`, `.spec`, `.md`) for high-entropy strings, hex private keys, PEM headers, and standard secret patterns (AWS, GitHub, Slack, Google API keys).

### Findings:
* **0 Hardcoded API Keys or Access Tokens Detected.**
* **0 Private Cryptographic Keys Detected.**
* **Public GUIDs and Identifiers (Non-Secret):**
  * `installer.iss:10`: `AppId={{E82956A1-94BC-4C55-9B21-03D953E2A89F}` — This is a public Windows Inno Setup application identifier used for Registry uninstallation key mapping. It is public and non-sensitive.
  * `main.py:181`: `app_id = "com.storagerelief.python.webview.optimizer"` — Public Windows AppUserModelID used by `shell32.dll` for taskbar icon grouping.
  * `main_qt.py:22`: `app_id = "com.storagerelief.python.optimizer"` — Public AppUserModelID for Qt runtime.

### Defensive Blacklist Patterns (Non-Secret Security Rules):
In `core/cleaner.py:27-76`, the following string literals represent **defensive blacklist targets**, not credentials belonging to the application:
```python
FORBIDDEN_CRITICAL_FILES = frozenset({
    "login data", "cookies", "web data", "history", "current session",
    "key4.db", "logins.json", "id_rsa", "id_ed25519", "bootmgr", ...
})
```
These signatures prevent the application from deleting user credentials on disk.

---

## 5. Client-Side & In-Memory Exposure Risks

### 5.1 Front-End In-Memory State (`ui/web/main.js`)
* `state.items`: Contains file objects with absolute paths, file sizes, and descriptions returned by the scanner.
* `state.duplicateFilesMap`: Contains paths, file sizes, modification timestamps, and SHA-256 hashes of duplicate candidates.
* **Risk Evaluation**: If a user's directory paths contain confidential project names, client names, or personal usernames (e.g., `C:\Users\JohnDoe\OneDrive\Desktop\Projects\ClientAcquisition\`), these paths reside in the WebView DOM JavaScript memory space.
* **Mitigation Present**:
  * Edge WebView2 DevTools are disabled in production via `debug=False` (`main.py:212`).
  * The frontend operates locally within the desktop process without external transmission.

### 5.2 External Resource Requests (Google Fonts)
* `ui/web/index.html` lines 7-12 load fonts from:
  * `https://fonts.googleapis.com`
  * `https://fonts.gstatic.com`
* **Risk Evaluation**: While no application secrets are transmitted, making outbound requests to a third-party CDN leaks the user's IP address and client timestamp to Google upon application launch.

---

## 6. Git & Version Control History Exposure Risks

### 6.1 Git Commit Log Inspection
* Historical inspection of the repository (`git log`) confirms no commits containing `.env`, API keys, certificates, or credentials.
* Clean repository state: Working directory is clean with zero uncommitted or tracked secret files.

### 6.2 `.gitignore` Evaluation (`.gitignore:1-29`)
The project `.gitignore` contains rules for:
* Python bytecode (`__pycache__/`, `*.py[cod]`)
* Distribution builds (`build/`, `dist/`, `StorageRelief.exe`, `StorageRelief_Setup.exe`, `*.spec`)
* Virtual environments (`.venv/`, `env/`, `venv/`)
* Temporary files and logs (`*.log`, `*.tmp`, `storage_relief.log`)
* IDE settings (`.vscode/`, `.idea/`)

### Identified Gap:
* **Missing Secret Exclusion Rules**: The `.gitignore` does **not** explicitly list common secret formats:
  * `.env`, `.env.*`
  * `*.pem`, `*.key`, `*.pfx`, `*.p12` (Code signing certificate files)
  * `secrets/`, `credentials.json`
* If a developer generates an Authenticode code-signing certificate (e.g., `cert.pfx`) or local environment file, Git will not ignore it by default, creating an accidental commit risk.

---

## 7. Logging & Error Output Exposure Risks

### 7.1 Backend Diagnostic Output (`main.py`)
All error handlers in `main.py` print exception messages to `sys.stderr`:
* Line 42: `print(f"[StorageRelief Backend Error] get_available_drives: {e}", file=sys.stderr)`
* Line 57: `print(f"[StorageRelief Backend Notice] get_drive_info on {target_letter} ({e}), falling back to C:\\", file=sys.stderr)`
* Line 87: `print(f"[StorageRelief Backend Error] scan_storage: {e}", file=sys.stderr)`
* Line 105: `print(f"[StorageRelief Backend Error] clean_selected_items: {e}", file=sys.stderr)`
* Line 114: `print(f"[StorageRelief Backend Error] open_item_path: {e}", file=sys.stderr)`
* Line 159: `print(f"[StorageRelief Backend Error] scan_duplicates: {e}", file=sys.stderr)`

### 7.2 Frontend Console Output (`ui/web/main.js`)
* Line 26: `console.error('[Python API Error] ${cmd}:', e)`
* Line 1132: `console.error('Clean operation encountered an issue:', err)`

### Risk Assessment:
When a file access exception occurs (e.g. `PermissionError`), the exception message includes the full absolute filesystem path (e.g. `[WinError 5] Access is denied: 'C:\\Users\\<Username>\\...'`). If the executable is run from a shell or wrapped in a launcher that captures stderr, sensitive file paths and user identity details are exposed in the execution logs.

---

## 8. Secret Rotation Requirements

| Secret Asset | Rotation Frequency Requirement | Rotation Procedure & Storage |
| :--- | :--- | :--- |
| **Authenticode Code Signing Certificate** (When implemented) | Every 1–3 years (upon certificate expiration). | Store PFX password and base64 certificate in GitHub Actions encrypted secrets (`CERT_BASE64`, `CERT_PASSWORD`). Rotate prior to certificate expiry. |
| **GitHub Actions Token** (`GITHUB_TOKEN`) | Ephemeral (Rotated automatically per CI run by GitHub). | Managed natively by GitHub Actions runner (`permissions: contents: write`). |
| **Third-Party API Tokens** | N/A (None used in project). | N/A |

---

## 9. Summary of Actual Findings with Evidence

### Finding SEC-01: Zero Hardcoded Application Secrets
* **Classification**: Positive Security Finding (Compliant)
* **Evidence**: Full codebase text search yields 0 private keys, 0 API credentials, 0 hardcoded passwords.
* **Why it matters**: Application poses zero risk of leaked cloud credentials or compromised third-party service accounts.

### Finding SEC-02: Missing Code Signing Certificate Pipeline
* **Classification**: Security Weakness / Infrastructure Gap
* **Evidence**: `build.ps1` and `.github/workflows/build-release.yml` compile binaries without an Authenticode signing step.
* **Risk**: Binaries distributed to users trigger Windows SmartScreen warnings ("Unknown Publisher") and can be tampered with or replaced without signature invalidation.
* **Recommended Fix**: Procure a code-signing certificate (or use a corporate DigiCert/Sectigo HSM), store certificate material in GitHub repository secrets, and integrate `signtool.exe` into `build.ps1` and `build-release.yml`.

### Finding SEC-03: Incomplete `.gitignore` Secret Exclusions
* **Classification**: Missing Control
* **Evidence**: `.gitignore` lines 1–29 omit `.env`, `*.pfx`, `*.p12`, `*.pem`, `*.key`.
* **Risk**: High risk of accidental commit if local code signing or development environment files are added.
* **Recommended Fix**: Add standard certificate and environment exclusions (`*.pfx`, `*.p12`, `*.pem`, `*.key`, `.env*`) to `.gitignore`.

### Finding SEC-04: User Directory Path Emission in Exception Messages
* **Classification**: Information Disclosure Risk (Low)
* **Evidence**: `main.py` lines 42, 57, 87, 105, 114, 159 print raw exception objects containing absolute filesystem paths to `sys.stderr`.
* **Risk**: Local system layout and user account names are logged in command-line outputs during execution failures.
* **Recommended Fix**: Sanitize exception logging to omit user profile directory prefixes or wrap errors in generic user-friendly messages while retaining raw logs only in controlled diagnostic modes.
