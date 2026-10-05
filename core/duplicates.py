import os
import sys
import stat
import hashlib
import ctypes
import re
import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Callable, Set, Any, Tuple

from core.scanner import format_bytes, is_reparse_point


@dataclass
class DuplicateFile:
    id: str
    path: str
    name: str
    size_bytes: int
    size_formatted: str
    modified_time: float
    modified_formatted: str
    is_original: bool
    selected_for_delete: bool
    ext: str


@dataclass
class DuplicateGroup:
    group_id: str
    hash_digest: str
    file_size: int
    file_size_formatted: str
    wasted_bytes: int
    wasted_formatted: str
    files: List[DuplicateFile]


@dataclass
class DuplicateScanResult:
    total_scanned_files: int
    total_scanned_bytes: int
    duplicate_groups_count: int
    total_wasted_bytes: int
    total_wasted_formatted: str
    groups: List[DuplicateGroup]


def score_originality(filepath: str, mtime: float = 0.0) -> float:
    """
    Intelligently scores how likely a file is to be the true 'Original' intended document
    rather than an accidental duplicate or downloaded copy.
    
    Higher score = stronger confidence that this is the primary/original file.
    Addresses audit critique: 'the assumption that older duplicate files are always the originals'.
    """
    score = 100.0
    name = os.path.basename(filepath).lower()
    norm_p = os.path.normpath(filepath).lower()

    # 1. Penalize obvious copy markers and browser download collision suffixes
    # Examples: "photo (1).png", "report - Copy.docx", "document_copy.pdf", "Copy of presentation.pptx"
    copy_patterns = [
        r"\(\d+\)",               # (1), (2), etc.
        r"\[\d+\]",               # [1], [2], etc.
        r" - copy",               # "file - Copy"
        r"_copy",                 # "file_copy"
        r"copy of",               # "Copy of file"
        r"\(copy\)",              # "(copy)"
        r"_duplicate",            # "_duplicate"
    ]
    for pattern in copy_patterns:
        if re.search(pattern, name):
            score -= 45.0
            break

    # 2. Prefer canonical user library directories over disposable/incoming scratchpads
    if "\\documents\\" in norm_p or "\\documents" in norm_p:
        score += 30.0
    elif "\\pictures\\" in norm_p or "\\photos\\" in norm_p:
        score += 30.0
    elif "\\music\\" in norm_p or "\\videos\\" in norm_p:
        score += 25.0
    elif "\\desktop\\" in norm_p:
        score += 15.0
    elif "\\downloads\\" in norm_p:
        # Downloads directory is overwhelmingly where duplicate collisions originate
        score -= 30.0
    elif "\\temp\\" in norm_p or "\\tmp\\" in norm_p or "\\appdata\\" in norm_p:
        score -= 40.0

    # 3. Path Depth: Shorter, cleaner directory structures are more likely canonical
    path_depth = len(norm_p.split(os.sep))
    score -= min(15.0, path_depth * 1.0)

    # 4. Secondary tie-breaker: older modification time gets a slight boost if locations are equal
    if mtime > 0:
        # Modest micro-score scaling so it never overrides copy names or curated folder priorities
        score -= (mtime / 1e11)

    return score


def verify_duplicate_integrity_before_delete(
    duplicate_path: str,
    sibling_paths: List[str],
    expected_size: int
) -> Tuple[bool, str]:
    """
    TOCTOU Pre-Deletion Integrity Verification:
    Asserts that deleting this duplicate will NOT cause permanent total data loss:
    1. Validates that the target duplicate file exists and hasn't changed size.
    2. Validates that at least ONE other valid copy in the group still exists on disk
       and has matching file size.
    """
    norm_dup = os.path.normpath(duplicate_path)
    if not os.path.isfile(norm_dup):
        return False, "Target duplicate file no longer exists on disk"

    try:
        if os.path.getsize(norm_dup) != expected_size:
            return False, "Target duplicate file size changed since scanning (TOCTOU violation)"
    except Exception as e:
        return False, f"Cannot verify duplicate file: {e}"

    # Search for at least one surviving sibling copy
    surviving_copies = 0
    for sib in sibling_paths:
        norm_sib = os.path.normpath(sib)
        if norm_sib.lower() == norm_dup.lower():
            continue
        if os.path.isfile(norm_sib):
            try:
                if os.path.getsize(norm_sib) == expected_size:
                    surviving_copies += 1
            except Exception:
                pass

    if surviving_copies == 0:
        return False, "ABORTED: No surviving original or sibling copy found on disk! Deletion stopped to prevent total data loss."

    return True, ""


