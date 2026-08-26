"""Domain errors for moderator auth. Routes map these to HTTP status codes."""


class AuthenticationError(Exception):
    """Base class for moderator authentication failures."""


class InvalidModeratorCredentialsError(AuthenticationError):
    """Group number and moderator phone did not identify an active moderator."""


class InvalidLoginChallengeError(AuthenticationError):
    """Challenge is invalid, expired, consumed, or has too many attempts."""


class InvalidSessionError(AuthenticationError):
    """Session token is absent, expired, revoked, or unknown."""
