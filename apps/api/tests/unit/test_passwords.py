from __future__ import annotations

import pytest

from app.core import security
from app.schemas.auth import LoginBody, SignupBody


class TestPasswordHash:
    def test_round_trip_and_format(self) -> None:
        stored = security.hash_password("throwaway-pw-1")
        scheme, n, r, p, salt, digest = stored.split("$")
        assert (scheme, n, r, p) == ("scrypt", str(security.SCRYPT_N), "8", "1")
        assert salt and digest and "throwaway" not in stored
        assert security.verify_password("throwaway-pw-1", stored)
        assert not security.verify_password("throwaway-pw-2", stored)

    def test_salt_is_random(self) -> None:
        assert security.hash_password("same-pw-1") != security.hash_password("same-pw-1")

    @pytest.mark.parametrize("stored", [None, "", "garbage", "bcrypt$1$2$3$a$b", "scrypt$x$8$1$AA==$AA=="])
    def test_malformed_hash_never_matches(self, stored: str | None) -> None:
        assert not security.verify_password("anything1", stored)

    def test_dummy_hash_is_stable_and_matches_nothing_typed(self) -> None:
        assert security.dummy_password_hash() == security.dummy_password_hash()
        assert not security.verify_password("password1", security.dummy_password_hash())


class TestSignupRules:
    def test_login_id_is_trimmed_and_lowercased(self) -> None:
        body = SignupBody(login_id="  Jjan.Test_1  ", password="abcd1234")
        assert body.login_id == "jjan.test_1" and body.nickname is None

    @pytest.mark.parametrize("login_id", ["abc", "a" * 21, "짠이짠이", "has space", "semi;colon"])
    def test_bad_login_ids(self, login_id: str) -> None:
        with pytest.raises(ValueError):
            SignupBody(login_id=login_id, password="abcd1234")

    @pytest.mark.parametrize("password", ["abc123", "abcdefgh", "12345678", "a1" * 37])
    def test_bad_passwords(self, password: str) -> None:
        with pytest.raises(ValueError):
            SignupBody(login_id="jjan", password=password)

    def test_blank_nickname_falls_back(self) -> None:
        assert SignupBody(login_id="jjan", password="abcd1234", nickname="  ").nickname is None

    def test_login_body_normalizes_the_id(self) -> None:
        assert LoginBody(login_id=" JJAN ", password="x").login_id == "jjan"
