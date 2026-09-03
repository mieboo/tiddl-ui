class ApiError(Exception):
    def __init__(
        self,
        status: int | None = None,
        subStatus: str | None = None,
        userMessage: str | None = None,
        **kwargs,
    ):
        # Tidal 错误 payload 可能缺键或带额外字段(timestamp/error/path),
        # 给默认值并用 **kwargs 吸收,避免在报错时反而抛 TypeError。
        self.status = status
        self.sub_status = subStatus
        self.user_message = userMessage or ""

    def __str__(self):
        return f"{self.user_message}, {self.status}/{self.sub_status}"
