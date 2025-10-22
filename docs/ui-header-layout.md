# Web UI: Hex Node Header Layout and Tuning

This document explains the recent visual changes to the hex node headers in the LiteGraph-based UI and how to tune them.

## What Changed

- Icon moved higher and aligned to a top-aligned header band.
- Title and detail text sizes reduced and use dynamic scaling based on node radius.
- Vertical spacing tightened between icon, title, and details.
- A subtle translucent contrast band was added at the top to improve legibility on patterned backgrounds.

See CHANGELOG entry [1.1.1] for a summary.

## Where to Edit

File: `campfirevalley/web/static/js/campfire-nodes.js`

Look for `HexNodeBaseMixin` and its `onDrawBackground` and `onDrawForeground` methods. The header layout is driven by these variables near the start of each method:

- `paddingTop`: top padding for the header band
- `iconSizeTop`: icon size used in the header
- `iconYTop`: icon top Y position (usually derived from `centerY - radius + paddingTop`)
- `titleGap`: space between icon bottom and title
- `titleFontSize`: font size for the title (scaled from radius)
- `propFontSize`: font size for detail rows (scaled from radius)

The text baseline for the emoji fallback and title uses `ctx.textBaseline = "top"` so values represent top-aligned y-coordinates.

## Example: Tighten Header Further

```
// onDrawForeground header metrics (example values)
const paddingTop = Math.max(4, Math.round(radius * 0.06));
const iconSizeTop = Math.round(radius * 0.72);
const iconYTop = Math.round(centerY - radius + paddingTop);
const titleGap = Math.round(radius * 0.06);
const titleFontSize = Math.max(10, Math.round(radius * 0.14));
const propFontSize = Math.max(9, Math.round(radius * 0.11));
```

- Increase `paddingTop` to push content downward; decrease to move it up.
- Increase `iconSizeTop` to enlarge the icon; decrease to shrink it.
- Increase `titleFontSize` or `propFontSize` to make text larger; decrease to make it more compact.

## Contrast Band (Legibility Aid)

A short block draws a semi-transparent rectangle across the top of the hex before the foreground elements:

- Adjust opacity by changing the alpha in `ctx.fillStyle = "rgba(0,0,0,0.15)"` (e.g., `0.10` is lighter, `0.20` is darker).
- Disable by removing or commenting the block or setting alpha to `0`.

## Previewing Your Changes

1. Rebuild the UI image:
   
   ```bash
   docker-compose build campfire-valley
   ```
2. Restart services:
   
   ```bash
   docker-compose up -d
   ```
3. Open the UI at `http://localhost:8000` and refresh.

Tip: If hot reload is enabled for static assets in your setup, a full rebuild may not be necessary. When in doubt, rebuild to ensure changes are served.