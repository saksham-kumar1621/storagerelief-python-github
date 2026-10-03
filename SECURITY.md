# Security Policy

## 🛡️ Safe Deletion Design Principles

StorageRelief is designed with file integrity as its highest priority:

1. **Non-Destructive Target Boundaries:** Scans only target known disposable caches, obsolete secondary version binaries, crash dumps, and temp artifacts. Active executables, user data directories, registry hives, and system boot files are strictly out-of-scope.
2. **NTFS Junction & Symlink Guards:** StorageRelief detects Windows `reparse_points` / symlinks and never recurses across junctions, eliminating infinite traversal loops.
3. **Pre-Deletion User Inspection:** Users can click the **Explorer** icon next to any item to verify its actual contents on disk before proceeding.
4. **Itemized Confirmation Modal:** Cleanups require explicit confirmation and display the exact list of targets and calculated byte reclaim values.
5. **No Telemetry / No Phone-Home:** StorageRelief operates 100% offline. Zero analytics, telemetry, or network calls are made.

---

## 🚨 Reporting a Vulnerability

If you discover a potential security or data-loss vulnerability, please submit an issue or contact the project maintainers with:
- Description of the target directory or path.
- Reproduction steps.
- Windows version and environment details.
