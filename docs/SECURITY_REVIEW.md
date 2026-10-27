# Development candidate security review — 2026-10-27

Release gate: **not a clean dependency audit**. Isolated pip-audit scanned the exact tested lock without changing the runtime. Six reported rows deduplicate to three advisories in two packages:

| Locked dependency | Advisory | Assessment |
|---|---|---|
| fastmcp2.14.7 | CVE-2025-64340 / GHSA-m8x7-r2rg-vh5g | Windows CLI installer command injection. This workflow directly runs a fixed Python entrypoint; it does not call fastmcp install claude-code/gemini-cli. Dependency remains affected |
| fastmcp2.14.7 | CVE-2026-27124 / GHSA-rww4-4w9c-7733 | OAuthProxy consent issue. This candidate uses local stdio and no OAuthProxy/GitHubProvider. Dependency remains affected |
| diskcache5.6.3 | CVE-2025-69872 / GHSA-w8v5-vhqr-4h9v | Untrusted write access to pickle cache can lead to execution. No fixed version returned by audit. Do not accept externally supplied cache data or share writable runtime directories; private-cache isolation has not been accepted as a complete remediation |

Primary upstream FastMCP advisories: [installer](https://github.com/PrefectHQ/fastmcp/security/advisories/GHSA-m8x7-r2rg-vh5g), [OAuth](https://github.com/PrefectHQ/fastmcp/security/advisories/GHSA-rww4-4w9c-7733). Both list3.2.0 as patched. A major-version migration and cache dependency replacement require isolated compatibility/real-stdio/GUI/audio reacceptance; not silently applied to the running installation or declared fixed here.

Source export uses a whitelist and scans credentials/personal absolute paths; no runtime config, cache, logs, screenshots, FLP/WAV or vendor presets included. Original MIT license retained. WinRT dependencies are PyWinRT projections/runtime; installed distribution license metadata in DEPENDENCIES.json is an inventory, not legal certification. Locked environment was freshly installed from PyPI and tested. Exact versions are pinned, but wheel hashes are not yet enforced.

Only a limited local development test artifact is accepted. Production/security release remains gated on dependency remediation and remaining GUI coverage. Do not expose this candidate or its bridge as a public network service.
