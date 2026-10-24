from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ..config import settings
from .deps import SESSION_COOKIE, require_user
from .security import read_session_id, sign_session_id, verify_password

router = APIRouter()
SESSION_TTL = timedelta(hours=12)


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.post("/login", summary="Вход: ставит cookie сессии")
def login(payload: LoginInput, request: Request, response: Response) -> dict[str, str]:
    connection = request.app.state.engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, password_hash FROM app.users WHERE login = %s",
                (payload.login,),
            )
            user = cursor.fetchone()
            if user is None or not verify_password(payload.password, user[1]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid login or password",
                )
            cursor.execute("DELETE FROM app.sessions WHERE expires_at <= now()")
            session_id = uuid4()
            expires_at = datetime.now(timezone.utc) + SESSION_TTL
            cursor.execute(
                "INSERT INTO app.sessions (id, user_id, expires_at) VALUES (%s, %s, %s)",
                (session_id, user[0], expires_at),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    response.set_cookie(
        key=SESSION_COOKIE,
        value=sign_session_id(session_id),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        expires=expires_at,
        path="/",
    )
    return {"login": payload.login}


@router.get("/me", summary="Текущий пользователь")
def get_current_user(user: dict = Depends(require_user)) -> dict[str, str]:
    return {"login": user["login"]}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход")
def logout(request: Request, response: Response, user: dict = Depends(require_user)) -> None:
    del user
    session_id = read_session_id(request.cookies.get(SESSION_COOKIE))
    connection = request.app.state.engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM app.sessions WHERE id = %s", (session_id,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")