# Attack Surface Analysis: StorageRelief

## 1. Executive Summary

StorageRelief is a standalone desktop application for Windows. It does not operate as a networked client-server service or SaaS web application, which significantly limits its exposure to remote network threats. However, its hybrid desktop architecture (integrating Microsoft Edge WebView2 with a high-privilege native Python backend and direct NTFS disk interaction) introduces unique local and inter-process attack surfaces.

This document inventories all external and internal interfaces, inputs, storage channels, and execution pathways that can be influenced or targeted by users, local processes, or malicious files.

---

## 2. Public Network Endpoints

| Endpoint | Protocol / Port | Direction | Description & Exposure |
| :--- | :--- | :--- | :--- |
| **None** | N/A | Inbound | StorageRelief **binds zero network ports** on localhost or public interfaces. There are no listening HTTP, HTTPS, TCP, UDP, or WebSocket servers. |
| `https://fonts.googleapis.com` | HTTPS / 443 | Outbound | Client CSS stylesheet request for Google Fonts (`ui/web/index.html:9-12`). |
| `https://fonts.gstatic.com` | HTTPS / 443 | Outbound | Font binary resource requests (`.woff2`) for Google Fonts (`ui/web/index.html:8`). |

### Attack Surface Assessment:
* **Inbound Network Surface**: **Zero.** Remote network exploitation over sockets is impossible because no listeners exist.
* **Outbound Network Surface**: Limited strictly to Google Fonts CDN. If TLS traffic is intercepted on untrusted networks, modified CSS could theoretically be served, but no application logic is driven by external network responses.

---

## 3. Internal Endpoints: PyWebView IPC Bridge Interface

The primary application boundary exists between the Microsoft Edge WebView2 rendering context (JavaScript) and the native Python runtime (`main.py`). The `StorageReliefAPI` class registers 8 RPC endpoints accessible via `window.pywebview.api`:

```
+-----------------------------------------------------------------------------------------+
|                                EDGE WEBVIEW2 JAVASCRIPT DOM                             |
|                               (window.pywebview.api.<method>)                           |
+-----------------------------------------------------------------------------------------+
       |                  |                |                  |                 |
       | get_available_   | get_drive_     | scan_storage()   | clean_selected_ | open_item_
       | drives()         | info()         |                  | items()         | path()
       v                  v                v                  v                 v
+-----------------------------------------------------------------------------------------+
|                               PYTHON BACKEND (StorageReliefAPI)                         |
|                                       (main.py)                                         |
+-----------------------------------------------------------------------------------------+
       |                  |                |                  |
       v                  v                v                  v
  [ Win32 Drive API ]  [ Win32 Stats ]  [ Scanner Engine ] [ Cleaner Engine ] [ Explorer.exe ]
```

### Detailed Endpoint Analysis:

#### 1. `clean_selected_items(paths)`
* **Location**: `main.py:90-106`
* **Input Parameters**: `paths`: `Union[List[str], Dict[str, Any]]`
* **Backend Processing**: Unpacks paths and passes them directly to `core/cleaner.py:clean_selected_paths(target_paths)`.
* **Attack Surface & Risk**: **CRITICAL**. This endpoint performs permanent file deletions. While `cleaner.py` evaluates `is_path_protected_by_firewall()`, any non-blacklisted file on the system (e.g. personal documents in non-protected folders) will be permanently deleted if supplied in the payload. The endpoint lacks session state validation or server-side whitelisting against scanned items.

#### 2. `open_item_path(path)`
* **Location**: `main.py:108-116`
* **Input Parameters**: `path`: `Union[str, Dict[str, Any]]`
* **Backend Processing**: Normalizes path, checks `os.path.exists()`, and executes:
  `subprocess.Popen(["explorer.exe", f"/select,{norm_path}"])` (for files) or
  `subprocess.Popen(["explorer.exe", norm_path])` (for directories).
