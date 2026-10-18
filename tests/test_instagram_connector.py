"""Unit and regression tests for Dakota's Instagram connector and error handling."""
import pytest
from unittest.mock import patch, MagicMock
from src.connectors.instagram import (
    search_instagram,
    validate_instagram_credentials,
    _parse_meta_error,
    _sanitize_string,
    _get_api_version,
    DEFAULT_META_GRAPH_VERSION,
)


def test_meta_graph_version_default():
    """Verify META_GRAPH_VERSION defaults to v21.0 when unset."""
    with patch("src.connectors.instagram.env", return_value=""):
        version = _get_api_version()
        assert version == "v21.0"


def test_meta_graph_version_normalization():
    """Verify custom version is formatted with 'v' prefix."""
    with patch("src.connectors.instagram.env", return_value="22.0"):
        assert _get_api_version() == "v22.0"
    with patch("src.connectors.instagram.env", return_value="/v20.0"):
        assert _get_api_version() == "v20.0"


def test_sanitize_string_redacts_tokens():
    """Verify credentials and access tokens are completely redacted from strings."""
    secret = "EAAQ3zSampleToken123456789"
    raw_error = f"Error calling graph: access_token={secret} failed for user."
    sanitized = _sanitize_string(raw_error, token=secret)
    assert secret not in sanitized
    assert "[REDACTED" in sanitized


def test_validate_credentials_missing_all():
    """Verify validate_instagram_credentials reports both missing fields when empty."""
    with patch("src.connectors.instagram.env", return_value=""):
        res = validate_instagram_credentials()
        assert res["status"] == "missing_credentials"
        assert res["configured"] is False
        assert "INSTAGRAM_ACCESS_TOKEN" in res["missing_fields"]
        assert "INSTAGRAM_USER_ID" in res["missing_fields"]
        assert "setup_guide" in res


def test_validate_credentials_missing_user_id():
    """Verify missing user ID is specifically reported."""
    def fake_env(name, default=""):
        if name == "INSTAGRAM_ACCESS_TOKEN":
            return "sample_token"
        return ""

    with patch("src.connectors.instagram.env", side_effect=fake_env):
        res = validate_instagram_credentials()
        assert res["status"] == "missing_credentials"
        assert "INSTAGRAM_USER_ID" in res["missing_fields"]
        assert "INSTAGRAM_ACCESS_TOKEN" not in res["missing_fields"]


def test_validate_credentials_success():
    """Verify safe account validation succeeds on valid 200 response."""
    def fake_env(name, default=""):
        if name == "INSTAGRAM_ACCESS_TOKEN":
            return "valid_token"
        if name == "INSTAGRAM_USER_ID":
            return "17841400000000000"
        return ""

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "17841400000000000",
        "username": "dakota_intelligence",
        "name": "Dakota Terminal",
    }

    with patch("src.connectors.instagram.env", side_effect=fake_env):
        with patch("requests.get", return_value=mock_resp):
            res = validate_instagram_credentials()
            assert res["status"] == "connected"
            assert res["configured"] is True
            assert res["username"] == "dakota_intelligence"
            assert res["account_id"] == "17841400000000000"


def test_parse_meta_error_token_expired():
    """Verify OAuth code 190 / subcode 463 is diagnosed as token_expired."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {
        "error": {
            "message": "Error validating access token: Session has expired",
            "type": "OAuthException",
            "code": 190,
            "error_subcode": 463,
        }
    }
    status, msg = _parse_meta_error(mock_resp, "dummy_token")
    assert status == "token_expired"
    assert "regenerate" in msg.lower()


def test_parse_meta_error_insufficient_permissions():
    """Verify permission code 10 is diagnosed as insufficient_permissions."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.json.return_value = {
        "error": {
            "message": "(#10) Application does not have the capability to make this API call.",
            "code": 10,
        }
    }
    status, msg = _parse_meta_error(mock_resp, "dummy_token")
    assert status == "insufficient_permissions"
    assert "instagram_basic" in msg


def test_parse_meta_error_invalid_account_id():
    """Verify code 100 is diagnosed as invalid_account_id."""
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {
        "error": {
            "message": "Unsupported get request. Object with ID '123' does not exist.",
            "code": 100,
        }
    }
    status, msg = _parse_meta_error(mock_resp, "dummy_token")
    assert status == "invalid_account_id"
    assert "professional" in msg.lower()


def test_search_instagram_missing_credentials():
    """Verify search_instagram returns clean missing_credentials dict without crashing."""
    with patch("src.connectors.instagram.env", return_value=""):
        res = search_instagram("ZOMATO")
        assert res["status"] == "missing_credentials"
        assert res["result_count"] == 0
        assert "INSTAGRAM_ACCESS_TOKEN" in res["error"]
        assert "v21.0" in res["error"]
