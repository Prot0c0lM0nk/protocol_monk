from .base import MonkBaseError


class EventBusError(MonkBaseError):
    """
    Critical failure in the event distribution system.

    Used when:
    - A listener crashes and brings down the bus (rare).
    - An event loop deadlock is detected.
    """

    pass