* **Attack Surface & Risk**: **MEDIUM**. Spawns a new Windows Explorer process. If special characters or directory junction paths are supplied, unintended Explorer shell windows or file selections could occur.

#### 3. `scan_storage(drive_letter)`
* **Location**: `main.py:64-88`
* **Input Parameters**: `drive_letter`: `Union[str, Dict[str, Any]]` (defaults to `"C:\\"`)
* **Backend Processing**: Validates and normalizes drive letter via `core/scanner.py:get_drive_info()`, then walks local filesystems.
* **Attack Surface & Risk**: **LOW**. Triggers deep directory enumeration across local storage drives. Maliciously nested directory trees could cause temporary CPU/disk I/O denial of service.

#### 4. `get_drive_info(drive_letter)`
* **Location**: `main.py:45-63`
* **Input Parameters**: `drive_letter`: `Union[str, Dict[str, Any]]`
* **Backend Processing**: Calls `kernel32.GetDiskFreeSpaceExW` and `GetVolumeInformationW`.
* **Attack Surface & Risk**: **LOW**. Read-only Win32 API query.

#### 5. `get_available_drives()`
* **Location**: `main.py:36-44`
* **Input Parameters**: None.
* **Backend Processing**: Calls `kernel32.GetLogicalDrives()`.
* **Attack Surface & Risk**: **LOW**. Read-only enumeration of local/removable storage volumes.

#### 6. `get_duplicate_scan_targets(drive_letter)`
* **Location**: `main.py:117-130`
* **Input Parameters**: `drive_letter`: `Union[str, Dict[str, Any]]`
* **Backend Processing**: Returns standard user directories (`Downloads`, `Videos`, `Documents`, `Pictures`, `Desktop`).
* **Attack Surface & Risk**: **LOW**. Read-only directory resolution.

#### 7. `scan_duplicates(options)`
* **Location**: `main.py:131-160`
* **Input Parameters**: `options`: `Dict[str, Any]` containing `target_dirs: List[str]` and `min_size_mb: float`.
* **Backend Processing**: Recursively traverses `target_dirs`, groups files by size, computes MD5 head/tail hashes, and full SHA-256 digests.
* **Attack Surface & Risk**: **MEDIUM**. Reads file contents on disk. Could be targeted with thousands of deeply nested symlinks or corrupted files to trigger high memory or CPU usage.

#### 8. `pick_custom_folder()`
* **Location**: `main.py:162-176`
* **Input Parameters**: None.
* **Backend Processing**: Instantiates `tkinter.Tk()` and displays native `filedialog.askdirectory()`.
* **Attack Surface & Risk**: **LOW**. Native Windows dialog modal.

---

## 4. Authentication & Authorization Surfaces

| Boundary | Mechanism | Current Security Posture |
| :--- | :--- | :--- |
| **UI to IPC Bridge** | None | **Zero Authentication.** Any JavaScript executing within the WebView has unrestricted access to all 8 methods of `window.pywebview.api`. |
| **Application to Operating System** | Windows User Token | Inherits the security context of the launching user. |
| **Role-Based Access Control (RBAC)** | None | Single-user utility model. No roles or user tiers exist. |
| **Administrative Elevation (UAC)** | Standard / Optional Admin | Configured with `PrivilegesRequired=lowest` in `installer.iss:24`. If launched with "Run as Administrator", application has elevated privileges to modify system directories (mitigated only by `cleaner.py` blacklist). |

---

## 5. User Input Surfaces

### 5.1 Graphical User Interface Inputs (`ui/web/`)
1. **Search Query Input (`searchQuery`)**:
   - Location: Search filter in System Cleaner view (`main.js:48`).
   - Handling: Case-insensitive substring comparison against `item.name`, `item.description`, and `item.path`.
   - Injection Risk: Sanitized via `escapeHtml()` during DOM rendering.
