# Appointment Availability Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let booking and rescheduling users ask which upcoming dates have real slots for the veterinarian and service already selected.

**Architecture:** Add a deterministic availability-intent detector and a bounded service that calls the existing date-specific .NET slots endpoint. Integrate it only in appointment date steps, preserve the pending draft, and format up to three available dates in the configured local time zone.

**Tech Stack:** Python 3.12+, asyncio, datetime, Pydantic Settings, pytest, Ruff

## Global Constraints

- Use only slots returned by the .NET backend.
- Search at most 14 calendar days by default and stop after 3 dates with slots.
- Keep the selected veterinarian and service IDs unchanged.
- Do not route operational availability discovery through the language model.
- Keep booking and rescheduling prompts professional and free of example lists.
- Make the search horizon and result count configurable through `HUELLITAS_` settings.

---

### Task 1: Availability discovery service

**Files:**
- Create: `src/app/modules/appointments/services/availability_discovery.py`
- Create: `tests/unit/modules/appointments/test_availability_discovery.py`

**Interfaces:**
- Consumes: `AppointmentsGateway`, selected UUIDs, local start date, bearer token, `search_days`, and `max_dates`.
- Produces: `is_availability_discovery_request`, `discover_available_dates`, and `format_available_dates`.

- [ ] **Step 1: Write failing intent and bounded-search tests**

Test literal phrases including `qué días hay disponibles`, `cuándo tiene cupo`, and `muéstrame los próximos horarios`. Use a recording gateway whose slots exist on offsets 1, 3, 5, and 7; assert that a 14-day search stops after offsets 1, 3, and 5 and every call receives the same veterinarian and service UUIDs. Add an empty-result test asserting exactly 14 date requests.

- [ ] **Step 2: Run tests to verify RED**

Run: `uv run pytest tests/unit/modules/appointments/test_availability_discovery.py -q`

Expected: collection fails because `availability_discovery` does not exist.

- [ ] **Step 3: Implement the deterministic service**

Create these public contracts:

```python
@dataclass(frozen=True, slots=True)
class AvailableAppointmentDate:
    value: date
    slots: tuple[AppointmentBookingSlot, ...]


def is_availability_discovery_request(text: str) -> bool:
    normalized = normalize_availability_text(text)
    return any(pattern.search(normalized) for pattern in AVAILABILITY_PATTERNS)


async def discover_available_dates(
    gateway: AppointmentsGateway,
    veterinarian_id: UUID,
    service_id: UUID,
    start_date: date,
    bearer_token: str,
    *,
    search_days: int,
    max_dates: int,
) -> tuple[AvailableAppointmentDate, ...]:
    matches: list[AvailableAppointmentDate] = []
    for offset in range(search_days):
        value = start_date + timedelta(days=offset)
        slots = await gateway.list_booking_slots(
            veterinarian_id, service_id, value, bearer_token
        )
        if slots:
            matches.append(AvailableAppointmentDate(value, slots))
            if len(matches) == max_dates:
                break
    return tuple(matches)


def format_available_dates(
    dates: tuple[AvailableAppointmentDate, ...],
    veterinarian_name: str | None,
    zone: ZoneInfo,
    search_days: int,
) -> str:
    if not dates:
        return (
            f"No encontré horarios disponibles durante los próximos {search_days} días. "
            "Puedes elegir otro veterinario o indicar una fecha posterior."
        )
    name = veterinarian_name or "El veterinario seleccionado"
    lines = format_available_date_lines(dates, zone)
    return f"{name} tiene disponibilidad:\n{lines}\nIndica la fecha que prefieres."
```

Normalize accents, punctuation, and repeated spaces for intent matching. Query dates sequentially from `start_date` through `start_date + search_days - 1`, append only non-empty results, and break at `max_dates`. Format Spanish dates and local slot times; when empty, state the exact search window and offer another veterinarian or a later date.

- [ ] **Step 4: Run service tests to verify GREEN**

