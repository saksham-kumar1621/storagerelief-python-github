import os
import stat
import shutil
import subprocess
from typing import List, Tuple, Callable, Optional


def _handle_remove_readonly(func, path, exc_info):
    """
    Error handler for shutil.rmtree on Windows.
    Clears the read-only attribute and retries removal.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


# =========================================================================
# COMPREHENSIVE SECURITY FIREWALL SPECIFICATION:
# StorageRelief STRICTLY asserts that private browser credentials,
# passwords, cookies, active sessions, tab states, and core operating
# system roots are permanently blacklisted and protected from deletion.
# =========================================================================
# Exact file names (case-insensitive) that represent sensitive browser stores or system files
FORBIDDEN_FILE_NAMES = frozenset({
    # Chromium / Edge / Brave / Opera sensitive profile stores
    "login data", "login data-journal", "login data.bak",
    "cookies", "cookies-journal",
    "web data", "web data-journal",
    "history", "history-journal",
    "local state", "bookmarks", "bookmarks.bak",
    "preferences", "secure preferences",
    # Active browser sessions & tab restore (files)
    "current session", "current tabs",
    "last session", "last tabs",
    "tab restore", "session restore",
    # Firefox / Gecko credential & session stores (files)
    "key4.db", "key3.db", "logins.json", "logins-backup.json",
    "places.sqlite", "places.sqlite-wal", "places.sqlite-shm",
    "formhistory.sqlite", "cert9.db", "cert8.db",
    "sessionstore.jsonlz4", "sessionstore.js",
    # Sensitive authentication files & keys
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa",
    # Critical Windows operating system root and kernel files
    "bootmgr", "ntldr", "pagefile.sys", "swapfile.sys", "hiberfil.sys"
})

# Exact directory component names that represent sensitive browser session / credential stores
FORBIDDEN_DIR_NAMES = frozenset({
    # Browser session and state directories
    "sessions",
    "session storage",
    "sessionstore-backups",
    "sync data",
    "token_service",
    # Sensitive host identity & credential folders
    ".ssh",
})

# Backwards compatibility export combining file and dir patterns
FORBIDDEN_DELETION_PATTERNS = frozenset(
    FORBIDDEN_FILE_NAMES | FORBIDDEN_DIR_NAMES | {
        "windows\\system32", "windows\\syswow64", "windows\\system",
        "accounts", "vault", "credentials"
    }
)


def is_path_protected_by_firewall(norm_path: str) -> Tuple[bool, str]:
    """
    Evaluates whether a target path violates security firewall assertions.
    Protects individual files and directory hierarchies without false positives
    on legitimate developer build caches (e.g. Gradle executionHistory.lock, npm, pip).
    """
    norm_lower = os.path.normpath(norm_path).lower()
    base_name = os.path.basename(norm_lower)

    # 1. Exact filename check (O(1) set lookup)
    if base_name in FORBIDDEN_FILE_NAMES:
        return True, f"Protected sensitive file ({base_name})"

    # 2. Path components / directory segment validation
    # Splits path into exact path segments (e.g. ['c:', 'users', 'user', 'sessions', 'tabs'])
    segments = [s for s in norm_lower.replace("/", "\\").split("\\") if s]
    segment_set = set(segments)

    # Check if target itself or any parent directory is a blacklisted sensitive store
    for forbidden_dir in FORBIDDEN_DIR_NAMES:
        if forbidden_dir in segment_set:
            return True, f"Protected sensitive directory store ({forbidden_dir})"

    # Specific credential store paths (AWS credentials, Windows Vault, Windows Credential Manager)
    if norm_lower.endswith(r"\.aws\credentials") or norm_lower.endswith(r"\microsoft\credentials") or norm_lower.endswith(r"\microsoft\vault"):
        return True, "Protected system or cloud credential store"

    # 3. Windows System and Core Protected Directories (system32, syswow64, system)
    for pattern in (r"\windows\system32", r"\windows\syswow64", r"\windows\system"):
        if norm_lower.endswith(pattern) or (pattern + "\\") in norm_lower:
            return True, f"Protected Windows system directory ({pattern})"

    # 4. Check for Drive Root or System Root
    drive, rest = os.path.splitdrive(norm_lower)
    if rest.strip("\\/") == "":
        return True, f"Cannot delete drive root partition ({drive})"

    system_root = os.environ.get("SystemRoot", r"C:\Windows").lower()
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files").lower()
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)").lower()
    program_data = os.environ.get("ProgramData", r"C:\ProgramData").lower()
    user_profile = os.environ.get("USERPROFILE", "").lower()

    # Block direct deletion of top-level system/user directories
    critical_roots = {system_root, program_files, program_files_x86, program_data, user_profile}
    if user_profile:
        critical_roots.add(os.path.dirname(user_profile))  # C:\Users
        critical_roots.update({
            os.path.join(user_profile, "desktop"),
            os.path.join(user_profile, "documents"),
            os.path.join(user_profile, "downloads"),
            os.path.join(user_profile, "pictures"),
            os.path.join(user_profile, "music"),
            os.path.join(user_profile, "videos"),
            os.path.join(user_profile, "appdata"),
            os.path.join(user_profile, "appdata", "local"),
            os.path.join(user_profile, "appdata", "roaming"),
            os.path.join(user_profile, "appdata", "locallow"),
        })

    for crit in critical_roots:
        if crit and norm_lower == crit:
            return True, f"Cannot delete primary operating system or user root ({norm_path})"

    return False, ""


def safe_delete_path(path: str) -> Tuple[bool, str]:
    """
    Safely deletes a file or directory tree with recursive read-only attribute stripping,
    strict firewall validation, symlink/reparse-point protection, and accurate error reporting.
    
    Returns:
        (True, "") on verified deletion
        (False, error_message) on failure or security block
    """
    if not path or not isinstance(path, str):
        return False, "Invalid path specification"

    abs_path = os.path.abspath(os.path.normpath(path))

    # TOCTOU: Check if path exists right now before attempting operations
    if not os.path.lexists(abs_path):
        return False, "Target path does not exist (may have been moved or deleted externally)"

    # Security firewall check: block access to any protected credential, session, or root target
    is_blocked, block_reason = is_path_protected_by_firewall(abs_path)
    if is_blocked:
        return False, f"Blocked by Security Assertion: {block_reason}"

    try:
        # Strip read-only attribute on target
        try:
            os.chmod(abs_path, stat.S_IWRITE)
        except Exception:
            pass

        # SYMLINK / JUNCTION / REPARSE POINT PROTECTION:
        # If the target is a symlink or directory junction, NEVER traverse into it.
        # Only unlink or remove the junction itself.
        if os.path.islink(abs_path):
            try:
                if os.path.isdir(abs_path):
                    os.rmdir(abs_path)
                else:
                    os.unlink(abs_path)
            except Exception:
                os.remove(abs_path)
            
            if os.path.lexists(abs_path):
                return False, "Failed to remove symlink or reparse point"
            return True, ""

        if os.path.isfile(abs_path):
            os.remove(abs_path)
            if os.path.lexists(abs_path):
                return False, "File could not be removed (in use by another process or permission denied)"
            return True, ""

        elif os.path.isdir(abs_path):
            # Pre-audit directory contents: ensure no subfolder or file violates firewall
            # (protects against targeting a browser profile root directly)
            for root, dirs, files in os.walk(abs_path, followlinks=False):
                for d in dirs:
                    d_blocked, _ = is_path_protected_by_firewall(os.path.join(root, d))
                    if d_blocked:
                        return False, f"Directory contains protected session or credential store ({d})"
                for f in files:
                    f_blocked, _ = is_path_protected_by_firewall(os.path.join(root, f))
                    if f_blocked:
                        return False, f"Directory contains protected session or credential store ({f})"

            # Recursively strip read-only attributes
            for root, dirs, files in os.walk(abs_path, followlinks=False):
                for d in dirs:
                    try:
                        os.chmod(os.path.join(root, d), stat.S_IWRITE)
                    except Exception:
                        pass
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), stat.S_IWRITE)
                    except Exception:
                        pass

            try:
                shutil.rmtree(abs_path, onerror=_handle_remove_readonly)
            except Exception as rmtree_err:
                # If full folder removal fails (e.g. process holds an open handle on 1 file),
                # attempt to remove remaining unlocked items
                partial_errors = 0
                try:
                    for entry in os.scandir(abs_path):
                        try:
                            if entry.is_file() or entry.is_symlink():
                                try:
                                    os.chmod(entry.path, stat.S_IWRITE)
                                except Exception:
                                    pass
                                os.remove(entry.path)
                            elif entry.is_dir():
                                shutil.rmtree(entry.path, onerror=_handle_remove_readonly)
                        except Exception:
                            partial_errors += 1
                except Exception:
                    pass

                # Accurate reporting: verify if the target still exists on disk
                if os.path.lexists(abs_path):
                    return False, f"Directory could not be fully removed (locked files or active process handle: {rmtree_err})"

            # Final verification check
            if os.path.lexists(abs_path):
                return False, "Directory could not be completely removed"
            return True, ""
        else:
            return False, "Unknown filesystem object"

    except Exception as e:
        return False, str(e)


def clean_selected_paths(
    paths: List[str],
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Tuple[List[str], List[str]]:
    """
    Cleans an array of paths and returns (deleted_paths, failed_paths_with_reasons).
    Accurately records failures without masking partial errors.
    """
    deleted: List[str] = []
    errors: List[str] = []
    total = len(paths)

    for i, p in enumerate(paths):
        if progress_callback:
            progress_callback(os.path.basename(p) or p, i + 1, total)

        success, err_msg = safe_delete_path(p)
        if success:
            deleted.append(p)
        else:
            errors.append(f"{p}: {err_msg}")

    return deleted, errors


def open_in_file_explorer(path: str) -> bool:
    """Spawns Windows File Explorer highlighting or opening the specified target."""
    if not path or not os.path.exists(path):
        return False

    try:
        norm_path = os.path.normpath(path)
        if os.path.isfile(norm_path):
            subprocess.Popen(["explorer.exe", f"/select,{norm_path}"])
        else:
            subprocess.Popen(["explorer.exe", norm_path])
        return True
    except Exception:
        return False