2. **Drive Selection Dropdown (`activeDrive`)**:
   - Location: Multi-drive selector (`main.js:41`, `main.js:424-468`).
   - Handling: Drive letter string is parsed in `core/scanner.py:193-200` (forces format `X:\`).
3. **Category Filter Tabs (`activeCategory`)**:
   - Location: Category selection pills (`main.js:47`).
   - Handling: Validated against predefined category identifier set.
4. **Duplicate Target Checkbox Selection (`duplicateTargets`)**:
   - Location: Target library selectors (`main.js:52`).
   - Handling: Filtered through `os.path.isdir()` in `core/duplicates.py:233`.
5. **Duplicate Minimum Size Parameter (`duplicateMinSizeMb`)**:
   - Location: Size threshold input.
   - Handling: Converted to `float` via `float(options.get("min_size_mb", 1.0))` (`main.py:139`).
6. **Checkbox Selections (`selectedIds`, `duplicateSelectedIds`)**:
   - Location: Per-card and per-group checkbox inputs in UI.
   - Handling: Mapped to set lookups in frontend memory.

### 5.2 Filesystem Input Surface (Untrusted Data from Disk)
Because StorageRelief scans disk volumes, the **file system itself functions as an untrusted input source**:
1. **File and Directory Names**:
   - Malicious files created by third parties or malware can have names containing HTML tags, path traversal characters (`..`), Unicode homoglyphs, or null bytes (`\0`).
   - *Mitigation*: Paths are sanitized via `os.path.normpath` and `os.path.abspath`; HTML output is escaped via `escapeHtml()`.
2. **Symbolic Links & Directory Junctions**:
   - Directory loops or junctions created to trick the scanner into traversing outside the target directory.
   - *Mitigation*: Explicitly blocked via `is_reparse_point()` (`FILE_ATTRIBUTE_REPARSE_POINT` check in `scanner.py:56-66` and `duplicates.py:208`) and `followlinks=False` in `os.walk()`.

---

## 6. File Processing & Hashing Surface (File Intake)

StorageRelief does not accept remote file uploads, but it ingests files locally during duplicate detection:
1. **Partial Hashing (`core/duplicates.py:145-162`)**:
   - Opens local files in binary mode: `open(filepath, "rb")`.
   - Reads 4096 bytes from the head, seeks to `size - 4096`, and reads 4096 bytes from the tail.
   - Computes MD5 hash.
   - Exception handling catches `PermissionError`, `FileNotFoundError`, and `OSError`.
2. **Full Cryptographic Hashing (`core/duplicates.py:164-174`)**:
   - Opens local files in binary mode: `open(filepath, "rb")`.
   - Reads in 64 KB chunks (`chunk_size = 65536`) to stream SHA-256 digest computation without loading large files into RAM.
   - Prevents memory exhaustion when processing multi-gigabyte video or archive files.

---

## 7. Storage & Permanent Deletion Surface

The most sensitive operational attack surface is the permanent file and directory deletion engine in `core/cleaner.py`:

```
User Action: "Proceed with Clean"
            |
            v
[ main.js: confirmClean() ]
            |  (Transmits array of path strings)
            v
[ main.py: clean_selected_items(paths) ]
            |
            v
[ core/cleaner.py: clean_selected_paths(paths) ]
            |
            +---> For each path: safe_delete_path(path)
                     |
                     +---> is_path_protected_by_firewall(path)  <--- BLACKLIST VALIDATION
                     |        [Pass] -> Proceed
                     |        [Fail] -> Return Error ("Blocked by Security Assertion")
                     |
                     +---> Symlink / Reparse Point check: os.path.islink(path)
                     |        [Yes]  -> os.unlink / os.rmdir (DO NOT TRAVERSE)
                     |
                     +---> Single File: os.remove(path)
                     |
                     +---> Container Directory (%TEMP%): Delete children only
                     |
                     +---> Standard Directory:
                              +---> Pre-audit walk (ensure no blacklisted child files)
                              +---> Strip read-only attributes
                              +---> shutil.rmtree(path)
                              +---> Fallback: os.scandir child purge
```

### Critical Gaps in Storage Attack Surface:
1. **No Whitelist Validation**: `clean_selected_paths` receives strings directly from the client. It does not check if the paths were generated by `scan_storage`.
2. **Fallback Scan Audit Bypass**: In `cleaner.py:296-310`, if `shutil.rmtree` throws an exception, the fallback loop iterates over child entries and calls `os.remove` and `shutil.rmtree` without re-verifying `is_path_protected_by_firewall`.
3. **Inaccurate Success State**: In `cleaner.py:314`, `partial_deleted > 0` causes the function to report success even if the main directory was not deleted.

---

## 8. Webhooks & Third-Party Integrations

* **Webhooks**: **None.** Zero incoming or outgoing webhook subscriptions.
* **Third-Party Services**:
  * **Google Fonts CDN**: `fonts.googleapis.com` (CSS) and `fonts.gstatic.com` (WOFF2 fonts).
  * **Microsoft Edge WebView2**: Embedded browser runtime provided by Windows.
  * No Google Analytics, Sentry, Mixpanel, Firebase, or external telemetry SDKs exist in the project.

---

## 9. Admin Surfaces & Privilege Boundaries

* **Administrative Interface**: None.
* **Process Privilege Context**:
  * The installer (`installer.iss:24`) configures `PrivilegesRequired=lowest`.
  * The app runs as a standard user process.
  * If the user right-clicks and runs "As Administrator", Windows assigns an elevated administrative token. In this mode, the application has OS permission to delete system-wide files, making reliance on the `core/cleaner.py` firewall critical.

---

## 10. Deployment & Packaging Attack Surface

### 10.1 PyInstaller Bundle Packaging (`build.ps1` & `StorageRelief.spec`)
* StorageRelief is packaged as a single-file executable using PyInstaller (`--onefile --noconsole`).
* At runtime, `--onefile` executables extract bundled Python scripts, shared libraries, and assets to a temporary directory in `%TEMP%\_MEIxxxxxx`.
* **DLL Search Order Hijacking Surface**: If `%TEMP%` has permissive permissions, a local low-privilege attacker could attempt to place malicious DLLs in temporary directories if search paths are not strictly controlled by the OS.

### 10.2 Continuous Integration & Release Pipeline (`.github/workflows/build-release.yml`)
* GitHub Actions workflow triggers on push to `main` and release tags (`v*`).
* Permissions: `contents: write` (for publishing releases).
* Steps: Check out code, install Python 3.12, install requirements, run unit tests, install Inno Setup, run build script, upload release binaries.
* **Identified Workflow Issue**: Line 42 runs `powershell ... -File .\scripts\build.ps1`. However, the repository contains `build.ps1` in the root directory, not in a `scripts` folder. The workflow will fail on release execution unless corrected.

---

## 11. Third-Party Dependencies Attack Surface

Runtime dependencies defined in `requirements.txt`:

| Package | Version Constraint | Role / Surface | Security Considerations |
| :--- | :--- | :--- | :--- |
| `pywebview` | `>=5.0.0` | Desktop webview wrapper (Edge WebView2 IPC bridge) | Core IPC communication channel. Vulnerabilities in bridge could allow DOM-to-native escapes. |
| `pythonnet` | `>=3.0.0` | .NET CLR interop for WinForms/Edge on Windows | Interops with native Windows assemblies. |
| `PySide6` | `>=6.6.0` | Qt6 GUI bindings (Alternative GUI `main_qt.py`) | Heavy C++ binary extension. Large footprint. Not used by default webview build. |
| `psutil` | `>=5.9.0` | Process and system monitoring | Interacts directly with Windows process tables. |
| `pyinstaller` | `>=6.0.0` | Binary packaging compiler | Compiles executable and bootloader. |

### Supply Chain Risk:
All versions in `requirements.txt` use open-ended `>=` bounds without hash pinning (`--require-hashes`). Upstream malicious updates or breaking API changes could enter builds automatically.
