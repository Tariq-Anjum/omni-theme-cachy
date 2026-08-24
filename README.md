# omni-theme-cachy

An Omarchy-inspired theming environment for Cachy OS (KDE Plasma 6).

## Goal

Provide a deterministic, reproducible theme engine that can apply a single semantic theme across KDE Plasma, apps, terminals, editors, and supporting tools on Cachy OS.

## Core Ideas

- **Semantic theme model**: TOML-based theme files capturing palettes, surfaces, roles, and states.
- **Surfaces & roles**: A `surfaces` model that maps UI areas (panels, popups, controls) to theme colors and behaviors.
- **User overlays & templates**: Omarchy-style user overrides and templates layered on top of the base theme for safe customization.
- **Renderer & staging**: A renderer that turns themes into Plasma styles, wallpapers, and app configs, with a staging pipeline for safe preview.
- **CLI & doctor**: An `omni` CLI with commands for applying, previewing, diagnosing, and exporting theme state.

## Roadmap (9 Sessions)

This project is being implemented in 9 sessions:

1. **Session 01 – Foundation & Research**
   - Define constraints for Cachy OS, KDE Plasma 6, and Omarchy.
   - Decide repo layout, language choices, and minimal runtime dependencies.

2. **Session 02 – Theme Model & Color Engine**
   - Design TOML theme schema (palettes, surfaces, roles).
   - Implement color engine and validation.

3. **Session 03 – Template Renderer & Staging**
   - Build renderer for Plasma style, wallpapers, and app configs.
   - Implement staging pipeline for safe, reversible theme application.

4. **Session 04 – Plasma Integration**
   - Connect renderer outputs to KDE Plasma 6 (look-and-feel, colors, icons, wallpapers).
   - Respect Plasma boundaries and user settings.

5. **Session 05 – Wallpaper & Visuals**
   - Integrate wallpaper generation/selection consistent with theme surfaces.
   - Provide presets and hooks for custom artwork.

6. **Session 06 – Application Adapters**
   - Adapters for VS Code, terminals, GTK, Qt apps, and browsers.
   - Focus on consistent semantic mapping across toolchain.

7. **Session 07 – CLI, Doctor & Preview**
   - `omni` CLI with commands for apply/preview/export.
   - "Doctor" diagnostics to spot broken themes, missing surfaces, or unsafe overrides.

8. **Session 08 – Security, Testing & QA**
   - Path safety, overlay traversal checks, and idempotent operations.
   - Automated tests around theme validation, staging, and rollback.

9. **Session 09 – Documentation, Packaging & Release**
   - User docs, operator docs, and agent-friendly implementation notes.
   - Packaging for Cachy OS (and other distros later) and final release flow.

## Status

The public repo currently hosts the license and this high-level README. Session specs and implementation code will be committed incrementally as the engine takes shape.

## Contributing

This project is still early-stage. Once the initial theme model and CLI skeleton are committed, contributions around adapters (VS Code, terminal, GTK/Qt) and QA tooling will be very welcome.
