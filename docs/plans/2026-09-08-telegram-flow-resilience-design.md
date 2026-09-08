# Telegram Flow Resilience Design

## Problem

Two independent regressions break a private Telegram flow after identity verification:

1. LangGraph routes every authenticated message to an existing pending operation without first checking `expires_at`. A registration left pending for hours therefore captures a new appointment request and answers that the old registration expired.
2. The chatbot appointment and pet gateways still call the retired client-portal routes under `/api/*/mine`. Backend `develop` intentionally returns `410 Gone` from those routes, so the chatbot converts a valid business request into a generic availability error.

## Decision

Keep the retired portal routes unchanged and add an explicit Telegram-agent HTTP surface in the owning backend modules. A JWT minted by `AgentDelegatedIdentityProvider` will carry `token_use=telegram_agent`; a dedicated authorization policy will require that claim. Controllers will always derive the account from `sub`, and existing Application handlers will continue enforcing ownership. No client identifiers will be accepted from request bodies.

The chatbot will call the new `/api/bot/pets` and `/api/bot/appointments` contracts. Public catalog routes remain unchanged. Anonymous appointment action-code routes remain available and are not weakened.

At the main graph boundary, an expired pending operation will be removed before module selection. The current message will then be routed normally. This means a complete request such as “quiero agendar una cita” starts the appointment flow immediately instead of being consumed by an old pet-registration draft. If the message cannot be routed after expiration, the response will deterministically explain that the previous operation expired and ask the user to state the desired operation again; it will not ask the general LLM to interpret a dangling “sí” or number.

## Backend HTTP contract

All routes require the `TelegramAgentOnly` policy and derive `userAccountId` from JWT `sub`.

| Method | Route | Existing Application use case | Success |
|---|---|---|---|
| GET | `/api/bot/pets` | `GetMyPetsQuery` | 200 list |
| POST | `/api/bot/pets` | `RegisterMyPetCommand` | 201 profile |
| PATCH | `/api/bot/pets/{petId}` | `UpdateMyPetProfileCommand` | 200 profile |
| GET | `/api/bot/appointments?scope=` | `GetMyAppointmentsQuery` | 200 list |
| GET | `/api/bot/appointments/{appointmentId}` | `GetMyAppointmentByIdQuery` | 200 detail |
| GET | `/api/bot/appointments/booking/options` | `GetAppointmentBookingOptionsQuery` | 200 options |
| GET | `/api/bot/appointments/booking/slots` | `GetAppointmentBookingSlotsQuery` | 200 slots |
| POST | `/api/bot/appointments` | `CreateMyAppointmentCommand` | 201 appointment |
| PATCH | `/api/bot/appointments/{appointmentId}/cancel` | `CancelMyAppointmentCommand` | 204 |

The cancellation route is available only after Telegram identity OTP produced a delegated token and after the chatbot's explicit yes/no confirmation. Existing anonymous SMS action-code routes remain intact for external autoservice compatibility.

## Security and errors

- Ordinary login JWTs and guest Telegram JWTs receive 403 on bot-private routes.
- Missing or malformed `sub` receives 401.
- Ownership remains in Application handlers and produces the existing not-found/forbidden/conflict contracts.
- Tokens, user messages, OTP values and personally identifying data are not added to logs.
- No database schema or seed changes are required.

## Compatibility

- `/api/pets/mine*` and `/api/appointments/mine*` continue returning `410 ClientPortal.Gone`.
- Staff controllers and permissions are unchanged.
- Existing Telegram conversation IDs and Redis checkpoints remain valid; only expired pending operations are ignored.
- Guest access and public service-catalog behavior are unchanged.

## Verification

Use focused tests only:

- graph: expired pending plus new routable intent, and expired pending plus ambiguous continuation;
- token/policy: delegated claim is emitted only for verified Telegram identities;
- backend HTTP: successful bot pet/appointment actions, ownership derivation, ordinary/guest JWT denial, legacy 410 preservation;
- chatbot gateways: exact new paths and unchanged payload parsing;
- module regression: appointment booking and pet registration.

