# Session Log

## 2026-09-29 — Password generator script: requirements agreed (no code yet)

**What:** Gathered requirements for a password generator script. No code
written yet; user will say "generate now" when ready.

**Decisions:**
- Language: PowerShell, started by double-clicking a `.bat` launcher (Windows).
- Settings live in a separate config file, easy to edit:
  - password length (default 20)
  - excluded characters (default: `i I l L | o O 0`)
  - number of passwords to generate
- Each password must contain at least 1 uppercase, 1 lowercase, 1 number,
  and 1 special character.
- Use Windows' cryptographically secure random generator (not `Get-Random`).
- Output goes into specific cells of an Excel workbook the user will provide.

**Open:**
- User to send the Excel file and explain which cells to fill.
- Confirm Excel is installed on the PCs that will run it (needed to write
  into an existing workbook from PowerShell).
- Confirm which special characters are allowed.
- Config file format to confirm.

## 2026-09-29 — CLAUDE.md short forms

Added known short forms `r` = are, `wat` = what, `tis` = this.
