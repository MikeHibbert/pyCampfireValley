# Requirements Document

## Introduction

CampfireValley is a Python library that extends the Campfires framework by introducing the concept of "valleys" as interconnected, secure communities of campfires. The library manages docks as gateways for inter-valley communication, handles riverboat (torch) exchanges via MCP, and provides default campfires for loading/offloading, security sanitization, and justice enforcement. It enables anonymous or discoverable valley connections, pre-shared key management, and provisioning of imported campfires for distributed AI workflows.

## Glossary

- **Valley**: A self-contained instance hosting multiple campfires with its own Party Box and MCP broker
- **Dock**: The gateway for each valley consisting of three default campfires handling inbound/outbound exchanges
- **Riverboat**: A metaphor for torches carrying Party Box payloads between valleys via MCP channels
- **Community**: A network of valleys with shared discovery, addresses, and access controls via pre-shared keys
- **Dockmaster_Campfire**: Default campfire handling torch loading/unloading and routing
- **Sanitizer_Campfire**: Default campfire providing security scanning and content filtering
- **Justice_Campfire**: Default campfire managing access control and policy enforcement
- **CampfireValley_System**: The complete library system managing valleys, docks, and communities
- **MCP_Broker**: Message Communication Protocol broker using Redis-py for inter-valley communication
- **Party_Box**: Storage system for torch payloads and attachments
- **Redis_Client**: Standard redis-py client for pub/sub messaging
- **Cryptography_Module**: Python cryptography library for encryption and key management
- **VALI**: Valley Application Layer Interface for standardized inter-valley service patterns
- **Backend_Developer**: Specialized campfire for backend development services
- **Frontend_Developer**: Specialized campfire for frontend development services  
- **Project_Manager**: Specialized campfire for project coordination and management
- **DevOps_Developer**: Specialized campfire for deployment and infrastructure services
- **Testing_Developer**: Specialized campfire for testing and quality assurance services

## Requirements

### Requirement 1

**User Story:** As a distributed AI system developer, I want to initialize and manage valleys, so that I can create self-contained instances that host multiple campfires with their own communication infrastructure.

#### Acceptance Criteria

1. WHEN a Valley is initialized with name and manifest path, THE CampfireValley_System SHALL create a valley instance with loaded configuration from manifest.yaml
2. THE CampfireValley_System SHALL auto-create a dock with three default campfires unless disabled in configuration
3. WHEN start() is called on a valley, THE CampfireValley_System SHALL boot the dock and subscribe to dock:invite and dock/incoming channels
4. THE CampfireValley_System SHALL support distributed deployment where valleys on different IPs connect via Redis_Client with TLS encryption
5. WHEN join_community() is called with community name and key, THE CampfireValley_System SHALL register with the community and exchange pre-shared keys using Cryptography_Module

### Requirement 2

**User Story:** As a valley operator, I want a dock gateway system, so that I can manage all inter-valley interactions through a secure, controlled entry point.

#### Acceptance Criteria

1. THE CampfireValley_System SHALL expose a public dock:invite channel for discovery when dock_mode is set to public
2. WHEN dock:invite is broadcast, THE CampfireValley_System SHALL include status, alias, public_address, exposed_campfires, and key_exchange information
3. WHEN inbound torches arrive on dock/incoming, THE CampfireValley_System SHALL validate sender key and route to appropriate campfire
4. THE CampfireValley_System SHALL package outbound torches with Party Box attachments, sign with key, and send to target address
5. WHERE dock_mode is set to partial, THE CampfireValley_System SHALL expose only dock metadata

### Requirement 3

**User Story:** As a valley administrator, I want default dock campfires for essential operations, so that I can ensure proper handling of torch loading, security scanning, and access control.

#### Acceptance Criteria

1. THE CampfireValley_System SHALL provide a Dockmaster_Campfire with Loader, Router, and Packer campers for torch handling
2. WHEN incoming torches are received, THE Dockmaster_Campfire SHALL unzip payloads and split large items into Party Box sub-boxes
3. THE CampfireValley_System SHALL provide a Sanitizer_Campfire with Scanner and Filter campers for security checks
4. WHEN content is flagged by sanitization, THE Sanitizer_Campfire SHALL move items to quarantine and notify Justice_Campfire
5. THE CampfireValley_System SHALL provide a Justice_Campfire with Sheriff and Investigator campers for access control and policy enforcement

### Requirement 4

**User Story:** As a valley network participant, I want community addressing and discovery features, so that I can connect with other valleys while maintaining appropriate privacy controls.

#### Acceptance Criteria

1. WHEN joining a community, THE CampfireValley_System SHALL send handshake torch with join flag, alias, and key hash to trusted neighbor
2. THE CampfireValley_System SHALL support hierarchical addressing in format valley:{name}/{campfire}/{camper}
3. WHERE expose setting is partial or none, THE CampfireValley_System SHALL limit propagation to direct connections only
4. THE CampfireValley_System SHALL manage pre-shared AES-256 keys using Cryptography_Module for authentication between valleys
5. WHEN access violations occur, THE Justice_Campfire SHALL revoke keys and update known valleys list using secure file operations

### Requirement 5

**User Story:** As a valley operator, I want to provision imported campfires dynamically, so that I can extend valley capabilities by importing configurations from trusted sources.

#### Acceptance Criteria

1. WHEN provision torch is received with campfire configuration, THE Dockmaster_Campfire SHALL forward to Sanitizer_Campfire for safety check
2. WHEN configuration passes security validation, THE Justice_Campfire SHALL verify sender trust level
3. IF configuration is approved, THE CampfireValley_System SHALL load RAG, create Campfire class, and wire MCP channels
4. THE CampfireValley_System SHALL support importing campfire configurations including roles, RAG paths, and auditor settings
5. THE CampfireValley_System SHALL maintain imported campfire lifecycle within the valley's Party Box and MCP broker

### Requirement 6

**User Story:** As a system administrator, I want comprehensive security and performance controls, so that I can ensure safe, scalable operation of valley networks.

#### Acceptance Criteria

1. THE CampfireValley_System SHALL encrypt all communications using Redis_Client with TLS configuration and Cryptography_Module for payload encryption
2. THE CampfireValley_System SHALL support 1-100 valleys using Redis_Client pub/sub for low-latency communication
3. THE CampfireValley_System SHALL handle torches under 1KB and Party Box assets up to 10MB using asyncio for concurrent execution
4. THE CampfireValley_System SHALL rotate pre-shared keys periodically using Cryptography_Module and store them encrypted in .secrets/valley_links.json
5. WHERE auditors are enabled, THE CampfireValley_System SHALL verify bundle integrity using hashlib and scan completeness before processing

### Requirement 7

**User Story:** As a developer, I want demo examples with specialist teams, so that I can see how valleys can provide and request development services through structured team collaboration.

#### Acceptance Criteria

1. THE CampfireValley_System SHALL provide demo examples using standard VALI (Valley Application Layer Interface) patterns
2. THE CampfireValley_System SHALL include a specialist team valley with Backend_Developer, Frontend_Developer, Project_Manager, DevOps_Developer, and Testing_Developer campfires
3. WHEN a service request torch is received, THE specialist valley SHALL route requests to appropriate developer campfires based on request type
4. THE CampfireValley_System SHALL provide a client valley example that requests development services from the specialist valley
5. THE CampfireValley_System SHALL demonstrate end-to-end workflows where client valleys send project requirements and receive completed deliverables through dock exchanges