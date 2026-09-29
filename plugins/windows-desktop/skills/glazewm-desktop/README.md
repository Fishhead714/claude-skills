# glazewm-desktop

One-script setup for a tiling Windows desktop: [GlazeWM](https://github.com/glzr-io/glazewm) (tiling window manager) + [YASB](https://github.com/amnweb/yasb) (status bar) showing workspace numbers and a local CPU / memory / disk indicator.

Part of [claude-skills](../../../../) — usable standalone, or as a [Claude Code](https://docs.claude.com/en/docs/claude-code) skill (`/plugin install windows-desktop@fishhead714-skills`). `SKILL.md` (Chinese) doubles as the detailed troubleshooting guide.

## What you get

- **9 workspaces.** With two monitors, 1–5 are pinned to the leftmost screen and 6–9 to the right; with one monitor, no pinning.
- **Keys:** `Alt+1..9` switch workspace · `Alt+Shift+1..9` move window there and follow · `Alt+Shift+A/F` move the whole workspace to the left/right screen · `Alt+Shift+R` reload config.
- **A thin bar on every screen:** workspace numbers on the left (current one highlighted), and `🟢local C12 M45` on the right — the dot turns green / orange / red at CPU 60/85 %, memory 80/90 %, C: drive 85/95 %. Click to expand details.

## Install

In a normal (non-admin) PowerShell, from this directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

Idempotent — safe to re-run. It will:

1. install GlazeWM and YASB via `winget` (skipped if present);
2. offer to uninstall Zebar (bundled with GlazeWM; replaced here by YASB);
3. write configs sized to your monitor count, backing up existing files as `*.bak-<timestamp>`;
4. add GlazeWM to per-user autostart;
5. detect and offer to fix the Windows `Alt+Shift` input-language hotkey conflict;
6. start or reload everything.

Preview only, without installing or changing anything:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -RenderOnly C:\temp\preview
```

## Pitfalls worth knowing (details in `SKILL.md`)

- **`Alt+Shift+<number>` does nothing** → Windows' "switch input language" hotkey owns Left Alt+Shift. Set `Language Hotkey` under `HKCU\Keyboard Layout\Toggle` to `3`, then sign out.
- **Don't `winget uninstall glzr-io.glazewm` to remove Zebar** — winget files Zebar under GlazeWM's ID and may remove both. Uninstall Zebar by its own MSI product code.
- **YASB custom widget stuck on `Loading...`** → don't set `exec_options.encoding`; YASB decodes the output again and the worker thread dies silently.
- **YASB custom widget shows a PowerShell banner** → YASB splits `run_cmd` on spaces and ignores quotes, so the script path must contain no spaces or quotes.
- **`glazewm.exe` says it "requires elevation"** → it has `uiAccess`; launch via `Start-Process` (ShellExecute), or talk to its IPC at `ws://localhost:6123`.
- **Two monitors show different load numbers** → solved with a shared cache + named mutex; the cache TTL must stay below YASB's `run_interval`.
- **PowerShell 5.1 garbles non-ASCII text** → keep every `.ps1` as UTF-8 **with BOM**.

## Requirements

Windows 10/11 with `winget`. Tested on a two-monitor (landscape + portrait) setup.

## License

MIT — see the repository root [`LICENSE`](../../../../LICENSE).
