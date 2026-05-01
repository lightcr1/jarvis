# Home Assistant Foundation Plan

This document defines the first structured expansion after the current V1 groundwork.

## Architectural Rule

Jarvis remains the primary system for:

- user experience
- authentication and permission enforcement
- orchestration
- command interpretation
- risk and confirmation policy
- auditability
- remote-access hardening decisions

Home Assistant is treated as a backend integration layer for selected domains such as:

- smart-home entities and services
- discovery signals
- shopping-list style integrations
- automations where explicitly allowed

Home Assistant must not become the main UI, main permission system, or primary assistant runtime.

## Foundation Scope Implemented Now

The current foundation adds a dedicated Home Assistant domain inside Jarvis:

- backend domain package in `jarvis/home_assistant/`
- explicit capability catalog
- action-risk policy mapping
- managed-entity and discovery-candidate models
- persisted Home Assistant domain store
- initial Home Assistant service boundary
- initial Home Assistant API router
- initial dedicated Home Assistant workspace page in the SPA

## Capability Model

Home Assistant access is intentionally not implied by normal admin access.

Capabilities introduced:

- `home_assistant.access`
- `home_assistant.device_discovery`
- `home_assistant.device_control`
- `home_assistant.security_device_control`
- `home_assistant.integration_management`
- `home_assistant.remote_control`
- `home_assistant.automation_management`

Access rules:

- the first global admin may bootstrap Home Assistant access
- all other users require explicit capability assignment
- capability assignment may come from direct user permissions or group-based permissions
- Jarvis remains the policy decision point

## Action / Risk Model

The foundation classifies Home Assistant actions into low, medium, and high risk.

Examples:

- low risk:
  - shopping list changes
  - read-oriented calendar actions
- medium risk:
  - normal device control
  - discovery review flows
- high risk:
  - security device control
  - remote system control
  - automation management where service impact is material

The current policy model already stores:

- required capability
- risk level
- confirmation requirement
- remote restriction flag

This gives Jarvis a stable place to enforce stronger remote policies later.

## Device / Entity Abstraction

The Home Assistant layer is not hardcoded only around lights or cameras.

The foundation introduces generic domain concepts:

- managed entity
- integration source
- capability list
- control mode
- trust level
- risk level
- onboarding status
- approval status
- area / room association

This keeps the path open for later support of:

- PCs
- NAS systems
- servers
- cameras
- lab systems
- other managed endpoints

## Discovery / Onboarding Model

Discovery is intentionally review-driven, not auto-trusting.

Current flow foundation:

1. candidate detected or proposed
2. candidate classified and stored
3. user reviews candidate
4. Jarvis enforces approval before integration

This foundation is designed to support later enrichment such as:

- likely device type
- suggested room
- trust score
- security sensitivity
- source provenance

## Dedicated UI Direction

The dedicated Home Assistant workspace inside Jarvis should remain:

- operational
- dashboard-oriented
- clearer at a glance than chat
- visually aligned with Jarvis
- separate from the standard conversation-first chat UI

The current foundation provides:

- dedicated `/home-assistant` route
- overview surface
- policy visibility
- discovery candidate review intake

Later UI phases should add:

- rooms / areas
- entities and states
- alerts and health
- approval queues
- security-sensitive action review
- shopping lists
- selected calendar surfaces

## Voice / Assistant Direction

Voice remains local-first where possible.

The Home Assistant expansion must not lock Jarvis into a single voice vendor.
Future voice work should preserve:

- local STT/TTS baseline
- optional cloud enhancement
- provider abstraction
- policy-aware command execution

## Security / Remote-Readiness Direction

Remote-friendly later does not mean internet-open now.

Security requirements for later phases:

- stronger restrictions for remote sessions
- explicit confirmation for high-risk classes
- auditable action trail
- capability separation by risk
- no direct Home Assistant exposure without Jarvis mediation

## Staged Plan

### Phase 1: Foundation

- capability model
- risk model
- domain models
- persistence
- service boundary
- API boundary
- dedicated UI shell

### Phase 2: Safe First Features

- read-only overview of entities and areas
- low-risk shopping list support
- discovery inbox / review queue
- explicit approval workflow

### Phase 3: Controlled Device Actions

- low-risk control classes
- stronger audit detail
- confirmation flows for medium/high-risk actions
- security-class device segmentation

### Phase 4: Broader Personal Assistant Expansion

- calendar and email assistance
- automation management
- PC/system control primitives
- stronger remote-access restrictions

## Current Boundaries

What is intentionally not implemented in this foundation:

- blind device auto-integration
- unrestricted remote execution
- security-device actions without stronger policy
- broad automation editor
- Home Assistant as a primary UI or auth layer

Those remain later-phase work.
