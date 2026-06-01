class AutoTokenToolError(Exception):
    """Base exception for the package."""


class ConfigError(AutoTokenToolError):
    """Raised when configuration is invalid."""


class LoginError(AutoTokenToolError):
    """Raised when login cannot complete."""


class VerificationTimeout(LoginError):
    """Raised when no verification code is received before the configured timeout."""


class ServiceAPIError(AutoTokenToolError):
    """Raised when the target service API returns an error."""


class ServiceAuthError(ServiceAPIError):
    """Raised when a token is rejected."""
