class USMOSError(Exception):
    """Base exception for the USMOS SDK."""


class USMOSValidationError(USMOSError):
    """Raised when SDK input is invalid."""
