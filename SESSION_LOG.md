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

- Planned files: `generate-passwords.bat` (double-click) runs
  `generate-passwords.ps1`, which reads a config file.
- Proposed config format (not yet confirmed): plain text, one setting per
  line, editable in Notepad:
  ```
  Length=20
  Count=10
  Exclude=iIlL|oO0
  ```
- Excel is written via Excel's COM automation (requires Excel installed).
- Security note given: passwords in a plain workbook are readable by anyone
  with the file; suggested Excel "Encrypt with Password" or importing into
  a free password manager (Bitwarden / KeePassXC).

**Open:**
- User to send the Excel file and explain which cells to fill.
- Confirm Excel is installed on the PCs that will run it.
- Confirm allowed special characters. Default set proposed:
  `! # $ % & * + - . = ? @ ^ _ ~ ( ) [ ] { } < > , ; : / \ ' " `` ` ``.
  Asked whether to drop quotes / backslash / backtick, or make the allowed
  set a config setting.
- Confirm config file format above.
- User rule: do NOT write the script until the user says "generate now".

## 2026-09-29 — Moving to a local session

User is moving this work to a Claude Code session running on their own PC
(Claude Desktop app or `claude remote-control`) so Claude can read local
files such as the Excel workbook. The new session should start by reading
this log. Work so far is on branch `claude/nice-lovelace-v6ls4j`.

Other notes from this session:
- Sidebar "groups" (kpop-feeder, ubiquitous-craft, Other…) are automatic,
  based on each session's repo/working directory; they can't be edited by
  hand. "Projects" (beta, Sept 2026) is a separate feature with a
  "Move to project" action.

## 2026-09-29 — CLAUDE.md short forms

Added known short forms `r` = are, `wat` = what, `tis` = this.