def get_quick_partial_hash(filepath: str, sample_size: int = 4096) -> Optional[str]:
    """Reads head and tail bytes to generate a fast intermediate verification signature."""
    try:
        size = os.path.getsize(filepath)
        if size == 0:
            return "empty_file"
        hasher = hashlib.md5()
        with open(filepath, "rb") as f:
            # Head bytes
            hasher.update(f.read(sample_size))
            if size > sample_size * 2:
                # Tail bytes
                f.seek(size - sample_size)
                hasher.update(f.read(sample_size))
        return hasher.hexdigest()
    except (PermissionError, FileNotFoundError, OSError):
        return None


def get_full_hash(filepath: str, chunk_size: int = 65536) -> Optional[str]:
    """Computes a cryptographically secure SHA-256 digest of the entire file."""
    try:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, FileNotFoundError, OSError):
        return None


def scan_duplicates(
    target_dirs: List[str],
    min_size_mb: float = 1.0,
    min_size_bytes: Optional[int] = None,
    file_types: Optional[Set[str]] = None,
    progress_callback: Optional[Callable[[str], None]] = None
) -> DuplicateScanResult:
    """
    Executes a high-efficiency multi-stage duplicate scan across the selected directories.
    Stage 1: Size grouping
    Stage 2: Fast partial boundary hash (Head & Tail)
    Stage 3: Full SHA-256 cryptographic verification
    Stage 4: Intelligent Original determination (curated library + clean filename priority)
    """
    if min_size_bytes is None:
        min_size_bytes = int(min_size_mb * 1024 * 1024)
    size_map: Dict[int, List[str]] = {}
    total_scanned_files = 0
    total_scanned_bytes = 0

    if progress_callback:
        progress_callback("Enumerating files across target directories...")

    def traverse_dir(folder: str, depth: int = 0):
        nonlocal total_scanned_files, total_scanned_bytes
        if depth > 15:
            return

        try:
            with os.scandir(folder) as it:
                for entry in it:
                    try:
                        if entry.is_symlink() or is_reparse_point(entry.path):
                            continue
                        if entry.is_file(follow_symlinks=False):
                            total_scanned_files += 1
                            ext = os.path.splitext(entry.name)[1].lower()
                            if file_types and ext not in file_types:
                                continue

                            st = entry.stat(follow_symlinks=False)
                            sz = st.st_size
                            total_scanned_bytes += sz

                            if sz >= min_size_bytes:
                                if sz not in size_map:
                                    size_map[sz] = []
                                size_map[sz].append(entry.path)

                        elif entry.is_dir(follow_symlinks=False):
                            traverse_dir(entry.path, depth + 1)
                    except (PermissionError, FileNotFoundError, OSError):
                        continue
        except (PermissionError, FileNotFoundError, OSError):
            return

    for target in target_dirs:
        if os.path.isdir(target):
            traverse_dir(target, 0)

    # Filter out sizes with only 1 file
    candidate_sizes = {sz: paths for sz, paths in size_map.items() if len(paths) > 1}
    total_candidates = sum(len(paths) for paths in candidate_sizes.values())

    if progress_callback:
        progress_callback(f"Analyzing {total_candidates} size-matched candidate files...")

    # 2. Phase 2: Fast Partial Boundary Hash (Head & Tail)
    partial_map: Dict[tuple, List[str]] = {}
    for sz, paths in candidate_sizes.items():
        for p in paths:
            ph = get_quick_partial_hash(p)
            if ph:
                key = (sz, ph)
                if key not in partial_map:
                    partial_map[key] = []
                partial_map[key].append(p)

    # Filter out singletons
    candidate_partials = {k: paths for k, paths in partial_map.items() if len(paths) > 1}

    # 3. Phase 3: Full Cryptographic Hash Verification
    if progress_callback:
        progress_callback("Computing cryptographic byte verification...")

    full_hash_map: Dict[tuple, List[str]] = {}
    for (sz, _), paths in candidate_partials.items():
        for p in paths:
            fh = get_full_hash(p)
            if fh:
                key = (sz, fh)
                if key not in full_hash_map:
                    full_hash_map[key] = []
                full_hash_map[key].append(p)

    # Filter verified duplicate groups
    verified_groups = {k: paths for k, paths in full_hash_map.items() if len(paths) > 1}

    groups: List[DuplicateGroup] = []
    group_counter = 0
    total_wasted_bytes = 0

    for (sz, fh), paths in verified_groups.items():
        group_counter += 1
        wasted_for_group = sz * (len(paths) - 1)
        total_wasted_bytes += wasted_for_group

        # Multi-factor Smart Original determination
        file_info_list = []
        for p in paths:
            try:
                mtime = os.path.getmtime(p)
                dt = datetime.datetime.fromtimestamp(mtime).strftime("%b %d, %Y %H:%M")
            except Exception:
                mtime = 0
                dt = "Unknown"

            orig_score = score_originality(p, mtime)

            file_info_list.append({
                "path": p,
                "name": os.path.basename(p),
                "mtime": mtime,
                "mtime_formatted": dt,
                "ext": os.path.splitext(p)[1].lower(),
                "orig_score": orig_score,
            })

        # Sort by originality score descending: highest score = True Original
        file_info_list.sort(key=lambda x: x["orig_score"], reverse=True)

        dup_files: List[DuplicateFile] = []
        for idx, fi in enumerate(file_info_list):
            is_orig = (idx == 0)
            dup_files.append(DuplicateFile(
                id=f"dup_{group_counter}_{idx + 1}",
                path=fi["path"],
                name=fi["name"],
                size_bytes=sz,
                size_formatted=format_bytes(sz),
                modified_time=fi["mtime"],
                modified_formatted=fi["mtime_formatted"],
                is_original=is_orig,
                selected_for_delete=not is_orig,  # Select duplicates by default, leave original safe
                ext=fi["ext"],
            ))

        groups.append(DuplicateGroup(
            group_id=f"group_{group_counter}",
            hash_digest=fh,
            file_size=sz,
            file_size_formatted=format_bytes(sz),
            wasted_bytes=wasted_for_group,
            wasted_formatted=format_bytes(wasted_for_group),
            files=dup_files,
        ))

    # Sort largest wasted space groups first
    groups.sort(key=lambda g: g.wasted_bytes, reverse=True)

    if progress_callback:
        progress_callback(f"Deduplication complete: {len(groups)} duplicate clusters uncovered.")

    return DuplicateScanResult(
        total_scanned_files=total_scanned_files,
        total_scanned_bytes=total_scanned_bytes,
        duplicate_groups_count=len(groups),
        total_wasted_bytes=total_wasted_bytes,
        total_wasted_formatted=format_bytes(total_wasted_bytes),
        groups=groups,
    )


