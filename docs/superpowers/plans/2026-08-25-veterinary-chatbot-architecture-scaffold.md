# Veterinary Chatbot Architecture Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the master architecture document and the empty repository scaffold with the approved modular veterinary chatbot design, without implementing executable bot behavior.

**Architecture:** Preserve the FastAPI modular-monolith shape while replacing LMS concepts with veterinary capabilities. .NET owns business data, Oracle Database 26ai, canonical conversations, external channels, and escalation state; Python owns orchestration, temporary technical state, Redis integration, and RAG over Qdrant.

**Tech Stack:** Python project scaffold, FastAPI boundary, LangGraph-oriented module layout, .NET HTTP integration boundary, Oracle Database 26ai behind .NET, Qdrant, Redis, JWT, Markdown documentation, Git.

## Global Constraints

- Do not implement Python classes, functions, endpoints, graphs, prompts, integrations, or bot behavior in this phase.
- Do not add runtime or development dependencies to `pyproject.toml` yet.
- Do not add secrets or concrete credentials to `.env.example`.
- Python must never connect directly to Oracle Database 26ai.
- Qdrant is the only vector store in the automation service architecture.
- .NET owns canonical conversation history, escalation state, external channels, and every business mutation.
- Redis is limited to cache, idempotency, conversation locking, and temporary technical checkpoints.
- Preserve the approved seven capability modules and prohibit direct imports between them.
- Use branch `refactor/veterinary-chatbot-architecture`.
- Use Conventional Commits with `:memo:` for documentation and `:sparkles:` for the new veterinary scaffold.

---

## Planned file map

### Documentation

- Modify `docs/Distribución de la arquitectura del servicio de automatización.md`: replace the LMS architecture with the approved veterinary master architecture.
- Modify `README.md`: identify the repository as the veterinary automation service and link the master architecture and approved design.
- Preserve `docs/plans/2026-08-25-veterinary-chatbot-architecture-design.md`: approved design decision.

### Core application scaffold

- Preserve `src/app/main.py`: future minimal application entry point.
- Preserve `src/app/bootstrap/`: future composition root, lifecycle, and module registration.
- Preserve `src/app/api/`: future versioned internal API boundary.
- Preserve `src/app/orchestration/`: future stable global graph, registry, routing, response envelope, and cross-cutting policies.
- Preserve `src/app/knowledge/`: future ingestion, chunking, indexing, retrieval, reranking, and document metadata.
- Preserve `src/app/security/`: future message, prompt-injection, content, and tool authorization controls.
- Preserve `src/app/observability/`: future logs, traces, metrics, and model usage.
- Preserve `src/app/shared/`: future minimal cross-module contracts and identifiers.
- Preserve `src/app/workers/`: future indexing, synchronization, and cleanup process entry points.

### Ports

- Create `src/app/ports/appointments.py`: future .NET appointment capability contract.
- Create `src/app/ports/services_catalog.py`: future .NET services, locations, schedules, and pricing contract.
- Create `src/app/ports/pet_profile.py`: future .NET pet data contract.
- Create `src/app/ports/conversation_history.py`: future canonical history retrieval and interaction registration contract.
- Create `src/app/ports/human_handoff.py`: future escalation request contract.
- Create `src/app/ports/knowledge_source.py`: future authorized-content synchronization contract.
- Create `src/app/ports/token_validator.py`: future JWT verification contract.
- Preserve technical ports for chat models, embeddings, Qdrant abstraction, Redis abstraction, and temporary checkpoints.
- Remove the broad inherited `src/app/ports/backend.py` contract and the unused `event_publisher.py` until an event transport is selected.

### Adapters

- Preserve `src/app/adapters/backend/dotnet_client.py`: future shared HTTP transport only.
- Create focused .NET gateway adapter files matching the business ports.
- Create `src/app/adapters/security/jwt.py`: future JWT validator implementation boundary.
- Replace `src/app/adapters/vector_store/pgvector.py` with `src/app/adapters/vector_store/qdrant.py`.
- Remove inherited LMS gateways and PostgreSQL conversation/checkpoint adapters.
- Preserve model, embedding, and Redis adapter locations without implementation.

### Capability modules

- Replace `src/app/modules/sales/` with:
  - `src/app/modules/appointments/`
  - `src/app/modules/services_catalog/`
  - `src/app/modules/pet_profile/`
  - `src/app/modules/veterinary_guidance/`
  - `src/app/modules/preventive_care/`
  - `src/app/modules/reminders/`
  - `src/app/modules/human_handoff/`
