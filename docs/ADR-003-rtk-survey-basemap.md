# ADR-003: RTK-Anchored Survey Basemap (Two-Pass M4E Setup)

**Date**: 2026-05-30
**Status**: Accepted

## Context
The census report needs animals plotted on a 1–5 cm accurate map of the actual
property, so each detection sits against the real habitat it was found in (food
plots, tree lines, water, bedding cover). Today the M4E setup flight is scoped
only as The Outer Guard: it flies one Smart Oblique pass and the system mines it
for hazards (Cowans), discarding the rest. There is no map deliverable, and
thermal detections use the drone's capture position rather than a terrain-
projected ground coordinate, which drifts on rolling ground.

Two accuracy numbers are in play and only one was solved:
- **GSD (resolution)** — easy at M4E altitudes (~2–3 cm/px at 60–70 m AGL).
- **Absolute position** — requires an RTK fix; without it the whole map can sit
  meters off true and the M4T detections (a separate flight) will not align.

## Decision
The M4E setup flight becomes **two stacked passes flown once per property**
(cached ~6 months), both on RTK:

| Pass | Gimbal | Template | Output |
|------|--------|----------|--------|
| Nadir map | −90° | `mapping2d`, ~80/70 overlap | Orthomosaic + DSM — the report basemap (NEW) |
| Oblique | −20° | `quickOrthoMappingEnable=1` | Vertical hazards → Cowan map (existing Outer Guard) |

- The **orthomosaic + DSM become a first-class deliverable**, persisted to
  `data/properties/{id}/` alongside `cowans.json`, built from the nadir imagery
  via WebODM/NodeODM (or DJI Terra).
- **Thermal detections are DSM-projected** to ground coordinates (promotes the
  Phase 2 "DEM-projected ground GPS" item) and plotted onto the ortho basemap in
  the companion app and the report.
- **RTK corrections** come from Point One Nav's free NTRIP network
  (`truertk.pointonenav.com:2101`, mount point **ITRF2014**), entered directly in
  DJI Pilot 2's Network RTK client. No external GNSS receiver required for the
  drone. Both the M4E setup and the M4T patrol fly FIXED.
- **RTK FIXED is a new pre-flight gate** — added to the operator checklist and
  surfaced as a companion-app pre-flight banner. A flight without FIXED forfeits
  the cm claim.

## Why
- The M4E imagery to build a survey-grade ortho is already being collected; this
  promotes a byproduct into the deliverable instead of adding a flight type.
- Nadir gives a crisp top-down basemap; oblique still catches the vertical
  hazards (towers, guy wires) that nadir misses. The two goals genuinely pull in
  different directions, so they get their own passes.
- The basemap is a once-per-property asset (habitat barely moves), which matches
  the existing 6-month Outer Guard cache cadence — same flight, same cadence.
- Point One closes the absolute-accuracy gap for free, making the 1–5 cm claim
  real end to end rather than "high-res but meters off."

## Consequences
- **Positive:** Detections plot on the right tree; defensible cm-accurate
  deliverable; no new subscription; offline ground-processing design (ADR-001
  lineage) preserved.
- **Negative:** Longer M4E flight time per property (two passes); ortho/DSM build
  adds a processing step (WebODM/NodeODM/Terra); `scout_kmz_generator.py` must
  emit two waylines instead of one.
- **Risks:**
  - **Datum mismatch.** Point One feeds **ITRF2014**; NAIP/USGS 3DEP/county
    parcels are **NAD83(2011)** (~1 m apart in coastal VA). Self-flown layers
    agree with each other, but any external geodata needs an
    ITRF2014→NAD83(2011) transform in the projection module.
  - **No RTK link in the field** → silently drops to non-FIXED; the pre-flight
    banner exists to make that visible.

## Alternatives considered
1. **Single oblique pass, reuse for basemap** — simplest, one flight, but a
   softer nadir map. Rejected for the report deliverable; acceptable only as a
   fallback.
2. **Bootstrap from free data (NAIP + USGS 3DEP)** — unblocks plotting with no
   new flight; lower res/currency and forces the datum transform immediately.
   Retained as the MVP starting point before the self-flown ortho exists.
3. **DJI FlightHub 2 as the orchestration backbone** — rejected for now. FH2 does
   not do thermal detection or adaptive routing (that stays in the local
   pipeline), is cloud-dependent against rural dawn connectivity (cuts against
   ADR-001's offline design), is a paid subscription, and its live map is
   situational-awareness grade, not survey grade. Revisit FH2 later only as an
   optional route-sync / hazard-annotation layer if SD-card sideloading becomes a
   field annoyance.

## References
- `docs/ADR-001` — two-sortie / no-land MVP lineage
- `projects/herd-mapper/dji-feature-utilization-audit.md` (vault) — M4E/M4T
  mission split, Phase 2 "DEM-projected ground GPS" item this promotes
- `core/scout_kmz_generator.py`, `core/scout_processor.py` — implementation
  surface (two-wayline emit, ortho/DSM persistence) for a later build session
