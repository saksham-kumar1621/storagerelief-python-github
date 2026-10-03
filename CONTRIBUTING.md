# Contributing to StorageRelief (Python Edition)

Thank you for your interest in improving StorageRelief! We welcome contributions from developers, designers, and testers.

---

## 🛠️ Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/saksham-kumar1621/StorageRelief-Python.git
   cd StorageRelief-Python
   ```

2. **Set up a Python Virtual Environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run Locally:**
   ```bash
   python main.py
   # or
   .\run.bat
   ```

---

## 🎨 UI & Aesthetics Guidelines

- **Zero Emojis in Core UI:** All user interface elements must use pure vector SVGs or clean typography.
- **Fluent Dark Glassmorphism:** Adhere to CSS custom properties defined in `ui/web/styles.css`.
- **Holographic Color Balance:** Maintain harmonic ratios between primary mint/aqua accents (`#2dd4bf`), amethyst violet accents (`#c084fc`), and deep obsidian glass backgrounds (`#08090d`).
- **Responsive Layouts:** Ensure all cards and gauge rings scale gracefully across laptop screens (1366x768) and high-DPI desktop displays (4K).

---

## 🔒 Safety & System Rules

- **Safe Deletion Only:** Any new cache or cleaner target must be provably redundant and non-destructive.
- **NTFS Loop Protection:** Always check for directory symlinks / reparse points (`FILE_ATTRIBUTE_REPARSE_POINT`) to avoid infinite recursion.
- **Resilient Unlocking:** Strip Windows read-only flags before deletion attempts and gracefully log locked files without crashing.

---

## 📦 Building Releases

To compile the standalone portable binary and Windows setup installer:
```powershell
.\build.ps1
```
Prerequisites:
- PyInstaller (`pip install pyinstaller`)
- Inno Setup 6 (optional, for `StorageRelief_Setup.exe`)