- Give every module the approved standard folders and empty architectural files.
- Give `appointments` separate node placeholders for scheduling, rescheduling, cancellation, selection, confirmation, and .NET result handling.
- Give other modules only capability-specific node names; do not add generic copied sales nodes.

---

### Task 1: Rewrite the master architecture for the veterinary domain

**Files:**
- Modify: `docs/Distribución de la arquitectura del servicio de automatización.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: approved decisions in `docs/plans/2026-08-25-veterinary-chatbot-architecture-design.md`.
- Produces: the authoritative architectural reference used to validate the scaffold in later tasks.

- [ ] **Step 1: Replace LMS terminology and architecture claims**

Rewrite the master document in Spanish with these exact top-level sections:

1. Propósito y alcance.
2. Principios y decisiones obligatorias.
3. Vista general y flujo entre sistemas.
4. Propiedad de datos y almacenamiento.
5. Distribución completa del repositorio.
6. Punto de entrada y bootstrap.
7. API interna versionada y JWT.
8. Orquestación y registro dinámico.
9. Módulos veterinarios.
10. Estructura estándar de un módulo.
11. Puertos por capacidad.
12. Adaptadores concretos.
13. RAG con Qdrant.
14. Seguridad veterinaria.
15. Escalamiento humano.
16. Confirmaciones e idempotencia.
17. Fallbacks y resiliencia.
18. Observabilidad.
19. Workers y recordatorios.
20. Estrategia de pruebas.
21. Reglas para agregar un módulo.
22. Decisiones fuera de alcance.

The document must explicitly state that .NET owns Oracle Database 26ai, canonical conversation history, escalation state, external channels, and business mutations. It must explicitly state that Python never connects to Oracle and that Qdrant is not a source of dynamic or transactional information.

- [ ] **Step 2: Document all seven modules and their boundaries**

Document `appointments`, `services_catalog`, `pet_profile`, `veterinary_guidance`, `preventive_care`, `reminders`, and `human_handoff`. Include scheduling, rescheduling, and cancellation as subflows of `appointments`, not separate modules.

- [ ] **Step 3: Document fallback precedence**

Define the processing precedence as authentication, request validation, idempotency, conversation lock, canonical escalation check, safety, routing, module execution, fallback handling, interaction registration, and response. Document the eight approved fallback categories and bounded retry rules.

- [ ] **Step 4: Replace the README placeholder**

Set the README title to `Huellitas ChatBot — Servicio de automatización veterinaria`. State that the repository is currently in the architecture-definition phase, list .NET/Oracle 26ai, Qdrant, and Redis ownership, and link both architecture documents using relative Markdown links.

- [ ] **Step 5: Validate terminology and links**

Run:

```powershell
rg -n "LMS|curso|tutor|estudiante|learning_gateway|assessment_gateway|pgvector|PostgreSQL" README.md docs
rg -n "Oracle Database 26ai|Qdrant|Redis|JWT|escalamiento|human_handoff" README.md docs
git diff --check
```

Expected: the first search has no inherited LMS architecture terms outside historical context in the approved design; the second finds all required decisions; `git diff --check` exits successfully.

- [ ] **Step 6: Commit documentation**

```powershell
git add -- README.md 'docs/Distribución de la arquitectura del servicio de automatización.md'
git commit -m "docs: :memo: adapt master architecture to veterinary domain"
```

### Task 2: Align infrastructure boundaries and remove inherited LMS storage choices

**Files:**
- Create: focused port and adapter placeholders listed in the planned file map.
- Delete: inherited LMS gateway placeholders, `src/app/ports/backend.py`, `src/app/ports/event_publisher.py`, PostgreSQL adapter placeholders, and `migrations/.gitkeep`.
- Rename: `src/app/adapters/vector_store/pgvector.py` to `src/app/adapters/vector_store/qdrant.py`.
- Preserve: all provider-neutral model, embedding, cache, knowledge, security, observability, orchestration, API, bootstrap, shared, and worker placeholders.

**Interfaces:**
- Consumes: ownership and dependency rules from the rewritten master document.
- Produces: empty but correctly named technical boundaries for later implementation.

- [ ] **Step 1: Remove inherited LMS and PostgreSQL placeholders**

Delete only these tracked empty files:

```text
src/app/adapters/backend/assessment_gateway.py
src/app/adapters/backend/authentication.py
src/app/adapters/backend/catalog_gateway.py
src/app/adapters/backend/learning_gateway.py
src/app/adapters/persistence/postgres_checkpoints.py
src/app/adapters/persistence/postgres_conversations.py
src/app/adapters/persistence/repositories/.gitkeep
src/app/adapters/vector_store/pgvector.py
src/app/ports/backend.py
src/app/ports/event_publisher.py
migrations/.gitkeep
```

- [ ] **Step 2: Create focused empty port placeholders**

Create these empty files:

```text
src/app/ports/appointments.py
src/app/ports/services_catalog.py
src/app/ports/pet_profile.py
src/app/ports/conversation_history.py
src/app/ports/human_handoff.py
src/app/ports/knowledge_source.py
src/app/ports/token_validator.py
```

- [ ] **Step 3: Create focused empty adapter placeholders**

Create these empty files:

```text
src/app/adapters/backend/appointments_gateway.py
src/app/adapters/backend/services_catalog_gateway.py
src/app/adapters/backend/pet_profile_gateway.py
src/app/adapters/backend/conversation_gateway.py
src/app/adapters/backend/human_handoff_gateway.py
src/app/adapters/backend/knowledge_source_gateway.py
src/app/adapters/security/jwt.py
src/app/adapters/vector_store/qdrant.py
```

- [ ] **Step 4: Extend empty orchestration policy placeholders**

Create:

```text
src/app/orchestration/policies/escalation_policy.py
src/app/orchestration/policies/idempotency_policy.py
src/app/orchestration/policies/retry_policy.py
src/app/orchestration/policies/safety_policy.py
src/app/orchestration/conversation_lock.py
```

- [ ] **Step 5: Validate infrastructure structure**

Run:

```powershell
rg --files src/app/ports src/app/adapters src/app/orchestration | Sort-Object
rg --files | rg "assessment|learning_gateway|catalog_gateway|pgvector|postgres_|migrations"
Get-ChildItem src/app -Recurse -File -Filter '*.py' | Where-Object Length -gt 0
git diff --check
```

Expected: the first command shows focused veterinary and technical boundaries; the second and third commands return no output; `git diff --check` exits successfully.

- [ ] **Step 6: Commit infrastructure scaffold**

```powershell
git add -A -- migrations src/app/adapters src/app/ports src/app/orchestration
git commit -m "refactor: :sparkles: align automation infrastructure boundaries"
```

### Task 3: Replace the sales module with veterinary capability modules

**Files:**
- Delete: `src/app/modules/sales/` and every inherited empty LMS placeholder below it.
- Create: seven standard module directory trees and their capability-specific node placeholders.

**Interfaces:**
- Consumes: the standard module contract and module list from the master document.
- Produces: the physical capability boundaries future implementation plans will fill.

- [ ] **Step 1: Remove the inherited sales module**

Delete the tracked empty `src/app/modules/sales/` tree after verifying every file remains empty.

- [ ] **Step 2: Create common empty files for every approved module**

For each of the seven modules, create:

```text
manifest.py
contracts.py
state.py
graph.py
domain/.gitkeep
services/.gitkeep
tools/.gitkeep
tests/.gitkeep
prompts/system_prompt.py
```

- [ ] **Step 3: Create appointment node placeholders**

Create:

```text
src/app/modules/appointments/nodes/identify_request.py
src/app/modules/appointments/nodes/collect_appointment_data.py
src/app/modules/appointments/nodes/list_appointments.py
src/app/modules/appointments/nodes/check_availability.py
src/app/modules/appointments/nodes/present_options.py
src/app/modules/appointments/nodes/request_confirmation.py
src/app/modules/appointments/nodes/execute_appointment_action.py
src/app/modules/appointments/nodes/handle_backend_result.py
```

- [ ] **Step 4: Create information and profile node placeholders**

Create:

```text
src/app/modules/services_catalog/nodes/understand_service_query.py
src/app/modules/services_catalog/nodes/fetch_dynamic_service_data.py
src/app/modules/services_catalog/nodes/retrieve_service_knowledge.py
src/app/modules/services_catalog/nodes/prepare_service_response.py
src/app/modules/pet_profile/nodes/identify_pet.py
src/app/modules/pet_profile/nodes/fetch_pet_profile.py
src/app/modules/pet_profile/nodes/prepare_profile_change.py
src/app/modules/pet_profile/nodes/request_confirmation.py
src/app/modules/pet_profile/nodes/submit_profile_change.py
```

- [ ] **Step 5: Create guidance and preventive-care node placeholders**

Create:

```text
src/app/modules/veterinary_guidance/nodes/collect_guidance_context.py
src/app/modules/veterinary_guidance/nodes/detect_urgency_signals.py
src/app/modules/veterinary_guidance/nodes/retrieve_authorized_guidance.py
src/app/modules/veterinary_guidance/nodes/prepare_safe_guidance.py
src/app/modules/preventive_care/nodes/identify_preventive_need.py
src/app/modules/preventive_care/nodes/fetch_authorized_pet_context.py
src/app/modules/preventive_care/nodes/retrieve_preventive_knowledge.py
src/app/modules/preventive_care/nodes/prepare_preventive_response.py
```

- [ ] **Step 6: Create reminder and handoff node placeholders**

Create:

```text
src/app/modules/reminders/nodes/validate_reminder_context.py
src/app/modules/reminders/nodes/build_reminder_content.py
src/app/modules/reminders/nodes/prepare_reminder_result.py
src/app/modules/human_handoff/nodes/determine_handoff_reason.py
src/app/modules/human_handoff/nodes/build_handoff_summary.py
src/app/modules/human_handoff/nodes/request_backend_handoff.py
src/app/modules/human_handoff/nodes/handle_handoff_result.py
```

- [ ] **Step 7: Validate module symmetry and emptiness**

Run:

```powershell
$moduleNames = @('appointments', 'services_catalog', 'pet_profile', 'veterinary_guidance', 'preventive_care', 'reminders', 'human_handoff')
$requiredEntries = @('manifest.py', 'contracts.py', 'state.py', 'graph.py', 'nodes', 'tools', 'prompts', 'domain', 'services', 'tests')
$missingEntries = foreach ($moduleName in $moduleNames) {
    foreach ($entry in $requiredEntries) {
        $entryPath = Join-Path "src/app/modules/$moduleName" $entry
        if (-not (Test-Path -LiteralPath $entryPath)) {
            $entryPath
        }
    }
}
if ($missingEntries) {
    $missingEntries
    throw 'The module scaffold is incomplete.'
}
rg --files src/app/modules | Sort-Object
rg --files src/app/modules | rg "sales|course|learning|assessment|student|tutor"
Get-ChildItem src/app/modules -Recurse -File -Filter '*.py' | Where-Object Length -gt 0
git diff --check
```

Expected: the LMS search and non-empty Python search return no output, and `git diff --check` exits successfully.

- [ ] **Step 8: Commit module scaffold**

```powershell
git add -A -- src/app/modules
git commit -m "feat: :sparkles: scaffold veterinary capability modules"
```

### Task 4: Audit the completed architecture-only scaffold

**Files:**
- Review: all tracked files.
- Modify only if an audit identifies a mismatch with the approved design.

**Interfaces:**
- Consumes: the approved design, rewritten master document, and aligned scaffold.
- Produces: evidence that the repository contains architecture only and no accidental implementation.

- [ ] **Step 1: Verify there is no executable implementation**

Run:

```powershell
Get-ChildItem src -Recurse -File -Filter '*.py' | Where-Object Length -gt 0
Get-Content -Raw pyproject.toml
Get-Content -Raw .env.example
```

Expected: no non-empty Python file and no dependencies or credentials.

- [ ] **Step 2: Verify domain and technology decisions**

Run:

```powershell
rg -n "Oracle Database 26ai|Qdrant|Redis|JWT|human_handoff|appointments" README.md docs
rg -n "LMS|curso|tutor|estudiante|pgvector|PostgreSQL" README.md 'docs/Distribución de la arquitectura del servicio de automatización.md' src
```

Expected: required veterinary decisions are present and inherited LMS/PostgreSQL terms are absent from the authoritative document and scaffold.

- [ ] **Step 3: Verify Git state and commits**

Run:

```powershell
git diff --check
git status --short
git log --oneline --decorate -5
```

Expected: no whitespace errors, a clean working tree, and Conventional Commits on `refactor/veterinary-chatbot-architecture`.

- [ ] **Step 4: Report the review boundary**

Report that architecture and filesystem layout are ready for review, while runtime behavior, dependency selection, API schemas, providers, prompts, and integrations remain intentionally unimplemented.
