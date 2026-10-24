from typing import Any

from fastapi import HTTPException, Request, status

from .security import read_session_id

SESSION_COOKIE = "session"


def require_user(request: Request) -> dict[str, Any]:
    session_id = read_session_id(request.cookies.get(SESSION_COOKIE))
    if session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    connection = request.app.state.engine.raw_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT users.id, users.login
                FROM app.sessions AS sessions
                JOIN app.users AS users ON users.id = sessions.user_id
                WHERE sessions.id = %s AND sessions.expires_at > now()
                """,
                (session_id,),
            )
            row = cursor.fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return {"id": row[0], "login": row[1]}