# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- (none)

### Changed
- (none)

### Fixed
- (none)

## [1.2.2] - 2026-04-13
### Added
- Web UI: searchable/clickable Valley snapshot picker with delete support
- Web UI: markdown rendering for chat responses (lists, code blocks, links)
- Web UI: radial auto-arrange (Valley → Campfires → Campers) using hex-terminal anchors
- Web UI: nearest-terminal connection routing for campfire ↔ camper links
- Auditor: natural language workflow reordering (“move X to first step …”)
- API: `POST /api/auditors/cleanup` to remove legacy `* Auditor` backend campfires
- Chat: ⏹️ Stop Audio button to interrupt browser text-to-speech
- Workflow: final report enforcement with “Role Contributions” appendix for synthesis verification

### Changed
- API: `/api/valley/snapshots` returns snapshot metadata (name/mtime/size) sorted newest-first
- API: `/api/valley/details` separates backend campfires vs backend campers
- API: `/api/campfires` hides legacy `* Auditor` by default (opt-in via `include_auditors=true`)
- Auditor: status/settings questions answer deterministically without mutating team state
- Snapshot load: rebuilds camper→campfire mapping from saved graph
- Discord bot: final responses post as new messages with chunking + full-report attachment
- Discord bot: waits for workflow payload on reply channel (ignores non-workflow messages)

### Fixed
- Auditor: `self audit` reliability for time windows and correlation-id audits
- Workflow persistence: prevents workflow state from being incorrectly treated as missing when graph links are absent
- Workflow: ensures the Discord reply is only published once the workflow finishes (no intermediate step response publishing)

## [1.2.0] - 2025-10-22
- No functional/code changes since 1.1.1.
- Housekeeping: align versions to 1.2.0 across project, runtime, and Docker tags.

## [1.2.1] - 2026-03-26
### Added
- Gateway CLI onboarding (`campfirevalley onboard`) and PID-tracked daemon helpers (`campfirevalley daemon run|status`)
- Voice ingestion endpoint (`POST /api/voice/ingest`) with admin token gating
- Local Parakeet STT fallback for audio transcription (`audio_base64` / `audio_url`)

## [1.1.1] - 2025-10-22

### Changed
- Web UI: Hex node header layout tightened for clarity and space efficiency
  - Moved header icon higher in the hex and aligned to top baseline
  - Reduced title and detail font sizes for improved stacking density
  - Tightened vertical spacing (`paddingTop`, `titleGap`) for compact headers
  - Synced emoji fallback and title to `textBaseline = "top"` for consistent alignment
- Typography: Switched to dynamic font sizing derived from node radius for readability at all scales

### Added
- Subtle translucent contrast band at the top of each hex node to improve text legibility on busy backgrounds

### Developer Notes
- Primary tuning variables in `campfirevalley/web/static/js/campfire-nodes.js` (HexNodeBaseMixin):
  - `paddingTop`, `iconSizeTop`, `iconYTop`, `titleGap`, `titleFontSize`, `propFontSize`
- See `docs/ui-header-layout.md` for guidance on adjusting these values

## [1.1.0] - 2024-12-22

### Added
- **LiteGraph Integration**: Implemented hierarchical LiteGraph display for visual campfire management
  - Interactive canvas for node visualization and manipulation
  - Real-time monitoring of processes and node interactions
  - Support for creating, connecting, and managing campfire nodes visually
- **Web Interface Enhancements**: 
  - Complete web interface with FastAPI backend
  - Static file serving for CSS, JavaScript, and HTML assets
  - RESTful API endpoints for campfire management
- **Federation Support**: 
  - Multi-valley federation capabilities
  - Default dock campfires for distributed processing
  - Enhanced configuration management for federated environments
- **Documentation Improvements**:
  - Comprehensive README.md with server usage instructions
  - Docker setup guide with manifest configuration examples
  - Valley configuration documentation with multiple manifest types
  - GitHub Pages documentation site setup

### Fixed
- **TypeError Resolution**: Fixed property access issues in campfire-nodes.js
- **Integration Tests**: Resolved test failures and improved test coverage
- **Docker Configuration**: Updated docker-compose.yml for proper service orchestration

### Changed
- **Version Synchronization**: Aligned version numbers across all files (setup.py, __init__.py, API, etc.)
- **Configuration Management**: Enhanced manifest.yaml structure for better valley configuration
- **Web Server**: Improved valley_with_web_server.py for better performance and reliability

### Technical Details
- Updated FastAPI application version to 1.1.0
- Enhanced Docker build scripts with new version
- Improved error handling in web interface components
- Added comprehensive logging and monitoring capabilities

## [1.0.0] - Previous Release
- Initial release with core campfire functionality
- Basic valley management and configuration
- Command-line interface and basic web components
