# Security And Privacy Notes

This project is designed for a local Raspberry Pi birdbox deployment. Treat your footage, credentials, and local network details as private by default.

## Never Commit

The `.gitignore` is intentionally strict. Check before every public push that these are absent:

- `.env` or any file containing passwords, tokens, app passwords, or API keys.
- Raw video clips, extracted frames, stream captures, logs, SQLite databases, or labelled datasets.
- SSH keys, private hostnames, private usernames, local-only IP notes, or router details.
- Private deployment handoff notes.

If a credential is committed, assume it has leaked. Rotate it immediately; deleting it in a later commit is not enough.

## Email Credentials

Email is optional. The detector runs without it.

If you enable email:

- Store settings only in `.env` or real environment variables.
- Prefer an app-specific password from your mail provider, not your normal account password.
- Do not log sender or recipient addresses.
- Keep attachment sizes small; many providers reject large messages.

## Local Stream

The MJPEG stream binds to all network interfaces on the Pi so devices on your LAN can view it.

Recommended defaults:

- Keep the stream on your home or field LAN.
- Do not port-forward it from your router.
- Use a VPN or private tunnel if you need remote access.
- Remember that live view pauses motion detection while it is active.

## SSH And Wi-Fi

The optional Wi-Fi watchdog is deliberately conservative:

- It attempts soft recovery.
- It does not reboot the Pi automatically.
- You should test any Wi-Fi power-saving services manually before enabling them in `.env`.

Use SSH keys, disable password login if you are comfortable doing so, and avoid publishing usernames or host details from your own network.

## Wildlife And Legal Responsibility

Nestboxes can involve protected wildlife, sensitive locations, and footage you may not intend to share. Before using this project:

- Check local wildlife law and good-practice guidance.
- Avoid unnecessary disturbance, especially during nesting.
- Keep exact locations private for sensitive species or sites.
- Be careful with public dashboards, maps, timestamps, or footage that could reveal locations.

## Pre-Publish Checklist

Run these checks before publishing a fork or release:

```bash
git status --short
git ls-files
rg -n --hidden -g "!**/.git/**" -i "192\\.168|password|token|secret|api[_-]?key|private|BEGIN .*KEY|ssh|local ip|exact location" .
```

Expected results:

- `git status --short` shows only intended source/docs changes.
- `git ls-files` does not include media, `.env`, logs, databases, or private notes.
- Search results contain only safe documentation or placeholder variable names.
