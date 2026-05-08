# ADR-001: Two-Sortie MVP Before Manifold 3

**Date**: 2026-04-23
**Status**: Accepted

## Decision
Build Phase 1 as a two-sortie system with ground processing between passes. Manifold 3 onboard integration is Phase 2.

## Why
Manifold 3 not yet purchased. Two-sortie MVP proves the adaptive mission concept, generates real-world detection data, and creates a paying service before hardware investment. Architecture is designed so Manifold 3 slots in as an execution mode swap, not a rewrite.

## Consequences
- Landing between passes means animals may disperse (acceptable for MVP validation)
- Operator runs processing script on laptop between sorties (~3-5 min)
- Phase 2 upgrade path: blob_detector and obstacle_mapper run onboard via PSDK, companion app receives data via 4G instead of local
