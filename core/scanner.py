import os
import sys
import stat
import ctypes
from dataclasses import dataclass
from typing import List, Optional, Callable


@dataclass
class StorageItem:
    id: str
    name: str
    path: str
    size_bytes: int
    size_formatted: str
    category: str          # "ghost_apps", "media_gaming", "browser_caches", "system_bloat", "caches", "dev_junk", "archives", "virtual_disks"
    category_label: str
    risk_level: str        # "safe", "review", "caution"
    description: str
    selected: bool


@dataclass
class DriveInfo:
    total_bytes: int
    free_bytes: int
    used_bytes: int
    total_gb: float
    free_gb: float
    used_gb: float
    percent_free: float
    letter: str = "C:\\"
    display_letter: str = "C:"
    label: str = "OS"
    drive_type: str = "fixed"
    drive_type_label: str = "System NVMe/SSD"
    file_system: str = "NTFS"
    is_system: bool = True


def format_bytes(bytes_count: int) -> str:
    KB = 1024
    MB = KB * 1024
    GB = MB * 1024

    if bytes_count >= GB:
        return f"{bytes_count / GB:.2f} GB"
    elif bytes_count >= MB:
        return f"{bytes_count / MB:.1f} MB"
    elif bytes_count >= KB:
        return f"{bytes_count / KB:.1f} KB"
    else:
        return f"{bytes_count} B"


def is_reparse_point(path: str) -> bool:
    """Detects NTFS junctions, mount points, and symlinks on Windows."""
    if os.path.islink(path):
        return True
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs != -1 and (attrs & 0x0400):  # FILE_ATTRIBUTE_REPARSE_POINT
            return True
    except Exception:
        pass
    return False


def get_dir_size_safe(path: str, depth: int = 0, max_depth: int = 4) -> int:
    """
    Recursively calculates directory size with:
    1. Strict NTFS junction & symlink bypass (prevents loops)
    2. Max depth guard (prevents stack exhaustion)
    3. Non-blocking error tolerance for locked files
    """
    if depth > max_depth:
        return 0

    if is_reparse_point(path):
        return 0

    total = 0
    try:
        with os.scandir(path) as it:
            for entry in it:
                try:
                    if entry.is_symlink() or is_reparse_point(entry.path):
                        continue
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += get_dir_size_safe(entry.path, depth + 1, max_depth)
                except (PermissionError, FileNotFoundError, OSError):
                    continue
    except (PermissionError, FileNotFoundError, OSError):
        return 0

    return total


def get_available_drives() -> List[DriveInfo]:
    """
    Enumerates all active logical drives on the Windows host.
    Extracts volume label, drive type (fixed NVMe/SSD, removable USB),
    file system (NTFS, exFAT), and real-time storage capacities.
    """
    drives: List[DriveInfo] = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    system_drive = os.environ.get("SystemDrive", "C:").upper().rstrip("\\")
    gb_div = 1024.0 * 1024.0 * 1024.0

    for i in range(26):
        if (bitmask >> i) & 1:
            letter = chr(65 + i) + ":\\"
            display = chr(65 + i) + ":"
            dtype = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(letter))

            # 0=UNKNOWN, 1=NO_ROOT, 5=CDROM
            if dtype in (0, 1):
                continue

            free_caller = ctypes.c_ulonglong(0)
            total = ctypes.c_ulonglong(0)
            free_total = ctypes.c_ulonglong(0)

            res = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(letter),
                ctypes.byref(free_caller),
                ctypes.byref(total),
                ctypes.byref(free_total),
            )
            if res == 0 or total.value == 0:
                continue

            vol_name = ctypes.create_unicode_buffer(1024)
            fs_name = ctypes.create_unicode_buffer(1024)
            serial = ctypes.c_ulong()
            max_len = ctypes.c_ulong()
            flags = ctypes.c_ulong()
            ctypes.windll.kernel32.GetVolumeInformationW(
                ctypes.c_wchar_p(letter),
                vol_name,
                1024,
                ctypes.byref(serial),
                ctypes.byref(max_len),
                ctypes.byref(flags),
                fs_name,
                1024,
            )

            is_sys = (display.upper() == system_drive)
            t_bytes = total.value
            f_bytes = free_total.value
            u_bytes = max(0, t_bytes - f_bytes)
            p_free = (f_bytes / t_bytes * 100.0) if t_bytes > 0 else 0.0

            type_labels = {
                2: ("removable", "Removable USB"),
                3: ("fixed", "Local NVMe/SSD"),
                4: ("network", "Network Drive"),
                5: ("cdrom", "Optical Disc"),
                6: ("ramdisk", "RAM Disk"),
            }
            d_type, d_type_label = type_labels.get(dtype, ("fixed", "Local Disk"))
            if is_sys:
                d_type_label = "System NVMe/SSD"

            label = vol_name.value.strip() or ("Local Disk" if d_type == "fixed" else "USB Drive")

            drives.append(DriveInfo(
                total_bytes=t_bytes,
                free_bytes=f_bytes,
                used_bytes=u_bytes,
                total_gb=round(t_bytes / gb_div, 2),
                free_gb=round(f_bytes / gb_div, 2),
                used_gb=round(u_bytes / gb_div, 2),
                percent_free=round(p_free, 1),
                letter=letter,
                display_letter=display,
                label=label,
                drive_type=d_type,
                drive_type_label=d_type_label,
                file_system=fs_name.value.strip() or "NTFS",
                is_system=is_sys,
            ))

    return drives


