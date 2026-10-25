class BackendError(Exception):
    def __init__(self, message: str, status_code: int = 503, code: str = "service_unavailable"):
        self.message, self.status_code, self.code = message, status_code, code
        super().__init__(message)
