![Version](https://img.shields.io/github/v/release/jrhubott/adaptive-cover-pro?style=for-the-badge)
![Tests](https://img.shields.io/github/actions/workflow/status/jrhubott/adaptive-cover-pro/tests.yml?branch=main&label=Tests&style=for-the-badge)
![Hassfest](https://img.shields.io/github/actions/workflow/status/jrhubott/adaptive-cover-pro/hassfest.yml?branch=main&label=Hassfest&style=for-the-badge)
![HACS](https://img.shields.io/github/actions/workflow/status/jrhubott/adaptive-cover-pro/hacs.yaml?branch=main&label=HACS&style=for-the-badge)
![Coverage](https://img.shields.io/codecov/c/github/jrhubott/adaptive-cover-pro?style=for-the-badge)

![Adaptive Cover Pro](https://raw.githubusercontent.com/jrhubott/adaptive-cover-pro/main/images/dark_logo.png)

# Adaptive Cover Pro

Sun-tracking cover automation with an inspectable decision pipeline, full venetian sequencing, glare zones, and a seasonal climate arbiter — for Home Assistant.

> Full documentation lives on the [Wiki](https://github.com/jrhubott/adaptive-cover-pro/wiki).

---

## What it does

- **Four cover types with full geometric modeling** — vertical blinds, horizontal awnings, tilt-only blinds, and venetian blinds; each uses real window and facade geometry, not rules of thumb.
- **Inspectable decision pipeline** — 10 handlers run in priority order (safety, weather, manual, climate, glare, solar) and each reports its reason. A `decision_trace` sensor shows exactly why the cover is at 45% — no black boxes.
- **Venetian blinds done properly** — dual-axis sequencer waits for the carriage to settle before sending tilt, handles back-rotation across a 45-second post-settle window, and pre-positions tilt on opening to eliminate flicker. Covers KNX, Shelly, and Somfy IO buses.
- **Climate mode with a full seasonal arbiter** — winter heating, winter insulation, summer cooling, and glare comfort each have independent logic; presence, lux, irradiance, and cloud cover are all suppression inputs.
- **Glare zones** — name the floor areas you want protected (TV, dining table); the cover deploys further than pure sun tracking when a protected zone would receive direct sun.
- **15 runtime services** — every parameter is scriptable from automations; no UI interaction needed to change mode, position limits, or overrides at runtime.

More detail: **[How It Decides](https://github.com/jrhubott/adaptive-cover-pro/wiki/How-It-Decides)** · **[Climate Mode](https://github.com/jrhubott/adaptive-cover-pro/wiki/Climate-Mode)** · **[Enhanced Geometric Accuracy](https://github.com/jrhubott/adaptive-cover-pro/wiki/Enhanced-Geometric-Accuracy)**

## Companion Lovelace card

The **[Adaptive Cover Pro Card](https://github.com/jrhubott/adaptive-cover-pro-card)** turns the integration's sensors into a dashboard you can read at a glance. It's HACS-installable and ships three cards in one bundle.

**Sky compass** — watch the sun cross each window in real time: its arc through the field of view, the shaded wedge of the cover closing to track it, sunrise and sunset, and the day's elevation curve underneath.

<img src="https://raw.githubusercontent.com/jrhubott/adaptive-cover-pro-card/main/images/sky-compass-timelapse.gif" alt="Sky compass tracking the sun across a full day" width="540">

**Tile card** — one compact row per shade: icon, live position, `↑ ■ ▼` controls, and a badge that tells you which automation is driving the cover right now (Auto, Solar tracking, a Manual override with its expiry and a resume button, Motion, and more). Tap any tile for the full pipeline trace, today's forecast, the compass, and override controls.

<img src="https://raw.githubusercontent.com/jrhubott/adaptive-cover-pro-card/main/images/tile-gallery.png" alt="Tile card across four automation states" width="440">

**Full card** — everything in one place: the compass, the elevation chart, the pipeline decision strip with the winning handler highlighted, per-cover position bars, and override controls.

<img src="https://raw.githubusercontent.com/jrhubott/adaptive-cover-pro-card/main/images/card-preview.png" alt="Adaptive Cover Pro Card — all sections" width="340">

Setup and options: **[Lovelace Card](https://github.com/jrhubott/adaptive-cover-pro/wiki/Lovelace-Card)** · **[Sky Compass Card](https://github.com/jrhubott/adaptive-cover-pro/wiki/Sky-Compass-Card)**.

---

## Quick install

**HACS (recommended):** In HACS, search **Adaptive Cover Pro**, download, restart Home Assistant, then add the integration.

**Manual:** Copy `custom_components/adaptive_cover_pro/` into `config/custom_components/`, restart Home Assistant, and add the integration.

Full steps: **[Installation](https://github.com/jrhubott/adaptive-cover-pro/wiki/Installation)** · **[First-Time Setup](https://github.com/jrhubott/adaptive-cover-pro/wiki/First-Time-Setup)**

## Documentation

|                            |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 🚀 **Getting started**     | [Installation](https://github.com/jrhubott/adaptive-cover-pro/wiki/Installation) · [First-Time Setup](https://github.com/jrhubott/adaptive-cover-pro/wiki/First-Time-Setup) · [Cover Types](https://github.com/jrhubott/adaptive-cover-pro/wiki/Cover-Types) · [Migrating from Adaptive Cover](https://github.com/jrhubott/adaptive-cover-pro/wiki/Migrating-from-Adaptive-Cover)                                                                                                              |
| 🧠 **How it works**        | [How It Decides](https://github.com/jrhubott/adaptive-cover-pro/wiki/How-It-Decides) · [Basic Mode](https://github.com/jrhubott/adaptive-cover-pro/wiki/Basic-Mode) · [Climate Mode](https://github.com/jrhubott/adaptive-cover-pro/wiki/Climate-Mode) · [Enhanced Geometric Accuracy](https://github.com/jrhubott/adaptive-cover-pro/wiki/Enhanced-Geometric-Accuracy)                                                                                                                        |
| 🎨 **Dashboard**           | [Lovelace Card](https://github.com/jrhubott/adaptive-cover-pro/wiki/Lovelace-Card) — install, configure, and use the companion card that visualizes the full pipeline                                                                                                                                                                                                                                                                                                                          |
| ⚙️ **Configuration**       | [Sun Tracking](https://github.com/jrhubott/adaptive-cover-pro/wiki/Configuration-Sun-Tracking) · [Glare Zones](https://github.com/jrhubott/adaptive-cover-pro/wiki/Configuration-Glare-Zones) · [Weather Safety](https://github.com/jrhubott/adaptive-cover-pro/wiki/Configuration-Weather-Safety) · [Climate](https://github.com/jrhubott/adaptive-cover-pro/wiki/Configuration-Climate) · [Summary Screen](https://github.com/jrhubott/adaptive-cover-pro/wiki/Configuration-Summary-Screen) |
| 🔌 **Entities & services** | [Entities](https://github.com/jrhubott/adaptive-cover-pro/wiki/Entities) · [Runtime Configuration Services](https://github.com/jrhubott/adaptive-cover-pro/wiki/Runtime-Configuration-Services) · [Position Verification](https://github.com/jrhubott/adaptive-cover-pro/wiki/Position-Verification) · [Somfy RTS (My Position)](https://github.com/jrhubott/adaptive-cover-pro/wiki/My-Position-Support-Somfy-RTS)                                                                            |
| 🛠️ **Operations**          | [Troubleshooting](https://github.com/jrhubott/adaptive-cover-pro/wiki/Troubleshooting) (incl. [stopping false manual overrides](https://github.com/jrhubott/adaptive-cover-pro/wiki/Troubleshooting#workaround--stop-unexpected-manual-overrides-entirely)) · [Known Limitations](https://github.com/jrhubott/adaptive-cover-pro/wiki/Known-Limitations)                                                                                                                                       |

## Support

If Adaptive Cover Pro has been useful, you can support the project:

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/jrhubott)

---

## kamahat patches (this fork — `kamahat:main` and `kamahat:personal/main`)

This fork tracks **jrhubott/adaptive-cover-pro** `main`. The `personal/main` branch adds two extra features on top of the 12 upstream-targeted patches.

### Patches common to both `main` and `personal/main`

| # | Commit | What |
|---|--------|------|
| 1 | `7e1ca8a` | fix(migrations): write idempotency flag before entity removal |
| 2 | `f1c8efe` | fix(sun): replace assert type guards with explicit RuntimeError |
| 3 | `3b29a01` | perf(cover): change-gate proxy cover `async_write_ha_state` calls |
| 4 | `9b44e8e` | fix(coordinator): guard `sun.sun` unavailability in `get_blind_data` |
| 5 | `859fb14` | perf(geometry): add `lru_cache` to pure safety-margin functions |
| 6 | `17425f3` | perf: add `UpdateFingerprint` for coordinator pipeline short-circuit |
| 7 | `0aa8afa` | perf(3.4): extend `UpdateFingerprint` to cover ALL pipeline inputs via MD5 |
| 8 | `c6e7609` | fix(3.4): correct `ClimateReadings` field name in fingerprint |
| 9 | `52ef390` | feat(3.4): add `any_command_grace_active` to `GracePeriodManager` |
| 10 | `9caa3a6` | perf(3.3): add `SunGeometryCache` with per-minute TTL for coordinator batching |
| 11 | `125c709` | perf(3.4): wire `UpdateFingerprint` short-circuit into `coordinator._async_update_data` |
| 12 | `da4a6d3` | fix: remove `zip_release` to fix HACS double-nested install path |

### Extra features on `personal/main` only

| Commit | What |
|--------|------|
| `78c75c9` | feat: add `SecurityHandler` (priority 95) and `hub/` subpackage |

#### SecurityHandler

`pipeline/handlers/security.py` — a new pipeline handler at **priority 95** (between `ForceOverrideHandler` at 100 and `WeatherOverrideHandler` at 90).

When a presence/occupancy sensor is configured and reports `off` (no one home), closes all covers to the configured security position (default 0%). **Fail-safe**: unavailable or unknown sensor state is treated as "present" — covers are never accidentally closed by a flapping sensor.

#### hub/ subpackage

`custom_components/adaptive_cover_pro/hub/` — a subpackage for hub/group cover management:

```
hub/
  __init__.py
  config.py    # hub configuration helpers
  cover.py     # hub cover entity
  scene.py     # scene support
  select.py    # select entity for hub
  switch.py    # switch entity for hub
```

### Installation (HACS — `personal/main` is the HACS branch)

1. In HACS, add this repository as a custom repository: `kamahat/adaptive-cover-pro`
2. Select **Integration**, install, restart Home Assistant
3. Add the integration from Settings > Integrations

### Code structure

```
custom_components/adaptive_cover_pro/
  coordinator.py          # orchestrator; _async_update_data uses UpdateFingerprint
  pipeline/
    handlers/             # 10 upstream handlers + SecurityHandler (priority 95)
    fingerprint.py        # UpdateFingerprint -- MD5 hash of all pipeline inputs
  managers/
    grace_period.py       # any_command_grace_active property
    cover_command/
  engine/
    sun_geometry.py       # SunGeometryCache -- per-minute TTL memoisation
  hub/                    # hub/group cover subpackage (personal/main only)
```

### Release runbook

1. `git fetch upstream && git checkout personal/main && git rebase main` — keep personal/main on top of latest main
2. Update version in `manifest.json`
3. `git tag v<VERSION>-personal && git push origin personal/main --tags`

### Syncing upstream

```bash
git fetch upstream
git checkout main
git rebase upstream/main
git push origin main --force-with-lease
git checkout personal/main
git rebase main
git push origin personal/main --force-with-lease
```

---

<details>
<summary>Francais / French</summary>

## Patches kamahat

La branche `personal/main` est la branche HACS. Elle contient les 12 correctifs de `main` plus :

### SecurityHandler

`pipeline/handlers/security.py` — handler de pipeline a **priorite 95** (entre `ForceOverrideHandler` a 100 et `WeatherOverrideHandler` a 90).

Quand un capteur de presence est configure et signale `off` (personne a la maison), ferme tous les volets a la position de securite configuree (defaut 0%). **Fail-safe** : un etat indisponible ou inconnu du capteur est traite comme "present" — les volets ne se ferment jamais a cause d'un capteur defaillant.

### Sous-paquet hub/

`custom_components/adaptive_cover_pro/hub/` — gestion des volets en groupe (hub).

### Installation HACS

1. Dans HACS, ajouter le depot personnalise : `kamahat/adaptive-cover-pro`
2. Selectionner Integration, installer, redemarrer Home Assistant
3. Ajouter l'integration depuis Parametres > Integrations

### Runbook release

1. `git fetch upstream && git checkout personal/main && git rebase main`
2. Mettre a jour la version dans `manifest.json`
3. `git tag v<VERSION>-personal && git push origin personal/main --tags`

</details>