def get_drive_info(drive_letter: str = "C:\\") -> DriveInfo:
    """Queries real-time drive space via Win32 GetDiskFreeSpaceExW for any target drive letter."""
    # Normalize drive letter to format 'X:\'
    cleaned = drive_letter.strip().rstrip("/\\")
    if len(cleaned) == 1 and cleaned.isalpha():
        target_root = f"{cleaned.upper()}:\\"
    elif len(cleaned) >= 2 and cleaned[1] == ":":
        target_root = f"{cleaned[:2].upper()}\\"
    else:
        target_root = "C:\\"

    free_bytes_caller = ctypes.c_ulonglong(0)
    total_bytes = ctypes.c_ulonglong(0)
    total_free_bytes = ctypes.c_ulonglong(0)

    res = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        ctypes.c_wchar_p(target_root),
        ctypes.byref(free_bytes_caller),
        ctypes.byref(total_bytes),
        ctypes.byref(total_free_bytes),
    )

    if res == 0:
        raise RuntimeError(f"Failed to query drive {target_root} info via Windows API")

    vol_name = ctypes.create_unicode_buffer(1024)
    fs_name = ctypes.create_unicode_buffer(1024)
    serial = ctypes.c_ulong()
    max_len = ctypes.c_ulong()
    flags = ctypes.c_ulong()
    ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(target_root),
        vol_name,
        1024,
        ctypes.byref(serial),
        ctypes.byref(max_len),
        ctypes.byref(flags),
        fs_name,
        1024,
    )

    dtype = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(target_root))
    system_drive = os.environ.get("SystemDrive", "C:").upper().rstrip("\\")
    display = target_root[:2].upper()
    is_sys = (display == system_drive)

    type_labels = {
        2: ("removable", "Removable USB"),
        3: ("fixed", "Local NVMe/SSD"),
        4: ("network", "Network Drive"),
        5: ("cdrom", "Optical Disc"),
        6: ("ramdisk", "RAM Disk"),
    }
    d_type, d_type_label = type_labels.get(dtype, ("fixed", "Local Disk"))
    if is_sys:
        d_type_label = "System NVMe/SSD"

    total = total_bytes.value
    free = total_free_bytes.value
    used = max(0, total - free)
    gb_div = 1024.0 * 1024.0 * 1024.0
    percent_free = (free / total * 100.0) if total > 0 else 0.0
    label = vol_name.value.strip() or ("Local Disk" if d_type == "fixed" else "USB Drive")

    return DriveInfo(
        total_bytes=total,
        free_bytes=free,
        used_bytes=used,
        total_gb=round(total / gb_div, 2),
        free_gb=round(free / gb_div, 2),
        used_gb=round(used / gb_div, 2),
        percent_free=round(percent_free, 1),
        letter=target_root,
        display_letter=display,
        label=label,
        drive_type=d_type,
        drive_type_label=d_type_label,
        file_system=fs_name.value.strip() or "NTFS",
        is_system=is_sys,
    )