Run: `uv run pytest tests/unit/modules/appointments/test_availability_discovery.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the service**

```bash
git add src/app/modules/appointments/services/availability_discovery.py tests/unit/modules/appointments/test_availability_discovery.py
git commit -m "feat(appointments): discover upcoming availability"
```

### Task 2: Booking and rescheduling behavior

**Files:**
- Modify: `src/app/modules/appointments/services/date_resolver.py`
- Modify: `src/app/modules/appointments/nodes/collect_appointment_data.py`
- Modify: `src/app/modules/appointments/nodes/collect_reschedule_data.py`
- Modify: `src/app/modules/appointments/graph.py`
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: Task 1 discovery functions and executor limits.
- Produces: professional date prompts and availability discovery within both date collection flows.

- [ ] **Step 1: Write failing flow tests**

Add a booking test that advances through pet, service, and veterinarian, sends `qué días hay disponibles`, and asserts that the response names the selected veterinarian and lists real dates while the pending step remains `date`. Add the equivalent rescheduling test and assert original veterinarian/service IDs are used. Add prompt assertions for `¿Para qué fecha deseas agendar la cita?` and `¿Para qué fecha deseas reprogramar la cita?`.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q -k "availability_discovery or professional_date_prompt"`

Expected: failures because discovery questions are still sent to the date resolver and prompts still contain examples.

- [ ] **Step 3: Integrate discovery with date resolution**

Define:

```python
BOOKING_DATE_PROMPT = "¿Para qué fecha deseas agendar la cita?"
RESCHEDULE_DATE_PROMPT = "¿Para qué fecha deseas reprogramar la cita?"
```

Allow `date_resolution_error_message(error, prompt)` to append the correct professional prompt for unrecognized dates. Add `availability_search_days: int = 14` and `availability_max_dates: int = 3` to `AppointmentsModuleExecutor` and pass them to booking and rescheduling. Resolve an explicit natural date first; only when no date resolves, detect the availability question and invoke Task 1 discovery. Return the formatted discovery response with the original pending draft unchanged.

- [ ] **Step 4: Run appointment tests to verify GREEN**

Run: `uv run pytest tests/unit/modules/appointments -q`

Expected: all appointment tests pass.

- [ ] **Step 5: Commit flow integration**

```bash
git add src/app/modules/appointments/services/date_resolver.py src/app/modules/appointments/nodes/collect_appointment_data.py src/app/modules/appointments/nodes/collect_reschedule_data.py src/app/modules/appointments/graph.py tests/unit/modules/appointments/test_appointments_module.py
git commit -m "feat(appointments): answer availability questions"
```

### Task 3: Configuration, documentation, and verification

**Files:**
- Modify: `src/app/bootstrap/settings.py`
- Modify: `src/app/bootstrap/module_registry.py`
- Modify: `src/app/bootstrap/lifecycle.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/unit/bootstrap/test_pet_profile_settings.py`

**Interfaces:**
- Consumes: executor configuration from Task 2.
- Produces: `HUELLITAS_APPOINTMENT_AVAILABILITY_SEARCH_DAYS` and `HUELLITAS_APPOINTMENT_AVAILABILITY_MAX_DATES` settings.

- [ ] **Step 1: Write failing settings tests**

Assert defaults of 14 and 3. Assert zero values are rejected and explicit values load from the two `HUELLITAS_` environment fields.

- [ ] **Step 2: Run settings tests to verify RED**

Run: `uv run pytest tests/unit/bootstrap/test_pet_profile_settings.py -q`

Expected: failures because the settings fields do not exist.

- [ ] **Step 3: Add settings and wire the registry**

Add:

```python
appointment_availability_search_days: int = Field(default=14, ge=1, le=60)
appointment_availability_max_dates: int = Field(default=3, ge=1, le=10)
```

Pass both fields from lifecycle to `build_module_registry` and from the registry to `AppointmentsModuleExecutor`. Document both variables in `.env.example` and explain availability discovery in `README.md`.

- [ ] **Step 4: Run complete verification**

Run:

```bash
uv run pytest -q
uv run ruff check src/app/modules/appointments src/app/bootstrap tests/unit/modules/appointments tests/unit/bootstrap/test_pet_profile_settings.py
uv run python -m compileall -q src
git diff --check
```

Expected: every command exits zero.

- [ ] **Step 5: Commit and inspect**

```bash
git add src/app/bootstrap/settings.py src/app/bootstrap/module_registry.py src/app/bootstrap/lifecycle.py .env.example README.md tests/unit/bootstrap/test_pet_profile_settings.py docs/superpowers/plans/2026-09-08-appointment-availability-discovery.md
git commit -m "config(appointments): configure availability discovery"
git status --short
git log --oneline -8
```

Expected: clean working tree with the discovery changes committed on `feat/natural-language-appointment-dates`.
