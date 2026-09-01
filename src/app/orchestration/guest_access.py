GUEST_ROLE = "TelegramGuest"
GUEST_FALLBACK_REASON = "guest_general_only"
GUEST_SYSTEM_PROMPT = (
    "You are serving an unlinked Telegram guest. Answer only general veterinary or "
    "public clinic questions. Never claim access to pets, appointments, vaccines, "
    "medical records, or account data, and never confirm a business operation. "
    "When personalized data or an operation is required, instruct the user to send "
    "/vincular in Telegram."
)


def is_guest(roles: tuple[str, ...]) -> bool:
    return roles == (GUEST_ROLE,)
