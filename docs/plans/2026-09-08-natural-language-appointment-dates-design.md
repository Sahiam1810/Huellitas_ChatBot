# Natural-language appointment dates design

## Goal

Allow Spanish-speaking users to provide an appointment date naturally, without requiring a fixed numeric format, and use the resolved local date to query the selected veterinarian's real availability.

## Approach

Use a deterministic Spanish date resolver in the appointments module. It remains independent from the chat model so operational booking behavior is repeatable, fast, testable, and unavailable-model failures cannot alter a date.

The resolver accepts explicit dates and date expressions embedded in a sentence. Initial coverage includes:

- ISO, `DD/MM/YYYY`, and `DD-MM-YYYY` dates;
- `hoy`, `mañana`, and `pasado mañana`;
- Spanish weekdays with `este`, `próximo`, or `de la próxima semana` wording;
- day-of-month expressions for this month, next month, or a named month;
- common accent and filler-word variants.

Resolution uses the configured display time zone (`America/Bogota` in the current environment). A date earlier than the local current date is invalid; the resolver never silently moves it to another month or year.

## Booking and rescheduling flow

Once the pet, service, and veterinarian are selected, the bot asks for a date using natural examples rather than demanding a format. The resolver returns either a concrete `date` or a typed failure (`unrecognized`, `ambiguous`, `past`, or `invalid`).

A valid result is passed to the existing appointments gateway together with the veterinarian ID and service ID already stored in the pending draft. The backend remains authoritative for available slots. If it returns no slots, the draft stays on the date step and preserves the prior selections so the user can try another date.

The same resolver and messages apply to new bookings and rescheduling.

## Error handling

- Past date: explain that the date already passed and request another.
- Invalid calendar date: explain that the date does not exist.
- Ambiguous or unrecognized expression: request a clearer date and show natural-language examples.
- No backend slots: state that the selected veterinarian has no availability that day and request another date.
- Gateway failure: preserve the existing safe backend error behavior.

## Testing

Unit tests use an injected reference date and cover relative phrases, weekdays, month/year boundaries, accents, full sentences, past dates, and invalid dates. Module tests prove that both booking and rescheduling send the resolved date plus the previously selected veterinarian/service IDs to the gateway and preserve state when no slots exist.
