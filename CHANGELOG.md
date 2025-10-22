# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.2] - Unreleased
- Start development for 1.1.2. No user-facing changes yet.

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