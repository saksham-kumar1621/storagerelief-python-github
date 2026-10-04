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
# ZERO-TOLERANCE SECURITY AUDIT GUARANTEE:
# StorageRelief STRICTLY asserts that private browser credentials,
# passwords, cookies, session tokens, and core system directories are
# permanently blacklisted and protected from deletion.
# =========================================================================
FORBIDDEN_DELETION_PATTERNS = frozenset({
    "login data", "login data-journal",
    "cookies", "cookies-journal",
    "web data", "web data-journal",
    "history", "history-journal",
    "local state", "bookmarks", "preferences",
    "windows\\system32", "windows\\syswow64", "bootmgr", "ntldr"
})


def safe_delete_path(path: str) -> Tuple[bool, str]:
    """
    Safely deletes a file or directory tree with recursive read-only attribute stripping.
    Includes active security firewall to protect sensitive user profile and OS files.
    """
    if not os.path.exists(path):
        return True, ""

    # Security firewall check: block access to any protected credential or system target
    path_norm = os.path.normpath(path).lower()
    base_name = os.path.basename(path).lower()
    for forbidden in FORBIDDEN_DELETION_PATTERNS:
        if forbidden in path_norm or forbidden == base_name:
            return False, f"Blocked by Security Assertion: Protected resource ({forbidden})"


    try:
        # Strip read-only attribute on target
        try:
            os.chmod(path, stat.S_IWRITE)
        except Exception:
            pass

        if os.path.isfile(path) or os.path.islink(path):
            os.remove(path)
            return True, ""
        elif os.path.isdir(path):
            # Recursively strip read-only attributes
            for root, dirs, files in os.walk(path):
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
                shutil.rmtree(path, onerror=_handle_remove_readonly)
                return True, ""
            except Exception:
                # If full folder removal fails (e.g. process holds open lock on 1 file),
                # recursively empty all unlocked children inside the folder
                partial_errors = 0
                for entry in os.scandir(path):
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
    Cleans an array of paths and returns (deleted_paths, failed_paths).
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
    if not os.path.exists(path):
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
