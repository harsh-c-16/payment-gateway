"""Common §3 error contract; SQL and provider text never reach the wire."""

from shared.contracts.common import ErrorBody, ErrorCode, ErrorResponse


class ServiceError(Exception):
    def __init__(self, status, code, message, *, details=None):
        super().__init__(message)
        self.status = status
        self.body = ErrorBody(
            code=code, message=message, retryable=status in {429, 503}, details=details or {}
        )

    def response(self, correlation_id):
        return ErrorResponse(error=self.body, correlation_id=correlation_id).model_dump(mode="json")


def storage_unavailable():
    return ServiceError(503, ErrorCode.STORAGE_UNAVAILABLE, "Catalogue storage is unavailable.")


def not_found(what="Resource"):
    return ServiceError(404, ErrorCode.NOT_FOUND, f"{what} not found.")
