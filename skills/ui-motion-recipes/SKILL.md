---
name: ui-motion-recipes
description: Curated frontend motion and visual-effects system for polished web interfaces. Contains the complete transitions.dev decision rules and 27 production-ready recipes, motion-token polish and refinement guidance, and integration references for thinking-orbs, metal-fx, img-fx, and border-beam. Use for component transitions, animation audits, motion refinement, AI activity indicators, image-generation reveals, animated borders, and high-emphasis React effects.
---

# UI Motion Recipes

Use this file as the index and decision layer for the bundled motion knowledge. Read the user's request and the existing frontend, select the most relevant reference, read that file completely, and then follow its instructions.

## Operating procedure

1. Inspect the relevant component and styles before choosing an effect. Identify the framework, styling system, package manager, theme implementation, existing motion tokens, interaction states, and accessibility requirements.
2. Classify the request:
   - Add or replace a familiar interface transition: use the transitions.dev catalog and one numbered recipe.
   - Audit or improve motion that already exists: use the transition-polish instructions.
   - Add a specialized React visual effect: use one package reference.
3. Read the selected reference completely. Do not reconstruct a recipe from the short description in this index.
4. Match by interaction intent and component role, not by the nearest duration, easing, or visual resemblance.
5. Prefer the smallest effect that communicates the state change. Do not add a runtime package when a focused CSS recipe solves the interaction.
6. For implementation requests, integrate the selected recipe or package into the existing architecture and run relevant validation. For review requests, report findings without editing.
7. Preserve semantic behavior, keyboard and focus interaction, reduced-motion handling, theming, responsive layout, SSR constraints, and the project's established design language.

## Core instruction files

### Transitions catalog and rules

Read [transitions-catalog-and-rules.md](references/transitions-dev/transitions-catalog-and-rules.md) before selecting or installing a transitions.dev recipe. This is the repository owner's complete original `transitions-dev` skill prompt. It contains:

- interaction-first decision rules;
- `transitions reveal`, `review`, `apply`, and `refine` behavior;
- duration, easing, distance, scale, and blur tokens;
- universal CSS installation guidance;
- the required five-step recipe output format;
- JavaScript orchestration requirements;
- reduced-motion requirements;
- common implementation mistakes;
- links to every numbered recipe.

After reading it, read exactly the numbered recipe that matches the requested interaction.

### Transition polish

Read [transition-polish.md](references/transitions-polish/transition-polish.md) when motion already exists and needs to feel more intentional or consistent. This is the repository owner's complete original `transitions-polish/SKILL.md`, renamed so it remains a reference within this single skill. It covers:

- usage-based token selection rather than nearest-number replacement;
- open versus close asymmetry;
- hover-in versus hover-out behavior;
- stagger totals and intent delays;
- duration, easing, distance, scale, and blur decisions;
- read-only motion reviews and focused polish edits.

### Refine UI rules

Read [refine-ui-rules.md](references/transitions-polish/refine-ui-rules.md) for the compact version of the polish rules used by the transitions.dev Refine panel's Small refinement flow. Use it for a narrow, per-transition refinement when the full project-scale polish workflow is unnecessary.

### Shared token stylesheets

- `references/transitions-dev/_root.css` contains the full shared motion scale and semantic variables for the 27 transition recipes.
- `references/transitions-polish/_root.css` contains the smaller token set used by the polish workflow.

Install a root stylesheet only when shared tokens are useful. Do not duplicate variables already present in the project.

## Transition recipe catalog

All recipes are stored in `references/transitions-dev/`. Read the catalog-and-rules file first, then the selected recipe.

