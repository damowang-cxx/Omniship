from fastapi import Request


def get_request_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


def get_request_user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")

