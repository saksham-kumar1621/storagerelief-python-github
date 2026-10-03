import os
import sys
import stat
import hashlib
import ctypes
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Callable, Set, Any

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


def get_quick_partial_hash(filepath: str, sample_size: int = 4096) -> Optional[str]:
    """Reads head and tail bytes to generate a fast intermediate verification signature."""
    try:
        size = os.path.getsize(filepath)
        hasher = hashlib.blake2b(digest_size=16)
        with open(filepath, "rb") as f:
            # Read first chunk
            hasher.update(f.read(sample_size))
            if size > sample_size * 2:
                # Seek and read last chunk
                f.seek(size - sample_size)
                hasher.update(f.read(sample_size))
        return hasher.hexdigest()
    except (PermissionError, FileNotFoundError, OSError):
        return None


def get_full_hash(filepath: str, chunk_size: int = 65536) -> Optional[str]:
    """Computes buffered full 128-bit BLAKE2b hash of the entire file."""
    try:
        hasher = hashlib.blake2b(digest_size=20)
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, FileNotFoundError, OSError):
        return None


def scan_duplicates(
    target_dirs: List[str],
    min_size_bytes: int = 1024 * 1024,  # Default 1 MB threshold
    file_types: Optional[Set[str]] = None,
    max_depth: int = 7,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> DuplicateScanResult:
    """
    Ultra-fast 3-phase duplicate file scanner:
    Phase 1: Direct O(1) file size clustering (eliminates ~95% of non-duplicates without reading file bodies).
    Phase 2: Head/tail boundary hash check for size collisions.
    Phase 3: Buffered cryptographic hash for exact byte parity.
    """
    if progress_callback:
        progress_callback("Auditing target directories...")

    size_map: Dict[int, List[str]] = {}
    total_scanned_files = 0
    total_scanned_bytes = 0

    # 1. Phase 1: Directory Traversal & Size Indexing
    def traverse_dir(folder: str, depth: int):
        nonlocal total_scanned_files, total_scanned_bytes
        if depth > max_depth or is_reparse_point(folder):
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

        # Sort files by creation/modification time so oldest is considered the "Original"
        file_info_list = []
        for p in paths:
            try:
                mtime = os.path.getmtime(p)
                mtime_str = os.path.getmtime(p)
                # Simple readable date format
                import datetime
                dt = datetime.datetime.fromtimestamp(mtime).strftime("%b %d, %Y %H:%M")
            except Exception:
                mtime = 0
                dt = "Unknown"

            file_info_list.append({
                "path": p,
                "name": os.path.basename(p),
                "mtime": mtime,
                "mtime_formatted": dt,
                "ext": os.path.splitext(p)[1].lower(),
            })

        # Oldest file first -> designated as Original
        file_info_list.sort(key=lambda x: x["mtime"])

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
