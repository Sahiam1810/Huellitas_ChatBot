# Natural-language Appointment Dates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve common Spanish natural-language dates into an exact local appointment date and query the selected veterinarian's backend availability for booking and rescheduling.

**Architecture:** Add a pure deterministic resolver under the appointments services package. Booking and rescheduling pass it an injected local reference date, retain their existing pending draft, and continue using the existing .NET slots gateway as the availability authority.

**Tech Stack:** Python 3.12+, `datetime`, `zoneinfo`, pytest, Ruff, mypy

## Global Constraints

- Interpret dates in the configured display time zone; production currently uses `America/Bogota`.
- Never silently move a past date to a later month or year.
- Never use the language model to choose or invent an operational date.
- Preserve the selected pet, service, veterinarian, and pending state when asking for another date.
- The .NET backend remains authoritative for available appointment slots.
- Add no third-party date parsing dependency.

---

### Task 1: Deterministic Spanish date resolver

**Files:**
- Create: `src/app/modules/appointments/services/date_resolver.py`
- Create: `tests/unit/modules/appointments/test_date_resolver.py`

**Interfaces:**
- Consumes: `text: str` and `reference_date: datetime.date`.
- Produces: `resolve_appointment_date(text, reference_date) -> DateResolution`, where `DateResolution.value` is the resolved date or `None`, and `DateResolution.error` is `DateResolutionError | None`.

- [x] **Step 1: Write failing relative-date tests**

Add literal expectations with `reference_date=date(2026, 9, 8)`:

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("la necesito para mañana", date(2026, 9, 9)),
        ("puede ser pasado mañana", date(2026, 9, 10)),
        ("el martes de la próxima semana", date(2026, 9, 15)),
        ("el próximo viernes", date(2026, 9, 11)),
        ("este domingo", date(2026, 9, 13)),
    ],
)
def test_resolves_relative_spanish_dates(text: str, expected: date) -> None:
    assert resolve_appointment_date(text, date(2026, 9, 8)).value == expected
```

- [x] **Step 2: Run the new tests and verify RED**

Run: `uv run pytest tests/unit/modules/appointments/test_date_resolver.py -q`

Expected: collection fails because `date_resolver` does not exist.

- [x] **Step 3: Implement normalization and relative resolution**

Create:

```python
class DateResolutionError(StrEnum):
    UNRECOGNIZED = "unrecognized"
    AMBIGUOUS = "ambiguous"
    PAST = "past"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class DateResolution:
    value: date | None = None
    error: DateResolutionError | None = None


def resolve_appointment_date(text: str, reference_date: date) -> DateResolution:
    normalized = normalize_date_text(text)
    candidate = resolve_relative_date(normalized, reference_date)
    if candidate is None:
        candidate = resolve_calendar_date(normalized, reference_date)
    if isinstance(candidate, DateResolutionError):
        return DateResolution(error=candidate)
    if candidate is None:
        return DateResolution(error=DateResolutionError.UNRECOGNIZED)
    if candidate < reference_date:
        return DateResolution(error=DateResolutionError.PAST)
    return DateResolution(value=candidate)
```

Implement `normalize_date_text(text) -> str`, `resolve_relative_date(text, reference_date) -> date | DateResolutionError | None`, and `resolve_calendar_date(text, reference_date) -> date | DateResolutionError | None` in the same module. Normalize case, accents, punctuation, and repeated spaces. Resolve `pasado mañana` before `mañana`; resolve weekday phrases with Monday as the start of the calendar week. Bare weekdays mean the next occurrence on or after the reference date, `próximo <weekday>` means the next occurrence strictly after it, and `<weekday> de la próxima semana` means that weekday in the next calendar week.

- [x] **Step 4: Add failing calendar-date and rejection tests**

Cover explicit formats embedded in sentences, `15 de este mes`, `15 del próximo mes`, named Spanish months, December-to-January rollover, `31 de febrero`, a past day in the current month, and unrecognized text. Assert the exact typed error for each rejection.

- [x] **Step 5: Implement calendar parsing and validation**

Use anchored numeric component regexes with non-digit boundaries and `datetime.date(year, month, day)` for calendar validation. Resolve named months without a year inside the reference year; if already past, return `PAST` rather than assuming the next year. Return `AMBIGUOUS` for an isolated day number without month context.

- [x] **Step 6: Run resolver tests and commit**

Run: `uv run pytest tests/unit/modules/appointments/test_date_resolver.py -q`

Expected: all resolver tests pass.

```bash
git add src/app/modules/appointments/services/date_resolver.py tests/unit/modules/appointments/test_date_resolver.py
git commit -m "feat(appointments): resolve natural Spanish dates"
```

### Task 2: Booking flow integration

**Files:**
- Modify: `src/app/modules/appointments/graph.py`
- Modify: `src/app/modules/appointments/nodes/collect_appointment_data.py`
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`

