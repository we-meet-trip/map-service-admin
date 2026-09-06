"""Central operator management; service environments never own login sessions."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from app import accounts, audit
from app.config import environment_name, environment_names
from app.security import require_operator, require_owner

router = APIRouter(prefix="/api/v1", tags=["operators"])


class AccountBody(BaseModel):
    role: Literal["owner", "operator", "viewer"] = "viewer"
    environments: list[str] = Field(default_factory=list, max_length=20)
    active: bool = True
    password: str | None = None

    @field_validator("password")
    @classmethod
    def valid_password(cls, value):
        if value is not None and (len(value) < 12 or len(value.encode()) > 72):
            raise ValueError("password must have at least 12 characters and at most 72 UTF-8 bytes")
        return value

    @field_validator("environments")
    @classmethod
    def valid_environments(cls, value):
        if set(value) - set(environment_names()):
            raise ValueError("unknown environment")
        return sorted(set(value))


class NewAccount(AccountBody):
    username: str = Field(pattern=r"^[A-Za-z0-9_.@-]{1,100}$")


@router.get("/environments")
async def environments(operator: str = Depends(require_operator)):
    permissions = await accounts.permissions(operator)
    names = environment_names()
    if permissions and permissions["role"] != "owner":
        names = [n for n in names if n in permissions["allowed_environments"]]
    return {"selected": environment_name(), "environments": names}


@router.get("/operators")
async def operators(_: str = Depends(require_owner)):
    return {"items": await accounts.list_accounts()}


@router.post("/operators", status_code=201)
async def create(body: NewAccount, actor: str = Depends(require_owner)):
    if body.password is None:
        raise HTTPException(422, "password required")
    if body.role != "owner" and not body.environments:
        raise HTTPException(422, "at least one environment required")
    try:
        account_id = await accounts.create_account(body.username, body.password, body.role, body.environments, body.active)
    except IntegrityError as exc:
        raise HTTPException(409, "username already exists") from exc
    await audit.record(actor, "operator.create", target_id=str(account_id), params={"username": body.username, "role": body.role, "environments": body.environments})
    return {"id": account_id}


@router.patch("/operators/{account_id}")
async def update(account_id: int, body: AccountBody, actor: str = Depends(require_owner)):
    try:
        await accounts.update_account(account_id, active=body.active, role=body.role,
            environments=body.environments, password=body.password)
    except LookupError as exc:
        raise HTTPException(404, "account not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    await audit.record(actor, "operator.update", target_id=str(account_id), params={"active": body.active, "role": body.role, "environments": body.environments, "password_changed": body.password is not None})
    return {"id": account_id, "sessions_revoked": True}