| # | Recipe | Use it for | Reference |
|---|---|---|---|
| 01 | Card resize | Tweening a container when width or height changes | [01-card-resize.md](references/transitions-dev/01-card-resize.md) |
| 02 | Number pop-in | Re-entering digits with a blurred slide after a number update | [02-number-pop-in.md](references/transitions-dev/02-number-pop-in.md) |
| 03 | Notification badge | Sliding a badge onto a trigger and popping its dot | [03-notification-badge.md](references/transitions-dev/03-notification-badge.md) |
| 04 | Text states swap | Replacing text in place with blur and directional motion | [04-text-states-swap.md](references/transitions-dev/04-text-states-swap.md) |
| 05 | Menu dropdown | Opening an anchored, origin-aware dropdown from a trigger | [05-menu-dropdown.md](references/transitions-dev/05-menu-dropdown.md) |
| 06 | Modal | Opening and closing a centered modal with asymmetric scale motion | [06-modal.md](references/transitions-dev/06-modal.md) |
| 07 | Panel reveal | Sliding a panel into a page region with cross-blur | [07-panel-reveal.md](references/transitions-dev/07-panel-reveal.md) |
| 08 | Page side-by-side | Moving between adjacent list/detail or step views | [08-page-side-by-side.md](references/transitions-dev/08-page-side-by-side.md) |
| 09 | Icon swap | Cross-fading two icons in one slot with blur and scale | [09-icon-swap.md](references/transitions-dev/09-icon-swap.md) |
| 10 | Success check | Celebrating completion with icon motion and SVG stroke draw | [10-success-check.md](references/transitions-dev/10-success-check.md) |
| 11 | Avatar group hover | Applying distance-falloff lift and spring return to item rows | [11-avatar-group-hover.md](references/transitions-dev/11-avatar-group-hover.md) |
| 12 | Error state shake | Showing replayable validation feedback and an input shake | [12-error-state-shake.md](references/transitions-dev/12-error-state-shake.md) |
| 13 | Input clear dissolve | Clearing text with fly-out and per-word streak motion | [13-input-clear-dissolve.md](references/transitions-dev/13-input-clear-dissolve.md) |
| 14 | Skeleton reveal | Pulsing a placeholder and revealing loaded content | [14-skeleton-reveal.md](references/transitions-dev/14-skeleton-reveal.md) |
| 15 | Shimmer text | Showing a pure-CSS progress or thinking highlight sweep | [15-shimmer-text.md](references/transitions-dev/15-shimmer-text.md) |
| 16 | Tabs sliding | Moving an active pill through a segmented control | [16-tabs-sliding.md](references/transitions-dev/16-tabs-sliding.md) |
| 17 | Tooltip | Delaying entrance while keeping dismissal immediate | [17-tooltip.md](references/transitions-dev/17-tooltip.md) |
| 18 | Texts reveal | Staggering stacked copy with blurred upward motion | [18-texts-reveal.md](references/transitions-dev/18-texts-reveal.md) |
| 19 | Card tilt | Tilting a card toward the pointer with optional glare | [19-card-tilt.md](references/transitions-dev/19-card-tilt.md) |
| 20 | Plus-to-menu morph | Morphing a circular trigger into the surface it opens | [20-plus-menu-morph.md](references/transitions-dev/20-plus-menu-morph.md) |
| 21 | Accordion | Expanding and collapsing content with grid rows and chevron motion | [21-accordion.md](references/transitions-dev/21-accordion.md) |
| 22 | Toast | Raising a toast with a slower entrance and faster exit | [22-toast.md](references/transitions-dev/22-toast.md) |
| 23 | Like button | Filling a heart with a pop and particle burst | [23-like-button.md](references/transitions-dev/23-like-button.md) |
| 24 | Learn-more hover | Extending a chevron into an arrow on hover | [24-learn-more-hover.md](references/transitions-dev/24-learn-more-hover.md) |
| 25 | Checkbox check | Filling a checkbox and drawing its checkmark stroke | [25-checkbox-check.md](references/transitions-dev/25-checkbox-check.md) |
| 26 | Spinning counter | Moving digit reels with slot-machine motion blur | [26-spinning-counter.md](references/transitions-dev/26-spinning-counter.md) |
| 27 | Toggle | Moving a switch thumb with a double-bounce overshoot | [27-toggle.md](references/transitions-dev/27-toggle.md) |

If no recipe clearly matches, do not force one. Explain the mismatch and design a restrained project-native transition instead.

## Specialized React effect libraries

Read both the named package guide and its adjacent `package.json` before installing or using a library. The package guide is a local snapshot of the repository owner's documentation, including public APIs, props, accessibility behavior, performance notes, and integration constraints.

