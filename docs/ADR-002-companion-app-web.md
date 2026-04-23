# ADR-002: Companion App as Web App

**Date**: 2026-04-23
**Status**: Accepted

## Decision
Build companion app as React/Vite web app, not a native Android app.

## Why
Ground station is a monitor connected via wireless HDMI to the DJI RC Pro controller. RC Pro runs Android with a browser. A web app runs in that browser with zero installation, displays on the external monitor via HDMI mirror, and works on any device (laptop, tablet, phone) as fallback. Native Android app would require APK sideloading on the RC Pro and rebuilds for every update.

## Consequences
- No access to native Android APIs (GPS, sensors) — not needed since drone provides all location data
- Requires a local server running on operator's laptop OR hosted endpoint
- Phase 2: companion app receives Manifold 3 data via WebSocket over 4G link
