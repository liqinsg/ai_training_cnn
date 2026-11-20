# 01 — Runtime Facts (v685 scope)

## Access and boundaries

- Read-only access: current repository, its `logs/` directory, and the MC archive path referenced by the inspected v685 loader.
- No remote server shell, live process status, broker API, or independently authenticated production configuration was available.
- No credentials or environment files were read. No order, position, strategy, risk, or production configuration was changed.
- Repository at inspection: branch `v2026c`, commit `fb30a285fa8ed1a764b0de3289a1e6b04c6f85b4`.

## Runtime evidence

| Evidence | Observation | Status |
|---|---|---|
| Local v685 source | `fx_trade_bot_v685.py` sets `APP_VERSION = "685-2"` and labels positions by profile. | E1 local source fact |
| Profile configuration | `config_profile.json` reports version `6.8.4`; v685 reads its `VERSION` from the profile configuration. | E1 local source fact |
| Worktree configuration diff | `ranking_cooldown.REMOVE_COOLDOWN` is `true` in the worktree and `false` in Git HEAD. | E1 repository-state fact; not made or reverted by this audit; deployment status unknown |
| v685 log tags | November `logs/fx_bot_202611*.log` include v685-2 profile ownership tags and MC/decision records. | E1 log fact |
| Checked-in service unit | `fx-trade-bot.service` points to `/home/nie/projects/ai_training_cnn/fx_trade_bot_v6.py`, not the current workspace's v685 entrypoint. | E1 checked-in config fact; not proof of active service |
| Visible crontab | The checked-in `crontab` contains v683 commands, not a confirmed v685 command. | E1 checked-in config fact; may be stale |
| Production runner/version/commit | Not observable from repository files alone. | NOT VERIFIED |
| Order environment | Logs show `DRY_RUN=False` and `--live=OFF`; actual running account/environment was not independently checked. | NOT VERIFIED as deployed environment |

## MC consumer path

The inspected v685 source loads the daily bundle and, when available, the weekly bundle. It logs the bundle filenames and per-pair P(up). The entry path passes per-pair MC probability into direction/scoring, includes MC among the direction voters, and applies probability-zone checks. Profile 2 blends weekly and daily inputs; other profiles use daily MC only in the inspected code.

This confirms behavior in the local source and corroborating log records, not that the same source commit was running on a production server.

