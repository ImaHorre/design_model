# Windows Username Apostrophe — Path Access Fix for Claude CLI

## The problem

The Windows username `ConorO'Sullivan` contains an apostrophe. This breaks path handling
in most of Claude's tools:

- **Read / Write / Edit / Glob / Grep tools** — fail silently or throw a "does not exist"
  error even when the path is valid
- **Bash tool** — the apostrophe breaks shell quoting; the path is never passed correctly
- **PowerShell tool with hardcoded strings** — single-quote quoting schemes conflict with
  the apostrophe in the name

## The fix

**Never hardcode `C:\Users\ConorO'Sullivan\` in any tool call.**

Always use the `$env:USERPROFILE` environment variable in PowerShell, which resolves to
the correct path without requiring the apostrophe to appear in the source string.

```powershell
# WRONG — will fail
Get-ChildItem "C:\Users\ConorO'Sullivan\OneDrive - Peak Emulsions"

# RIGHT — always works
Get-ChildItem "$env:USERPROFILE\OneDrive - Peak Emulsions"
```

## Rules by tool

| Tool | What to do |
|---|---|
| **PowerShell** | Use `$env:USERPROFILE` for any path under the user home |
| **Bash** | Avoid entirely for user-home paths on this machine |
| **Read / Write / Glob / Grep** | Cannot reliably reach paths under `C:\Users\ConorO'Sullivan\` — use PowerShell `Get-Content` / `Set-Content` instead |

## Reading files via PowerShell instead of Read tool

```powershell
# Read a file
Get-Content "$env:USERPROFILE\OneDrive - Peak Emulsions\Documents - Tech sharepoint\XX_Conor\PeakEmulsions\PeakEmulsions\03_Research\Droplet-Microfluidics\CLAUDE.md"

# List a directory
Get-ChildItem "$env:USERPROFILE\OneDrive - Peak Emulsions\Documents - Tech sharepoint\XX_Conor\PeakEmulsions\PeakEmulsions" | Select-Object Name

# Check if a path exists
Test-Path "$env:USERPROFILE\OneDrive - Peak Emulsions\..."

# Write a file (when Write tool cannot reach the path)
Set-Content "$env:USERPROFILE\..." -Value $content
```

## Key paths on this machine

| Location | PowerShell path |
|---|---|
| User home | `$env:USERPROFILE` |
| OneDrive (Peak Emulsions) | `$env:USERPROFILE\OneDrive - Peak Emulsions` |
| Obsidian vault root | `$env:USERPROFILE\OneDrive - Peak Emulsions\Documents - Tech sharepoint\XX_Conor\PeakEmulsions\PeakEmulsions` |
| DMF research wiki | `$env:USERPROFILE\OneDrive - Peak Emulsions\Documents - Tech sharepoint\XX_Conor\PeakEmulsions\PeakEmulsions\03_Research\Droplet-Microfluidics` |
| Claude global config | `$env:USERPROFILE\.claude` |

## Where to put this instruction for Claude

**The global `~/.claude/CLAUDE.md` cannot be used for this fix.** That file lives at
`C:\Users\ConorO'Sullivan\.claude\CLAUDE.md` — which Claude cannot reliably read due to
the same apostrophe problem. The fix cannot bootstrap itself from there.

**The correct approach: add the rule to every new project's `CLAUDE.md` early.**

When starting a new project, paste the one-liner rule (below) into the project's
`CLAUDE.md` before doing anything that requires user-home path access.

## Plans — same problem, same fix

Claude CLI tries to save plan files to `~/.claude/plans/` by default, which hits the
same apostrophe failure. Always tell Claude to save plans to the **local project**
`.claude/` folder instead:

> "Save the plan to `.claude/plans/` in this project, not the global folder."

Add this to any project CLAUDE.md where planning work happens:

```
Save all plan files to the local .claude/ folder in this project directory,
not to the global ~/.claude/ folder.
```

## One-line rule to paste into any CLAUDE.md

```
Never hardcode C:\Users\ConorO'Sullivan\ in tool calls — the apostrophe breaks path
resolution. Always use $env:USERPROFILE in the PowerShell tool instead. Use
Get-Content / Get-ChildItem / Set-Content for any file operations under the user home.
```