**Interfaces:**
- Consumes: `resolve_appointment_date(message, local_today)` and the veterinarian/service IDs already held by `AppointmentBookingDraft`.
- Produces: a slots request for the resolved date and clearer prompts/errors while preserving the pending draft.

- [x] **Step 1: Write failing booking-flow tests**

Construct `AppointmentsModuleExecutor` with `today_provider=lambda: date(2026, 9, 8)`. Advance through pet, service, and veterinarian, then send `la quiero para el martes de la próxima semana`. Assert that the gateway receives `date(2026, 9, 15)` with veterinarian `33333333-3333-3333-3333-333333333333` and service `44444444-4444-4444-4444-444444444444`, and that the bot lists returned slots.

Add tests proving a past expression stays on `step="date"`, does not call `list_booking_slots`, and asks for a valid future date; no-slot results preserve the selected veterinarian and request another date.

- [x] **Step 2: Run booking tests and verify RED**

Run: `uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q -k "natural_date or past_date or no_slots"`

Expected: failure because the flow still requires a formatted date and has no injected local date.

- [x] **Step 3: Inject the local date and integrate the resolver**

Add `today_provider: Callable[[], date] | None = None` to `AppointmentsModuleExecutor`; default it to `lambda: datetime.now(self._time_zone).date()`. Pass `self._today_provider()` into `advance_booking` and later rescheduling.

Replace `parse_booking_date(message)` at the booking date step with `resolve_appointment_date(message, local_today)`. Map `PAST`, `INVALID`, `AMBIGUOUS`, and `UNRECOGNIZED` to safe Spanish guidance. Change the date prompt to:

```text
¿Qué día prefieres? Puedes decir “mañana”, “el martes de la próxima semana” o “el 15 de este mes”.
```

When the gateway returns no slots, identify the previously selected veterinarian by name and request another date without rebuilding the draft.

- [x] **Step 4: Run all appointment module tests and commit**

Run: `uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q`

Expected: all appointment module tests pass.

```bash
git add src/app/modules/appointments/graph.py src/app/modules/appointments/nodes/collect_appointment_data.py tests/unit/modules/appointments/test_appointments_module.py
git commit -m "feat(appointments): accept natural booking dates"
```

### Task 3: Rescheduling integration and full verification

**Files:**
- Modify: `src/app/modules/appointments/nodes/collect_reschedule_data.py`
- Modify: `tests/unit/modules/appointments/test_appointments_module.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: the same injected local date and deterministic resolver used by booking.
- Produces: natural-language rescheduling with the original appointment's veterinarian/service IDs preserved in the slots request.

- [x] **Step 1: Write failing rescheduling tests**

Start a rescheduling draft with fixed veterinarian/service IDs and send `mañana` using `reference_date=date(2026, 9, 8)`. Assert the gateway receives `date(2026, 9, 9)` and returns numbered slots. Add a past-date test that keeps the pending draft and performs no slots query.

- [x] **Step 2: Run rescheduling tests and verify RED**

Run: `uv run pytest tests/unit/modules/appointments/test_appointments_module.py -q -k "reschedule and natural"`

Expected: failure because rescheduling still calls the fixed-format parser.

- [x] **Step 3: Integrate the shared resolver and update copy**

Pass `local_today` into `advance_reschedule`, use the same typed error mapping as booking, and replace every format-only rescheduling prompt with the shared natural-date prompt. Keep the existing live slot recheck before sending the OTP.

Document the accepted examples, local-time interpretation, past-date rejection, and backend-authoritative availability in `README.md`.

- [x] **Step 4: Run quality gates**

Run:

```bash
uv run pytest tests/unit/modules/appointments -q
uv run pytest tests/unit/adapters/dotnet/test_appointments_gateway.py -q
uv run ruff check src tests
uv run mypy src
uv run pytest -q
```

Expected: every command exits zero.

Verification note: this repository does not include `mypy` in its development
dependencies. The changed files pass Ruff, the full pytest suite passes, and the
source tree is additionally compiled with `python -m compileall`.

- [x] **Step 5: Commit and inspect the branch**

```bash
git add src/app/modules/appointments/nodes/collect_reschedule_data.py tests/unit/modules/appointments/test_appointments_module.py README.md
git commit -m "feat(appointments): accept natural reschedule dates"
git diff --check develop...HEAD
git status --short
```

Expected: no whitespace errors and a clean working tree.
