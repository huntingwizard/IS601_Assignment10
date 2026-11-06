"""
Tests for the FastAPI auth dependencies.

Instead of mocking token verification, these tests mint real JWTs with
User.create_access_token and hand the dependencies a tiny stand-in for a
database session, so the full "token -> user id -> row lookup" path runs.
"""

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException, status

from app.auth.dependencies import get_current_active_user, get_current_user
from app.models.user import User
from app.schemas.user import UserResponse

# Helpers
class StubQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *_criteria):
        return self

    def first(self):
        return self._row


class StubSession:
    """Mimics just enough of Session: db.query(Model).filter(...).first()."""

    def __init__(self, row=None):
        self._row = row
        self.queried_models = []

    def query(self, model):
        self.queried_models.append(model)
        return StubQuery(self._row)


def make_user(**overrides) -> User:
    now = datetime.utcnow()
    fields = {
        "id": uuid.uuid4(),
        "username": "alice",
        "email": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "password": "not-a-real-hash",
        "is_active": True,
        "is_verified": False,
        "created_at": now,
        "updated_at": now,
    }
    fields.update(overrides)
    return User(**fields)


def token_for(user: User, **kwargs) -> str:
    return User.create_access_token({"sub": str(user.id)}, **kwargs)


# get_current_user

def test_valid_token_returns_user_schema():
    user = make_user()
    db = StubSession(row=user)

    result = get_current_user(db=db, token=token_for(user))

    assert isinstance(result, UserResponse)
    assert result.id == user.id
    assert result.username == "alice"
    assert result.email == "alice@example.com"
    assert (result.first_name, result.last_name) == ("Alice", "Smith")
    assert result.is_active is True
    assert result.is_verified is False
    assert db.queried_models == [User]


def test_response_schema_hides_password():
    user = make_user()

    result = get_current_user(db=StubSession(row=user), token=token_for(user))

    assert "password" not in result.model_dump()


def test_valid_token_for_deleted_user_is_unauthorized():
    ghost = make_user()

    with pytest.raises(HTTPException) as caught:
        get_current_user(db=StubSession(row=None), token=token_for(ghost))

    assert caught.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert caught.value.detail == "Could not validate credentials"


@pytest.mark.parametrize("bad_token", ["", "garbage", "a.b.c"])
def test_unparseable_token_is_unauthorized_without_touching_db(bad_token):
    db = StubSession(row=make_user())

    with pytest.raises(HTTPException) as caught:
        get_current_user(db=db, token=bad_token)

    assert caught.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert db.queried_models == []


def test_expired_token_is_unauthorized():
    user = make_user()
    expired = token_for(user, expires_delta=timedelta(seconds=-1))

    with pytest.raises(HTTPException) as caught:
        get_current_user(db=StubSession(row=user), token=expired)

    assert caught.value.status_code == status.HTTP_401_UNAUTHORIZED


def test_unauthorized_response_asks_for_bearer_auth():
    with pytest.raises(HTTPException) as caught:
        get_current_user(db=StubSession(), token="garbage")

    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}


# get_current_active_user
def test_active_user_passes_through_unchanged():
    user = make_user()
    current = get_current_user(db=StubSession(row=user), token=token_for(user))

    assert get_current_active_user(current_user=current) is current


def test_inactive_user_is_rejected():
    user = make_user(is_active=False)
    current = get_current_user(db=StubSession(row=user), token=token_for(user))

    with pytest.raises(HTTPException) as caught:
        get_current_active_user(current_user=current)

    assert caught.value.status_code == status.HTTP_400_BAD_REQUEST
    assert caught.value.detail == "Inactive user"