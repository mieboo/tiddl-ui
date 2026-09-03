class AuthClientError(Exception):
    def __init__(
        self,
        status: int | None = None,
        error: str | None = None,
        sub_status: str | None = None,
        error_description: str | None = None,
        **kwargs,
    ):
        # Tidal 鉴权错误 payload 可能带额外字段,用 **kwargs 吸收避免构造崩溃
        self.status = status
        self.error = error
        self.sub_status = sub_status
        self.error_description = error_description

    def __str__(self):
        return (
            f"{self.error}, {self.error_description}, {self.status}/{self.sub_status}"
        )
