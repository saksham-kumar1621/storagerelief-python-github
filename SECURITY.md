# Security Policy

## 🛡️ Safe Deletion Design Principles

StorageRelief is designed with file integrity as its highest priority:

1. **Non-Destructive Target Boundaries:** Scans only target known disposable caches, obsolete secondary version binaries, crash dumps, and temp artifacts. Active executables, user data directories, registry hives, and system boot files are strictly out-of-scope.
2. **NTFS Junction & Symlink Guards:** StorageRelief detects Windows `reparse_points` / symlinks and never recurses across junctions, eliminating infinite traversal loops.
3. **Pre-Deletion User Inspection:** Users can click the **Explorer** icon next to any item to verify its actual contents on disk before proceeding.
4. **Itemized Confirmation Modal:** Cleanups require explicit confirmation and display the exact list of targets and calculated byte reclaim values.
5. **No Telemetry / No Phone-Home:** StorageRelief operates 100% offline. Zero analytics, telemetry, or network calls are made.

---

## 🔒 Zero Browser Credential Access Guarantee

StorageRelief specifically distinguishes between **disposable rendering caches** and **private user profile data**:

- **Allowed Targets:** Only isolated rendering artifacts (`Cache\Cache_Data`, `Code Cache\js`, `GPUCache`).
- **Permanently Blacklisted Files:** All private browser data (`Login Data`, `Login Data-journal`, `Cookies`, `Cookies-journal`, `Web Data`, `History`, `Bookmarks`, `Preferences`, `Local State`, `Sessions`) are strictly excluded.
- **Active Deletion Firewall:** An internal security firewall in `core/cleaner.py` (`FORBIDDEN_DELETION_PATTERNS`) programmatically validates all paths and refuses deletion if any protected credential pattern is encountered.
- Transparent Open-Source Verification: No pre-compiled binaries are stored in the git repository. All builds are generated directly from public Python source code.

---

## 📚 Detailed Security Documentation

Comprehensive architecture, audit findings, and defensive specifications are documented in the [`security/`](security/) directory:
- [Threat Model](security/threat-model.md) — STRIDE analysis, assets, trust boundaries, and attack scenarios.
- [Secrets & Credential Audit](security/secrets.md) — Comprehensive audit of secrets handling, environment vars, and git history.
- [Attack Surface Analysis](security/attack-surface.md) — Inventory of IPC endpoints, filesystem inputs, and execution pathways.
- [Security Checklist](security/security-checklist.md) — 20-domain project-specific checklist with categorized findings and recommendations.

---

## 🚨 Reporting a Vulnerability

If you discover a potential security or data-loss vulnerability, please submit an issue or contact the project maintainers with:
- Description of the target directory or path.
- Reproduction steps.
- Windows version and environment details.