### thinking-orbs

Use [thinking-orbs.md](references/thinking-orbs/thinking-orbs.md) for meaningful AI or agent activity states: `working`, `searching`, `solving`, `listening`, `composing`, and `shaping`.

- React 18+ component rendered with plain 2D canvas.
- Provides separately tuned 20px inline and 64px avatar-size designs.
- Automatically follows host theme conventions and system color scheme.
- Provides accessible labels, static reduced-motion frames, offscreen pausing, and a shared animation clock.
- Prefer it when users benefit from seeing what an AI system is doing; do not use it as unrelated decoration.

Package metadata: `references/thinking-orbs/package.json`.

### metal-fx

Use [metal-fx.md](references/metal-fx/metal-fx.md) for a high-emphasis liquid-metal ring around a button, chip, or icon.

- React 18+ WebGL wrapper with button and circular variants.
- Provides chromatic, silver, and gold presets, theme handling, intensity control, pausing, and optional neighboring reflections.
- Reuses one WebGL context and animation loop across mounted instances and handles SSR after hydration.
- Reserve it for a small number of premium or primary surfaces. Do not use it for ordinary navigation or routine controls.

Package metadata: `references/metal-fx/package.json`.

### img-fx

Use [img-fx.md](references/img-fx/img-fx.md) for AI image-generation cards, shader-driven loading mosaics, and staged image reveals.

- React 18+ component with `three` as a peer dependency.
- Provides organic pixels, mechanical pixels, and diagonal sweep presets.
- Supports image pools, automatic cycles, imperative manual reveal, themes, strength, pixel scale, palette overrides, and lifecycle callbacks.
- Use it when generation or image materialization is part of the product state, not as a generic page loader.

Package metadata: `references/img-fx/package.json`.

### border-beam

Use [border-beam.md](references/border-beam/border-beam.md) for a traveling or breathing border glow around cards, buttons, inputs, or search bars.

- React 18+ wrapper with rotating `sm`, `md`, and `line` beams plus inner and outer pulse variants.
- Provides colorful, monochrome, ocean, and sunset palettes with theme, strength, duration, and activation controls.
- Auto-detects the wrapped child's radius.
- Check the documented opaque-background, existing-border, overflow, and layout requirements before using `pulse-outside`.
- Use it for focused attention or active-state emphasis; avoid placing animated beams around many simultaneous elements.

Package metadata: `references/border-beam/package.json`.

## Choosing between recipes and packages

- Choose a numbered transitions.dev recipe for dropdowns, modals, panels, tabs, tooltips, accordions, form feedback, content swaps, navigation changes, and most interaction motion.
- Choose transition polish when the correct interaction already exists but its timing, easing, distance, scale, blur, stagger, or open/close relationship feels wrong.
- Choose thinking-orbs when communicating a semantic AI activity state.
- Choose img-fx when an image is actively generating, loading through a shader state, or materializing into view.
- Choose metal-fx for a deliberately premium primary action or icon treatment.
- Choose border-beam for a focused animated edge or active-card treatment.
- Prefer one primary visual idea per component. Combine effects only when their roles are distinct and the user explicitly wants a layered design.

## Installation and implementation

- Detect the package manager from the project's lockfile and use it consistently.
- Install only the package selected for the task. Add `three` with `img-fx` when the peer dependency is absent.
- Use the public APIs documented in the bundled package references; do not invent props.
- Do not install a React package in a non-React project. Use a CSS recipe or implement an equivalent native effect.
- Preserve the project's current component abstraction, styling method, tokens, and theme source.
- Avoid animating expensive layout and paint properties when transform or opacity communicates the same change.
- Keep continuous WebGL and glow effects bounded, pauseable, and purposeful.
- Verify entrance, exit, replay, keyboard, focus, light/dark theme, responsive, and reduced-motion states relevant to the chosen effect.

## Source provenance

The transition catalog, recipes, polish instructions, and refine rules are local snapshots of [Jakubantalik/transitions.dev](https://github.com/Jakubantalik/transitions.dev). Package guides, metadata, and licenses are local snapshots of the corresponding Jakubantalik repositories. Preserve their license files and attribution.