def scan_storage(drive_letter: str = "C:\\", progress_callback: Optional[Callable[[str], None]] = None) -> tuple[DriveInfo, List[StorageItem]]:
    """Runs a multi-category deep storage scan across the specified drive partition."""
    if progress_callback:
        progress_callback(f"Querying real-time drive metrics for {drive_letter[:2]}...")

    drive_info = get_drive_info(drive_letter)
    user_profile = os.environ.get("USERPROFILE", "C:\\Users\\Default")
    items: List[StorageItem] = []
    id_counter = 0

    if not drive_info.is_system:
        # =========================================================================
        # Non-System Secondary Drive / USB Storage Scan Flow
        # =========================================================================
        drive_root = drive_info.letter

        # 1. Drive Root Caches, Trash & Temp Folders
        if progress_callback:
            progress_callback(f"Scanning root temp & recycle containers on {drive_info.display_letter}...")

        root_cache_candidates = [
            (os.path.join(drive_root, "$Recycle.Bin"), f"{drive_info.display_letter} Recycle Bin Container", "caches", "review", "Files sent to the Windows Recycle Bin on this partition"),
            (os.path.join(drive_root, "Temp"), f"{drive_info.display_letter} Root Temp Directory", "caches", "safe", "Temporary scratch files on root volume"),
            (os.path.join(drive_root, "tmp"), f"{drive_info.display_letter} Root tmp Directory", "caches", "safe", "Temporary scratch files on root volume"),
            (os.path.join(drive_root, ".tmp"), f"{drive_info.display_letter} Hidden .tmp Directory", "caches", "safe", "Hidden scratch folder"),
        ]

        for p, name, cat, risk, desc in root_cache_candidates:
            if os.path.exists(p):
                sz = get_dir_size_safe(p, 0, 4)
                if sz > 5 * 1024 * 1024:  # > 5 MB
                    id_counter += 1
                    items.append(StorageItem(
                        id=f"item_{id_counter}",
                        name=name,
                        path=p,
                        size_bytes=sz,
                        size_formatted=format_bytes(sz),
                        category=cat,
                        category_label="Cache & Temp",
                        risk_level=risk,
                        description=desc,
                        selected=(risk == "safe"),
                    ))

        # 2. Game Client Incomplete Downloads & Shaders (Steam, Epic, Riot)
        if progress_callback:
            progress_callback(f"Analyzing game library download caches on {drive_info.display_letter}...")

        game_cache_candidates = [
            (os.path.join(drive_root, "SteamLibrary", "steamapps", "downloading"), "Steam Incomplete Downloads", "caches", "safe", "Stale or interrupted Steam game download chunks"),
            (os.path.join(drive_root, "SteamLibrary", "steamapps", "temp"), "Steam Staging Temp", "caches", "safe", "Temporary game patching staging files"),
            (os.path.join(drive_root, "SteamLibrary", "steamapps", "shadercache"), "Steam Vulkan/DX Shader Cache", "caches", "safe", "Rebuildable game shader pre-cache"),
            (os.path.join(drive_root, "Steam", "steamapps", "downloading"), "Steam Incomplete Downloads", "caches", "safe", "Stale or interrupted Steam game download chunks"),
            (os.path.join(drive_root, "Steam", "steamapps", "temp"), "Steam Staging Temp", "caches", "safe", "Temporary game patching staging files"),
            (os.path.join(drive_root, "Epic Games", "DirectXRedist"), "Epic Games DirectX Installers", "caches", "safe", "Duplicate DirectX setup packages bundled with games"),
            (os.path.join(drive_root, "GOG Galaxy", "Games", "!Downloads"), "GOG Galaxy Download Cache", "caches", "safe", "Interrupted or cached GOG installer packages"),
            (os.path.join(drive_root, "Ubisoft Game Launcher", "cache"), "Ubisoft Launcher Cache", "caches", "safe", "Rebuildable launcher cache"),
        ]

        for p, name, cat, risk, desc in game_cache_candidates:
            if os.path.exists(p):
                sz = get_dir_size_safe(p, 0, 4)
                if sz > 20 * 1024 * 1024:  # > 20 MB
                    id_counter += 1
                    items.append(StorageItem(
                        id=f"item_{id_counter}",
                        name=name,
                        path=p,
                        size_bytes=sz,
                        size_formatted=format_bytes(sz),
                        category=cat,
                        category_label="Cache & Temp",
                        risk_level=risk,
                        description=desc,
                        selected=True,
                    ))

        # 3. Developer Repositories on Secondary Drive
        if progress_callback:
            progress_callback(f"Checking developer codebases on {drive_info.display_letter}...")

        dev_roots = [
            os.path.join(drive_root, "Projects"),
            os.path.join(drive_root, "Dev"),
            os.path.join(drive_root, "Code"),
            os.path.join(drive_root, "Source"),
            os.path.join(drive_root, "Workspace"),
            os.path.join(drive_root, "repos"),
            os.path.join(drive_root, "Work"),
        ]

        for d_root in dev_roots:
            if not os.path.isdir(d_root):
                continue
            try:
                for proj in os.scandir(d_root):
                    if not proj.is_dir():
                        continue
                    p_name = proj.name
                    build_targets = [
                        (os.path.join(proj.path, "flutter_app", "build"), "Flutter Build Cache", "dev_junk", "safe", "Rebuildable compiled Flutter APK/debug binaries"),
                        (os.path.join(proj.path, "build"), "Build Directory", "dev_junk", "safe", "Compiled output binaries"),
                        (os.path.join(proj.path, "dist"), "Dist Package Output", "dev_junk", "safe", "Compiled distribution artifacts"),
                        (os.path.join(proj.path, "src-tauri", "target"), "Rust/Tauri Target Cache", "dev_junk", "safe", "Rebuildable cargo build artifacts"),
                        (os.path.join(proj.path, ".venv"), "Python Virtual Environment", "dev_junk", "review", "Virtual environment (can be re-created)"),
                        (os.path.join(proj.path, "node_modules"), "Node Modules Folder", "dev_junk", "review", "Node.js dependencies (reinstallable via npm install)"),
                    ]
                    for bt, label, cat, risk, desc in build_targets:
                        if os.path.isdir(bt):
                            sz = get_dir_size_safe(bt, 0, 4)
                            if sz > 50 * 1024 * 1024:
                                id_counter += 1
                                items.append(StorageItem(
                                    id=f"item_{id_counter}",
                                    name=f"{p_name} / {label}",
                                    path=bt,
                                    size_bytes=sz,
                                    size_formatted=format_bytes(sz),
                                    category=cat,
                                    category_label="Dev Build/Cache",
                                    risk_level=risk,
                                    description=desc,
                                    selected=(risk == "safe"),
                                ))
            except (PermissionError, OSError):
                continue

        # 4. Large Archives, Repacks & ISOs on Secondary Drive (> 300 MB)
        if progress_callback:
            progress_callback(f"Auditing large repacks and ISO images on {drive_info.display_letter}...")

        archive_exts = {".bin", ".iso", ".zip", ".rar", ".exe", ".msi", ".7z", ".tar", ".gz"}
        check_folders = [
            drive_root,
            os.path.join(drive_root, "Downloads"),
            os.path.join(drive_root, "ISOs"),
            os.path.join(drive_root, "Torrents"),
            os.path.join(drive_root, "Games"),
            os.path.join(drive_root, "Installers"),
            os.path.join(drive_root, "Setup"),
            os.path.join(drive_root, "Backups"),
        ]

        for folder in check_folders:
            if not os.path.isdir(folder):
                continue
            try:
                for entry in os.scandir(folder):
                    try:
                        if entry.is_file():
                            sz = entry.stat().st_size
                            if sz > 300 * 1024 * 1024:
                                ext = os.path.splitext(entry.name)[1].lower()
                                if ext in archive_exts:
                                    id_counter += 1
                                    items.append(StorageItem(
                                        id=f"item_{id_counter}",
                                        name=entry.name,
                                        path=entry.path,
                                        size_bytes=sz,
                                        size_formatted=format_bytes(sz),
                                        category="archives",
                                        category_label="Heavy Installer/Archive",
                                        risk_level="review",
                                        description="Large installer or archive on secondary drive.",
                                        selected=False,
                                    ))
                        elif entry.is_dir():
                            fname_lower = entry.name.lower()
                            if any(k in fname_lower for k in ("repack", "setup", "installer", "extracted")):
                                sz = get_dir_size_safe(entry.path, 0, 3)
                                if sz > 300 * 1024 * 1024:
                                    id_counter += 1
                                    items.append(StorageItem(
                                        id=f"item_{id_counter}",
                                        name=entry.name,
                                        path=entry.path,
                                        size_bytes=sz,
                                        size_formatted=format_bytes(sz),
                                        category="archives",
                                        category_label="Heavy Installer/Archive",
                                        risk_level="review",
                                        description="Large downloaded installer or unpacked repack directory.",
                                        selected=False,
                                    ))
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue

        # 5. Virtual Machine Images on Secondary Drive
        vm_dirs = [
            os.path.join(drive_root, "VMs"),
            os.path.join(drive_root, "Virtual Machines"),
            os.path.join(drive_root, "VirtualBox VMs"),
            drive_root,
        ]
        vm_exts = {".vdi", ".vmdk", ".vhdx", ".hdd", ".qcow2"}
        for vdir in vm_dirs:
            if not os.path.isdir(vdir):
                continue
            try:
                for ventry in os.scandir(vdir):
                    if ventry.is_file():
                        ext = os.path.splitext(ventry.name)[1].lower()
                        if ext in vm_exts:
                            sz = ventry.stat().st_size
                            if sz > 500 * 1024 * 1024:
                                id_counter += 1
                                items.append(StorageItem(
                                    id=f"item_{id_counter}",
                                    name=ventry.name,
                                    path=ventry.path,
                                    size_bytes=sz,
                                    size_formatted=format_bytes(sz),
                                    category="virtual_disks",
                                    category_label="Virtual Machine / Disk Image",
                                    risk_level="review",
                                    description="Virtual machine disk image container.",
                                    selected=False,
                                ))
            except (PermissionError, OSError):
                continue

        # Sort largest items first
        items.sort(key=lambda x: x.size_bytes, reverse=True)
        if progress_callback:
            progress_callback(f"Scan complete for {drive_info.display_letter}! Found {len(items)} reclaimable items.")
        return drive_info, items

    # =========================================================================
    # System Drive (C:) Standard Scan Flow
    # =========================================================================
    # =========================================================================
    # 1. Ghost Apps (Multi-version accumulator detection)
    # =========================================================================
    if progress_callback:
        progress_callback("Deep scanning Ghost App versions across software...")

    # Multi-version app inspectors (CapCut, Discord, Slack, Postman, Figma)
    ghost_app_inspectors = [
        ("CapCut", os.path.join(user_profile, "AppData", "Local", "CapCut", "Apps"), "", "CapCut Legacy v"),
        ("Discord", os.path.join(user_profile, "AppData", "Local", "Discord"), "app-", "Discord Legacy v"),
        ("Slack", os.path.join(user_profile, "AppData", "Local", "slack"), "app-", "Slack Legacy v"),
        ("Postman", os.path.join(user_profile, "AppData", "Local", "Postman"), "app-", "Postman Legacy v"),
        ("Figma", os.path.join(user_profile, "AppData", "Local", "Figma"), "app-", "Figma Legacy v"),
    ]

    for app_name, root_p, prefix, label_prefix in ghost_app_inspectors:
        if os.path.isdir(root_p):
            try:
                subdirs = [
                    d.path for d in os.scandir(root_p)
                    if d.is_dir() and (not prefix or d.name.startswith(prefix))
                ]
                subdirs.sort()
                if len(subdirs) > 1:
                    # Keep latest build, flag obsolete previous versions
                    for old_v in subdirs[:-1]:
                        sz = get_dir_size_safe(old_v, 0, 4)
                        if sz > 10 * 1024 * 1024:  # > 10 MB
                            id_counter += 1
                            v_name = os.path.basename(old_v)
                            items.append(StorageItem(
                                id=f"item_{id_counter}",
                                name=f"{label_prefix}{v_name}",
                                path=old_v,
                                size_bytes=sz,
                                size_formatted=format_bytes(sz),
                                category="ghost_apps",
                                category_label="Ghost App Version",
                                risk_level="safe",
                                description=f"Obsolete previous version build of {app_name} left behind after auto-update",
                                selected=True,
                            ))
            except Exception:
                pass

    # Discord staged update package archives
    disc_packages = os.path.join(user_profile, "AppData", "Local", "Discord", "packages")
    if os.path.isdir(disc_packages):
        sz = get_dir_size_safe(disc_packages, 0, 2)
        if sz > 20 * 1024 * 1024:
            id_counter += 1
            items.append(StorageItem(
                id=f"item_{id_counter}",
                name="Discord Update Package Cache",
                path=disc_packages,
                size_bytes=sz,
                size_formatted=format_bytes(sz),
                category="ghost_apps",
                category_label="Ghost App Version",
                risk_level="safe",
                description="Accumulated Discord Squirrel installer packages (.nupkg)",
                selected=True,
            ))

    # Spotify staged updates
    spotify_update = os.path.join(user_profile, "AppData", "Local", "Spotify", "Update")
    if os.path.isdir(spotify_update):
        sz = get_dir_size_safe(spotify_update, 0, 2)
        if sz > 15 * 1024 * 1024:
            id_counter += 1
            items.append(StorageItem(
                id=f"item_{id_counter}",
                name="Spotify Staged Update Files",
                path=spotify_update,
                size_bytes=sz,
                size_formatted=format_bytes(sz),
                category="ghost_apps",
                category_label="Ghost App Version",
                risk_level="safe",
                description="Pending or leftover Spotify client update binaries",
                selected=True,
            ))

    # =========================================================================
    # 2. Media, Creator & Gaming Caches (Steam, Epic, Adobe, DaVinci, Spotify, Shaders)
    # =========================================================================
    if progress_callback:
        progress_callback("Auditing Media, Creator & Gaming Caches...")

    media_gaming_targets = [
        # GPU Shader Caches
        (os.path.join(user_profile, "AppData", "Local", "NVIDIA", "DXCache"),
         "NVIDIA DirectX Shader Cache", "media_gaming", "safe", "Precompiled DirectX shaders (auto-rebuilt on game launch)"),
        (os.path.join(user_profile, "AppData", "Local", "NVIDIA", "GLCache"),
         "NVIDIA OpenGL Shader Cache", "media_gaming", "safe", "Precompiled OpenGL shaders (auto-rebuilt on launch)"),
        (os.path.join(user_profile, "AppData", "Local", "D3DSCache"),
         "Windows Global DirectX Shader Cache", "media_gaming", "safe", "Universal DirectX D3D shader cache"),
        (os.path.join(user_profile, "AppData", "Local", "AMD", "DxCache"),
         "AMD Radeon Shader Cache", "media_gaming", "safe", "Precompiled AMD graphics shaders"),
        
        # Steam Caches
        (r"C:\Program Files (x86)\Steam\steamapps\downloading",
         "Steam Incomplete Downloads", "media_gaming", "safe", "Stale or interrupted Steam game download staging chunks"),
        (r"C:\Program Files (x86)\Steam\steamapps\temp",
         "Steam Staging Temp", "media_gaming", "safe", "Temporary game patching and update staging files"),
        (r"C:\Program Files (x86)\Steam\steamapps\shadercache",
         "Steam Game Shader Pre-Cache", "media_gaming", "safe", "Vulkan and DirectX game shader pre-cache"),
        (os.path.join(user_profile, "AppData", "Local", "Steam", "htmlcache"),
         "Steam Client HTML Browser Cache", "media_gaming", "safe", "Embedded Chromium web cache for Steam store and library"),
        (r"C:\Program Files (x86)\Steam\appcache\httpcache",
         "Steam HTTP Network Cache", "media_gaming", "safe", "Cached store banners and metadata"),

        # Epic Games Launcher
        (os.path.join(user_profile, "AppData", "Local", "EpicGamesLauncher", "Saved", "webcache"),
         "Epic Games Web Cache", "media_gaming", "safe", "Embedded web browser cache in Epic Games launcher"),
        (os.path.join(user_profile, "AppData", "Local", "EpicGamesLauncher", "Saved", "Logs"),
         "Epic Games Launcher Logs", "media_gaming", "safe", "Historical game launcher diagnostic logs"),

        # Riot Games & Battle.net
        (r"C:\Riot Games\Riot Client\UX\GPUCache",
         "Riot Client GPU Cache", "media_gaming", "safe", "Valorant & LoL Riot Client UI GPU cache"),
        (r"C:\ProgramData\Battle.net\Agent\data\cache",
         "Battle.net Agent Cache", "media_gaming", "safe", "Blizzard Battle.net agent download cache"),

        # Creator Tools: Adobe Premiere / After Effects Media Cache
        (os.path.join(user_profile, "AppData", "Roaming", "Adobe", "Common", "Media Cache Files"),
         "Adobe Premiere / AE Media Cache", "media_gaming", "review", "Conforming audio (.cfa) and video preview render files"),
        (os.path.join(user_profile, "AppData", "Roaming", "Adobe", "Common", "Peak Files"),
         "Adobe Peak Audio Waveform Files", "media_gaming", "safe", "Generated .pek audio waveform display files (re-generated on project load)"),
        (os.path.join(user_profile, "AppData", "Roaming", "Adobe", "Common", "Media Cache"),
         "Adobe Common Media Database", "media_gaming", "review", "Cached media records for Adobe Creative Cloud video editors"),

        # Creator Tools: DaVinci Resolve
        (os.path.join(user_profile, "AppData", "Roaming", "Blackmagic Design", "DaVinci Resolve", "Support", ".Cache"),
         "DaVinci Resolve Project Cache", "media_gaming", "review", "Temporary timeline proxies and render cache"),
        (os.path.join(user_profile, "Videos", "CacheClip"),
         "DaVinci Resolve CacheClip", "media_gaming", "review", "Rendered timeline clip cache (can be re-rendered in DaVinci)"),

        # Streaming & Communication Apps Media Caches
        (os.path.join(user_profile, "AppData", "Local", "Spotify", "Storage"),
         "Spotify Audio & Offline Cache", "media_gaming", "safe", "Temporary downloaded song cache and album artwork"),
        (os.path.join(user_profile, "AppData", "Roaming", "discord", "Cache"),
         "Discord Chat Media Cache", "media_gaming", "safe", "Cached images, avatars, and attachments from Discord servers"),
        (os.path.join(user_profile, "AppData", "Roaming", "discord", "Code Cache"),
         "Discord Code Cache", "media_gaming", "safe", "Compiled JavaScript bytecode for Discord desktop"),
        (os.path.join(user_profile, "AppData", "Roaming", "Telegram Desktop", "tdata", "user_data", "cache"),
         "Telegram Desktop Media Cache", "media_gaming", "safe", "Cached voice messages, images, and stickers"),
        (os.path.join(user_profile, "AppData", "Local", "Packages", "5319275A.WhatsAppDesktop_cv1g1gvanyjgm", "LocalCache"),
         "WhatsApp Desktop Local Cache", "media_gaming", "safe", "Temporary media and thumbnail cache"),
        (os.path.join(user_profile, "AppData", "Roaming", "Code", "GPUCache"),
         "VS Code GPU Shader Cache", "media_gaming", "safe", "Rebuildable GPU renderer cache for Visual Studio Code"),
    ]

    for p, name, cat, risk, desc in media_gaming_targets:
        if os.path.exists(p):
            sz = get_dir_size_safe(p, 0, 4)
            if sz > 5 * 1024 * 1024:  # > 5 MB
                id_counter += 1
                items.append(StorageItem(
                    id=f"item_{id_counter}",
                    name=name,
                    path=p,
                    size_bytes=sz,
                    size_formatted=format_bytes(sz),
                    category=cat,
                    category_label="Media & Gaming Cache",
                    risk_level=risk,
                    description=desc,
                    selected=(risk == "safe"),
                ))

    # =========================================================================
    # 3. Web Browser Deep Caches (Chrome, Edge, Brave, Firefox, Opera)
    # =========================================================================
    if progress_callback:
        progress_callback("Auditing Web Browser deep caches...")

    browser_targets = [
        # Google Chrome
        (os.path.join(user_profile, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Cache"),
         "Google Chrome Browser Cache", "browser_caches", "safe", "Cached web pages, images, and network responses"),
        (os.path.join(user_profile, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "Code Cache"),
         "Google Chrome Code Cache", "browser_caches", "safe", "V8 compiled JavaScript and WebAssembly code cache"),
        (os.path.join(user_profile, "AppData", "Local", "Google", "Chrome", "User Data", "Default", "GPUCache"),
         "Google Chrome GPU Cache", "browser_caches", "safe", "Hardware-accelerated web graphics shader cache"),

        # Microsoft Edge
        (os.path.join(user_profile, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Cache"),
         "Microsoft Edge Browser Cache", "browser_caches", "safe", "Cached web assets and network downloads"),
        (os.path.join(user_profile, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "Code Cache"),
         "Microsoft Edge Code Cache", "browser_caches", "safe", "Precompiled JavaScript bytecode cache"),
        (os.path.join(user_profile, "AppData", "Local", "Microsoft", "Edge", "User Data", "Default", "GPUCache"),
         "Microsoft Edge GPU Cache", "browser_caches", "safe", "DirectX/Edge UI GPU acceleration cache"),

        # Brave Browser
        (os.path.join(user_profile, "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data", "Default", "Cache"),
         "Brave Browser Cache", "browser_caches", "safe", "Cached site media and web elements"),
        (os.path.join(user_profile, "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data", "Default", "Code Cache"),
         "Brave Browser Code Cache", "browser_caches", "safe", "Compiled script cache for Brave"),

        # Opera & Opera GX
        (os.path.join(user_profile, "AppData", "Local", "Opera Software", "Opera Stable", "Cache"),
         "Opera Browser Cache", "browser_caches", "safe", "Temporary browser cache"),
        (os.path.join(user_profile, "AppData", "Local", "Opera Software", "Opera GX Stable", "Cache"),
         "Opera GX Browser Cache", "browser_caches", "safe", "Gaming browser cache and streaming temp files"),
    ]

    for p, name, cat, risk, desc in browser_targets:
        if os.path.exists(p):
            sz = get_dir_size_safe(p, 0, 4)
            if sz > 5 * 1024 * 1024:  # > 5 MB
                id_counter += 1
                items.append(StorageItem(
                    id=f"item_{id_counter}",
                    name=name,
                    path=p,
                    size_bytes=sz,
                    size_formatted=format_bytes(sz),
                    category=cat,
                    category_label="Web Browser Cache",
                    risk_level=risk,
                    description=desc,
                    selected=True,
                ))

    # Mozilla Firefox profile caches
    firefox_profiles = os.path.join(user_profile, "AppData", "Local", "Mozilla", "Firefox", "Profiles")
    if os.path.isdir(firefox_profiles):
        try:
            for prof in os.scandir(firefox_profiles):
                if prof.is_dir():
                    ff_cache = os.path.join(prof.path, "cache2")
                    if os.path.isdir(ff_cache):
                        sz = get_dir_size_safe(ff_cache, 0, 4)
                        if sz > 10 * 1024 * 1024:
                            id_counter += 1
                            items.append(StorageItem(
                                id=f"item_{id_counter}",
                                name=f"Firefox Profile Cache ({prof.name.split('.')[1] if '.' in prof.name else prof.name})",
                                path=ff_cache,
                                size_bytes=sz,
                                size_formatted=format_bytes(sz),
                                category="browser_caches",
                                category_label="Web Browser Cache",
                                risk_level="safe",
                                description="Cached web pages, media, and fonts from Firefox sessions",
                                selected=True,
                            ))
        except Exception:
            pass

    # =========================================================================
    # 4. Windows System Junk & Diagnostics (Crash Dumps, WER, Update Bloat)
    # =========================================================================
    if progress_callback:
        progress_callback("Auditing Windows System Junk, WER & Crash Dumps...")

    system_bloat_targets = [
        (os.path.join(user_profile, "AppData", "Local", "CrashDumps"),
         "Windows User Crash Dumps", "system_bloat", "safe", "Memory dumps created when applications crash (.dmp files)"),
        (r"C:\ProgramData\Microsoft\Windows\WER\ReportArchive",
         "Windows Error Report Archives (WER)", "system_bloat", "safe", "Archived telemetry reports sent to Microsoft after crashes"),
        (r"C:\ProgramData\Microsoft\Windows\WER\ReportQueue",
         "Windows Error Reporting Queue", "system_bloat", "safe", "Pending telemetry error reports queued on disk"),
        (r"C:\Windows\Minidump",
         "Windows Kernel Crash Minidumps", "system_bloat", "safe", "Small BSOD memory dumps created during Blue Screen crashes"),
        (r"C:\Windows\SoftwareDistribution\Download",
         "Windows Update Download Staging", "system_bloat", "safe", "Downloaded Windows update installer packages that have already been installed"),
        (r"C:\Windows\SoftwareDistribution\DeliveryOptimization",
         "Windows Delivery Optimization Cache", "system_bloat", "safe", "Peer-to-peer Windows update distribution cache"),
        (os.path.join(user_profile, "AppData", "Local", "Microsoft", "Windows", "Explorer"),
         "Windows Explorer Thumbnail Cache", "system_bloat", "safe", "Cached thumbnail database (.db) for images and videos in Explorer"),
        (r"C:\Windows\Prefetch",
         "Windows Prefetch Traces", "system_bloat", "safe", "App startup execution traces (re-created automatically by Windows)"),
    ]

    for p, name, cat, risk, desc in system_bloat_targets:
        if os.path.exists(p):
            sz = get_dir_size_safe(p, 0, 4)
            if sz > 1 * 1024 * 1024:  # > 1 MB
                id_counter += 1
                items.append(StorageItem(
                    id=f"item_{id_counter}",
                    name=name,
                    path=p,
                    size_bytes=sz,
                    size_formatted=format_bytes(sz),
                    category=cat,
                    category_label="Windows System Junk",
                    risk_level=risk,
                    description=desc,
                    selected=True,
                ))

    # Heavy Windows BSOD Complete Memory Dump (MEMORY.DMP)
    bsod_dump = r"C:\Windows\MEMORY.DMP"
    if os.path.isfile(bsod_dump):
        try:
            sz = os.path.getsize(bsod_dump)
            if sz > 100 * 1024 * 1024:
                id_counter += 1
                items.append(StorageItem(
                    id=f"item_{id_counter}",
                    name="Windows BSOD Full Kernel Dump (MEMORY.DMP)",
                    path=bsod_dump,
                    size_bytes=sz,
                    size_formatted=format_bytes(sz),
                    category="system_bloat",
                    category_label="Windows System Junk",
                    risk_level="review",
                    description="Full RAM image dump written during a system crash",
                    selected=False,
                ))
        except Exception:
            pass

    # =========================================================================
    # 5. General Temp & Package Caches (%TEMP%, pip, npm, gradle)
    # =========================================================================
    if progress_callback:
        progress_callback("Scanning package & scratch temp caches...")

    cache_targets = [
        (os.environ.get("TEMP", os.path.join(user_profile, "AppData", "Local", "Temp")),
         "User Temp Directory (%TEMP%)", "caches", "safe", "Application temporary work files, installers, and logs"),
        ("C:\\Windows\\Temp", "Windows System Temp", "caches", "safe", "System-level temporary files and installer remnants"),
        ("C:\\Temp", "Root Temp Directory", "caches", "safe", "Windows root temporary scratch space"),
        ("C:\\tmp", "Root tmp Directory", "caches", "safe", "Windows root tmp scratch space"),
        (os.path.join(user_profile, "AppData", "Local", "CapCut", "User Data", "Cache"),
         "CapCut Video Project Cache", "caches", "safe", "Temporary timeline proxies and effect caches"),
        (os.path.join(user_profile, "AppData", "Local", "uv", "cache"),
         "uv Python Package Cache", "caches", "safe", "Cached Python wheels and binaries"),
        (os.path.join(user_profile, "AppData", "Local", "npm-cache"),
         "npm Package Cache", "caches", "safe", "Cached Node.js npm packages"),
        (os.path.join(user_profile, "AppData", "Local", "pip", "cache"),
         "pip Package Cache", "caches", "safe", "Cached Python pip downloads"),
        (os.path.join(user_profile, ".gradle", "caches"),
         "Gradle Build Cache", "caches", "safe", "Cached Android/Java gradle dependencies"),
        (os.path.join(user_profile, "OneDrive", "Desktop", ".tmp.driveupload"),
         "OneDrive Sync Upload Temp", "caches", "safe", "Interrupted OneDrive cloud upload cache"),
    ]

    for p, name, cat, risk, desc in cache_targets:
        if os.path.exists(p):
            sz = get_dir_size_safe(p, 0, 4)
            if sz > 5 * 1024 * 1024:  # > 5 MB
                id_counter += 1
                items.append(StorageItem(
                    id=f"item_{id_counter}",
                    name=name,
                    path=p,
                    size_bytes=sz,
                    size_formatted=format_bytes(sz),
                    category=cat,
                    category_label="Temp & Package Cache",
                    risk_level=risk,
                    description=desc,
                    selected=True,
                ))

    # =========================================================================
    # 6. Heavy Repacks, Installers & Large Archives (> 300 MB)
    # =========================================================================
    if progress_callback:
        progress_callback("Checking heavy repacks and installers...")

    archive_exts = {".bin", ".iso", ".zip", ".rar", ".exe", ".msi", ".7z", ".tar", ".gz"}
    scan_dirs = [
        os.path.join(user_profile, "Downloads"),
        os.path.join(user_profile, "Desktop"),
        os.path.join(user_profile, "OneDrive", "Desktop"),
    ]

    for d in scan_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for entry in os.scandir(d):
                try:
                    if entry.is_file():
                        sz = entry.stat().st_size
                        if sz > 300 * 1024 * 1024:  # > 300 MB
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext in archive_exts:
                                id_counter += 1
                                items.append(StorageItem(
                                    id=f"item_{id_counter}",
                                    name=entry.name,
                                    path=entry.path,
                                    size_bytes=sz,
                                    size_formatted=format_bytes(sz),
                                    category="archives",
                                    category_label="Heavy Installer/Archive",
                                    risk_level="review",
                                    description="Large downloaded installer or archive. Safe to remove if already installed.",
                                    selected=False,
                                ))
                    elif entry.is_dir():
                        fname_lower = entry.name.lower()
                        if any(k in fname_lower for k in ("repack", "setup", "installer", "extracted")):
                            sz = get_dir_size_safe(entry.path, 0, 3)
                            if sz > 300 * 1024 * 1024:
                                id_counter += 1
                                items.append(StorageItem(
                                    id=f"item_{id_counter}",
                                    name=entry.name,
                                    path=entry.path,
                                    size_bytes=sz,
                                    size_formatted=format_bytes(sz),
                                    category="archives",
                                    category_label="Heavy Installer/Archive",
                                    risk_level="review",
                                    description="Large downloaded installer or archive directory.",
                                    selected=False,
                                ))
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            continue

    # 4. Developer Artifacts & Heavy Build Output
    if progress_callback:
        progress_callback("Scanning developer project roots...")

    project_roots = [
        os.path.join(user_profile, "OneDrive", "Desktop", "Projects"),
        os.path.join(user_profile, "Desktop", "Projects"),
        os.path.join(user_profile, "Projects"),
    ]

    for root in project_roots:
        if not os.path.isdir(root):
            continue
        try:
            for proj in os.scandir(root):
                if not proj.is_dir():
                    continue

                p_name = proj.name
                # Protect current app directories from self-cleaning
                if "storagerelief" in p_name.lower() or "storage-relief" in p_name.lower():
                    continue

                build_targets = [
                    (os.path.join(proj.path, "flutter_app", "build"), "Flutter Build Cache", "dev_junk", "safe", "Rebuildable compiled Flutter APK/debug binaries"),
                    (os.path.join(proj.path, "build"), "Build Directory", "dev_junk", "safe", "Compiled output binaries"),
                    (os.path.join(proj.path, "dist"), "Dist Package Output", "dev_junk", "safe", "Compiled distribution artifacts"),
                    (os.path.join(proj.path, "src-tauri", "target"), "Rust/Tauri Target Cache", "dev_junk", "safe", "Rebuildable cargo build artifacts"),
                    (os.path.join(proj.path, ".venv"), "Python Virtual Environment", "dev_junk", "review", "Virtual environment (can be re-created via requirements.txt)"),
                    (os.path.join(proj.path, "node_modules"), "Node Modules Folder", "dev_junk", "review", "Node.js dependencies (can be reinstalled via npm install)"),
                ]

                for bt, label, cat, risk, desc in build_targets:
                    if os.path.isdir(bt):
                        sz = get_dir_size_safe(bt, 0, 4)
                        if sz > 50 * 1024 * 1024:  # > 50 MB
                            id_counter += 1
                            items.append(StorageItem(
                                id=f"item_{id_counter}",
                                name=f"{p_name} / {label}",
                                path=bt,
                                size_bytes=sz,
                                size_formatted=format_bytes(sz),
                                category=cat,
                                category_label="Dev Build/Cache",
                                risk_level=risk,
                                description=desc,
                                selected=(risk == "safe"),
                            ))
        except (PermissionError, OSError):
            continue

    # 5. Virtual Machines & Emulators
    if progress_callback:
        progress_callback("Auditing emulator and VM virtual disks...")

    vm_targets = [
        ("C:\\Program Files\\Netease\\MuMuPlayer\\vms", "MuMuPlayer VM Disks", "virtual_disks", "review", "Android emulator virtual hard drive (.vdi)"),
        (os.path.join(user_profile, "AppData", "Local", "wsl"), "WSL Virtual Hard Drive", "virtual_disks", "caution", "Windows Subsystem for Linux ext4.vhdx storage disk"),
    ]

    for p, name, cat, risk, desc in vm_targets:
        if os.path.exists(p):
            sz = get_dir_size_safe(p, 0, 3)
            if sz > 500 * 1024 * 1024:  # > 500 MB
                id_counter += 1
                items.append(StorageItem(
                    id=f"item_{id_counter}",
                    name=name,
                    path=p,
                    size_bytes=sz,
                    size_formatted=format_bytes(sz),
                    category=cat,
                    category_label="Virtual Machine / Emulator",
                    risk_level=risk,
                    description=desc,
                    selected=False,
                ))

    # Sort largest items first
    items.sort(key=lambda x: x.size_bytes, reverse=True)

    if progress_callback:
        progress_callback(f"Scan complete! Found {len(items)} reclaimable items.")

    return drive_info, items
