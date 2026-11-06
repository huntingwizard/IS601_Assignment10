"""
Unit tests for the Pydantic schemas (no database required).
"""

import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import app.schemas as schemas_pkg
from app.schemas.base import PasswordMixin, UserBase, UserCreate, UserLogin
from app.schemas.user import Token, TokenData, UserResponse
from app.schemas.user import UserLogin as LoginPayload

VALID_PASSWORD = "Str0ngPass"


def profile(**overrides) -> dict:
    data = {
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": "grace@example.com",
        "username": "ghopper",
    }
    data.update(overrides)
    return data


# UserBase
def test_user_base_accepts_valid_profile():
    user = UserBase(**profile())

    assert user.first_name == "Grace"
    assert user.last_name == "Hopper"
    assert user.email == "grace@example.com"
    assert user.username == "ghopper"


@pytest.mark.parametrize("email", ["plain", "missing@", "@nodomain.com", "a b@x.com"])
def test_user_base_rejects_bad_email(email):
    with pytest.raises(ValidationError, match="email"):
        UserBase(**profile(email=email))


@pytest.mark.parametrize("field", ["first_name", "last_name"])
def test_user_base_rejects_overlong_names(field):
    with pytest.raises(ValidationError, match=field):
        UserBase(**profile(**{field: "x" * 51}))


@pytest.mark.parametrize("username", ["ab", "u" * 51])
def test_user_base_enforces_username_length(username):
    with pytest.raises(ValidationError, match="username"):
        UserBase(**profile(username=username))


@pytest.mark.parametrize("field", ["first_name", "last_name", "email", "username"])
def test_user_base_requires_every_field(field):
    data = profile()
    del data[field]

    with pytest.raises(ValidationError, match=field):
        UserBase(**data)


def test_user_base_can_be_built_from_an_object():
    orm_like = SimpleNamespace(**profile())

    assert UserBase.model_validate(orm_like).username == "ghopper"


# PasswordMixin

def test_password_mixin_accepts_strong_password():
    assert PasswordMixin(password=VALID_PASSWORD).password == VALID_PASSWORD


@pytest.mark.parametrize(
    "password, message",
    [
        ("Ab1", "at least 6 characters"),
        ("nouppercase1", "uppercase"),
        ("NOLOWERCASE1", "lowercase"),
        ("NoDigitsHere", "digit"),
    ],
)
def test_password_mixin_rejects_weak_passwords(password, message):
    with pytest.raises(ValidationError, match=message):
        PasswordMixin(password=password)


def test_password_mixin_rejects_overlong_password():
    with pytest.raises(ValidationError, match="128"):
        PasswordMixin(password="Aa1" + "x" * 126)


def test_password_mixin_accepts_boundary_lengths():
    assert PasswordMixin(password="Abcde1").password == "Abcde1"  # 6 chars
    assert PasswordMixin(password="Aa1" + "x" * 125).password  # 128 chars


def test_password_mixin_requires_a_password():
    # Needs `raise ValueError("Password is required")` in PasswordMixin.
    with pytest.raises(ValidationError, match="Password is required"):
        PasswordMixin(password="")


# UserCreate and UserLogin (from schemas.base)
def test_user_create_combines_profile_and_password():
    created = UserCreate(**profile(), password=VALID_PASSWORD)

    assert created.username == "ghopper"
    assert created.password == VALID_PASSWORD


def test_user_create_requires_password():
    with pytest.raises(ValidationError):
        UserCreate(**profile())


def test_user_create_rejects_weak_password():
    with pytest.raises(ValidationError, match="digit"):
        UserCreate(**profile(), password="NoDigitsHere")


def test_user_create_rejects_bad_email_even_with_good_password():
    with pytest.raises(ValidationError, match="email"):
        UserCreate(**profile(email="nope"), password=VALID_PASSWORD)


def test_login_accepts_username_or_email_identifier():
    assert UserLogin(username="ghopper", password=VALID_PASSWORD).username == "ghopper"
    assert UserLogin(username="grace@example.com", password=VALID_PASSWORD)


def test_login_rejects_short_identifier():
    with pytest.raises(ValidationError, match="username"):
        UserLogin(username="gh", password=VALID_PASSWORD)


def test_login_rejects_weak_password():
    with pytest.raises(ValidationError):
        UserLogin(username="ghopper", password="weak")


# Response schemas (from schemas.user)

def response_fields(**overrides) -> dict:
    now = datetime(2025, 1, 1, 12, 0, 0)
    fields = {
        "id": uuid.uuid4(),
        "username": "ghopper",
        "email": "grace@example.com",
        "first_name": "Grace",
        "last_name": "Hopper",
        "is_active": True,
        "is_verified": False,
        "created_at": now,
        "updated_at": now,
    }
    fields.update(overrides)
    return fields


def test_user_response_accepts_complete_data():
    fields = response_fields()

    response = UserResponse(**fields)

    assert response.id == fields["id"]
    assert response.is_verified is False


def test_user_response_reads_from_object_attributes():
    fields = response_fields()

    response = UserResponse.model_validate(SimpleNamespace(**fields))

    assert response.email == "grace@example.com"


def test_user_response_has_no_password_fields():
    names = set(UserResponse.model_fields)

    assert "password" not in names
    assert "password_hash" not in names


def test_user_response_rejects_invalid_email():
    with pytest.raises(ValidationError, match="email"):
        UserResponse(**response_fields(email="broken"))


def test_user_response_rejects_non_uuid_id():
    with pytest.raises(ValidationError, match="id"):
        UserResponse(**response_fields(id="not-a-uuid"))


def test_token_defaults_to_bearer_and_nests_user():
    token = Token(access_token="abc.def.ghi", user=UserResponse(**response_fields()))

    assert token.token_type == "bearer"
    assert token.model_dump()["user"]["username"] == "ghopper"


def test_token_requires_user():
    with pytest.raises(ValidationError, match="user"):
        Token(access_token="abc.def.ghi")


def test_token_data_user_id_is_optional():
    assert TokenData().user_id is None

    some_id = uuid.uuid4()
    assert TokenData(user_id=some_id).user_id == some_id


def test_plain_login_payload_does_not_enforce_password_strength():
    assert LoginPayload(username="ghopper", password="x").password == "x"


# Package exports
def test_package_exports_resolve():
    for name in schemas_pkg.__all__:
        assert hasattr(schemas_pkg, name), f"app.schemas is missing {name}"