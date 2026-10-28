"""Safe common errors; exception/SQL/provider text never enters the wire response."""

from shared.contracts.common import ErrorBody, ErrorCode, ErrorResponse


class ServiceError(Exception):
    def __init__(self, status: int, code: ErrorCode, message: str, *, details=None):
        super().__init__(message)
        self.status = status
        self.body = ErrorBody(
            code=code,
            message=message,
            retryable=status in {429, 503},
            details=details or {},
        )

    def response(self, correlation_id: str):
        return ErrorResponse(error=self.body, correlation_id=correlation_id).model_dump(mode="json")
