"""
Integration tests for user registration, password hashing, login and JWTs.

Registration and login hit the real Postgres database through the
`db_session` fixture, which empties every table after each test.
"""

import uuid
from datetime import timedelta

import pytest
from jose import jwt

from app.models.user import User

GOOD_PASSWORD = "GoodPass1"


def make_payload(n: int = 1, **overrides) -> dict:
    """Registration data for a unique, valid member."""
    data = {
        "first_name": "Member",
        "last_name": f"Number{n}",
        "email": f"member{n}@example.com",
        "username": f"member_{n}",
        "password": GOOD_PASSWORD,
    }
    data.update(overrides)
    return data


@pytest.fixture
def member(db_session):
    """A registered and committed user, plus the data used to create it."""
    payload = make_payload()
    user = User.register(db_session, payload)
    db_session.commit()
    return user, payload



# Password hashing
def test_hash_is_not_the_plain_password():
    hashed = User.hash_password(GOOD_PASSWORD)

    assert hashed != GOOD_PASSWORD
    assert hashed.startswith("$2")  # bcrypt prefix


def test_hashing_same_password_twice_gives_different_hashes():
    assert User.hash_password(GOOD_PASSWORD) != User.hash_password(GOOD_PASSWORD)


def test_verify_password_accepts_only_the_original():
    user = User(password=User.hash_password(GOOD_PASSWORD))

    assert user.verify_password(GOOD_PASSWORD) is True
    assert user.verify_password("BadPass1") is False
    assert user.verify_password("") is False



# Registration: happy path
def test_register_populates_user_fields(db_session):
    payload = make_payload(5)
    user = User.register(db_session, payload)
    db_session.commit()

    assert isinstance(user.id, uuid.UUID)
    assert user.first_name == payload["first_name"]
    assert user.last_name == payload["last_name"]
    assert user.email == payload["email"]
    assert user.username == payload["username"]
    assert user.is_active is True
    assert user.is_verified is False


def test_register_stores_hash_not_plaintext(member):
    user, payload = member

    assert user.password != payload["password"]
    assert user.verify_password(payload["password"]) is True


def test_registered_user_can_be_found_again(db_session, member):
    user, payload = member

    found = db_session.query(User).filter_by(username=payload["username"]).one()

    assert found.id == user.id


# Registration: rejected input
def test_duplicate_email_is_rejected(db_session, member):
    clash = make_payload(2, email=member[1]["email"])

    with pytest.raises(ValueError, match="Username or email already exists"):
        User.register(db_session, clash)


def test_duplicate_username_is_rejected(db_session, member):
    clash = make_payload(2, username=member[1]["username"])

    with pytest.raises(ValueError, match="Username or email already exists"):
        User.register(db_session, clash)


@pytest.mark.parametrize(
    "password, message",
    [
        ("Ab1", "at least 6 characters"),
        ("alllower1", "uppercase"),
        ("ALLUPPER1", "lowercase"),
        ("NoDigitsHere", "digit"),
    ],
)
def test_weak_passwords_are_rejected(db_session, password, message):
    with pytest.raises(ValueError, match=message):
        User.register(db_session, make_payload(password=password))


def test_missing_password_is_rejected(db_session):
    payload = make_payload()
    del payload["password"]

    with pytest.raises(ValueError, match="at least 6 characters"):
        User.register(db_session, payload)


def test_malformed_email_is_rejected(db_session):
    with pytest.raises(ValueError, match="email"):
        User.register(db_session, make_payload(email="not-an-email"))


def test_too_short_username_is_rejected(db_session):
    with pytest.raises(ValueError, match="username"):
        User.register(db_session, make_payload(username="ab"))


def test_rejected_registration_leaves_no_row(db_session):
    with pytest.raises(ValueError):
        User.register(db_session, make_payload(password="weak"))

    assert db_session.query(User).count() == 0


# Authentication
def test_login_with_username(db_session, member):
    user, payload = member

    result = User.authenticate(db_session, payload["username"], payload["password"])

    assert result is not None
    assert result["token_type"] == "bearer"
    assert result["user"]["id"] == user.id
    assert User.verify_token(result["access_token"]) == user.id


def test_login_with_email(db_session, member):
    _, payload = member

    result = User.authenticate(db_session, payload["email"], payload["password"])

    assert result is not None
    assert result["user"]["email"] == payload["email"]


def test_login_response_never_exposes_password(db_session, member):
    _, payload = member

    result = User.authenticate(db_session, payload["username"], payload["password"])

    assert "password" not in result["user"]
    assert "password_hash" not in result["user"]


def test_login_with_wrong_password_fails(db_session, member):
    _, payload = member

    assert User.authenticate(db_session, payload["username"], "WrongPass1") is None


def test_login_with_unknown_account_fails(db_session):
    assert User.authenticate(db_session, "ghost", GOOD_PASSWORD) is None


def test_successful_login_sets_last_login(db_session, member):
    user, payload = member
    assert user.last_login is None

    User.authenticate(db_session, payload["username"], payload["password"])
    db_session.refresh(user)

    assert user.last_login is not None


def test_failed_login_does_not_set_last_login(db_session, member):
    user, payload = member

    User.authenticate(db_session, payload["username"], "WrongPass1")
    db_session.refresh(user)

    assert user.last_login is None



# JSON web tokens
def test_token_round_trip_returns_same_id():
    user_id = uuid.uuid4()

    token = User.create_access_token({"sub": str(user_id)})

    assert User.verify_token(token) == user_id


def test_expired_token_is_rejected():
    token = User.create_access_token(
        {"sub": str(uuid.uuid4())}, expires_delta=timedelta(seconds=-5)
    )

    assert User.verify_token(token) is None


def test_token_signed_with_another_key_is_rejected():
    forged = jwt.encode({"sub": str(uuid.uuid4())}, "some-other-key", algorithm="HS256")

    assert User.verify_token(forged) is None


def test_token_with_replaced_signature_is_rejected():
    token = User.create_access_token({"sub": str(uuid.uuid4())})
    header, body, _ = token.split(".")

    assert User.verify_token(f"{header}.{body}.{'A' * 43}") is None


def test_token_without_subject_is_rejected():
    assert User.verify_token(User.create_access_token({"role": "admin"})) is None


def test_token_with_non_uuid_subject_is_rejected():
    assert User.verify_token(User.create_access_token({"sub": "12345"})) is None


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "invalid.token.string"])
def test_garbage_tokens_are_rejected(garbage):
    assert User.verify_token(garbage) is None



# Representation
def test_repr_shows_name_and_email(member):
    user, payload = member

    text = repr(user)

    assert payload["email"] in text
    assert payload["first_name"] in text