def get_default_scan_targets(drive_letter: str = "C:\\") -> List[Dict[str, Any]]:
    """Returns accessible default user library directories for duplicate hunting, tailored to the selected drive."""
    user_profile = os.environ.get("USERPROFILE", "C:\\Users\\Default")
    cleaned = drive_letter.strip().rstrip("/\\")
    drive_root = (cleaned[:2] if len(cleaned) >= 2 and cleaned[1] == ":" else "C:").upper() + "\\"
    system_drive = os.environ.get("SystemDrive", "C:").upper().rstrip("\\") + "\\"

    if drive_root.upper() == system_drive.upper():
        targets = [
            {"id": "downloads", "name": "Downloads", "path": os.path.join(user_profile, "Downloads"), "enabled": True},
            {"id": "videos", "name": "Videos", "path": os.path.join(user_profile, "Videos"), "enabled": True},
            {"id": "documents", "name": "Documents", "path": os.path.join(user_profile, "Documents"), "enabled": True},
            {"id": "pictures", "name": "Pictures", "path": os.path.join(user_profile, "Pictures"), "enabled": False},
            {"id": "desktop", "name": "Desktop", "path": os.path.join(user_profile, "Desktop"), "enabled": False},
        ]
    else:
        # Secondary drive targets
        candidates = [
            ("downloads", "Downloads", os.path.join(drive_root, "Downloads"), True),
            ("videos", "Videos", os.path.join(drive_root, "Videos"), True),
            ("movies", "Movies", os.path.join(drive_root, "Movies"), True),
            ("media", "Media", os.path.join(drive_root, "Media"), False),
            ("games", "Games", os.path.join(drive_root, "Games"), False),
            ("projects", "Projects", os.path.join(drive_root, "Projects"), False),
            ("backups", "Backups", os.path.join(drive_root, "Backups"), False),
            ("root", f"Drive Root ({drive_root[:2]})", drive_root, False),
        ]
        targets = [
            {"id": cid, "name": cname, "path": cpath, "enabled": cenabled}
            for cid, cname, cpath, cenabled in candidates
            if os.path.exists(cpath)
        ]
        if not targets:
            targets = [{"id": "root", "name": f"Drive Root ({drive_root[:2]})", "path": drive_root, "enabled": True}]

    return [t for t in targets if os.path.isdir(t["path"])]
