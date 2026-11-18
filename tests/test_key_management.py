"""API-key lifecycle: secure storage, masking and honest failure modes."""

from __future__ import annotations

import sys

import pytest

from memory_agent.config import AgentSettings, InMemorySettingsStore, JsonSettingsStore
from memory_agent.core.exceptions import (
    CredentialStoreUnavailableError,
    InvalidRequestError,
    MissingApiKeyError,
)
from memory_agent.security.api_key_manager import (
    ApiKeyManager,
    DpapiCredentialStore,
    InMemoryCredentialStore,
    LinuxSecretServiceStore,
    MacKeychainStore,
    create_default_credential_store,
)

SECRET = "AIzaSyD-not-a-real-key-1234567890"


def test_in_memory_store_round_trip_and_delete():
    store = InMemoryCredentialStore()
    manager = ApiKeyManager(store)
    manager.store_key("gemini", SECRET)
    assert manager.has_key("gemini") is True
    assert manager.get_key("gemini") == SECRET
    manager.delete_key("gemini")
    assert manager.has_key("gemini") is False
    with pytest.raises(MissingApiKeyError):
        manager.require_key("gemini")


def test_masked_key_never_reveals_the_secret():
    manager = ApiKeyManager(InMemoryCredentialStore())
    manager.store_key("gemini", SECRET)
    masked = manager.masked_key("gemini")
    assert masked is not None
    assert SECRET not in masked
    assert masked.endswith(SECRET[-4:])
    assert masked.startswith("•")


def test_short_or_whitespace_keys_are_rejected():
    manager = ApiKeyManager(InMemoryCredentialStore())
    with pytest.raises(InvalidRequestError):
        manager.store_key("gemini", "short")
    with pytest.raises(InvalidRequestError):
        manager.store_key("gemini", "has a space in it")


def test_unknown_provider_is_rejected():
    manager = ApiKeyManager(InMemoryCredentialStore())
    with pytest.raises(Exception):
        manager.store_key("not-a-provider", SECRET)


def test_unavailable_secure_storage_never_falls_back_to_plaintext(tmp_path):
    store = LinuxSecretServiceStore()
    manager = ApiKeyManager(store)
    assert manager.store_available is False
    with pytest.raises(CredentialStoreUnavailableError):
        manager.store_key("gemini", SECRET)
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
def test_dpapi_round_trip_and_ciphertext_on_disk(tmp_path):
    path = tmp_path / "credentials" / "agent_keys.json"
    store = DpapiCredentialStore(path)
    assert store.is_available is True, store.unavailable_reason
    manager = ApiKeyManager(store)
    manager.store_key("gemini", SECRET)

    # The key is usable...
    assert manager.get_key("gemini") == SECRET
    # ...but never stored as plaintext.
    raw = path.read_bytes()
    assert SECRET.encode("utf-8") not in raw
    assert b"AIzaSy" not in raw
    assert path.read_text(encoding="utf-8").count("cipher") == 0

    manager.delete_key("gemini")
    assert manager.get_key("gemini") is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
def test_dpapi_store_handles_multiple_providers(tmp_path):
    store = DpapiCredentialStore(tmp_path / "keys.json")
    manager = ApiKeyManager(store)
    manager.store_key("gemini", "gemini-key-12345678")
    manager.store_key("openai", "sk-openai-key-87654321")
    assert manager.get_key("gemini") == "gemini-key-12345678"
    assert manager.get_key("openai") == "sk-openai-key-87654321"
    assert manager.delete_key  # callable
    manager.delete_key("gemini")
    assert manager.get_key("openai") == "sk-openai-key-87654321"


def test_default_store_is_secure_per_platform(tmp_path):
    store = create_default_credential_store(tmp_path)
    if sys.platform == "win32":
        assert isinstance(store, DpapiCredentialStore)
    elif sys.platform == "darwin":
        assert isinstance(store, MacKeychainStore)
    else:
        assert isinstance(store, LinuxSecretServiceStore)


def test_manager_repr_never_contains_secrets():
    manager = ApiKeyManager(InMemoryCredentialStore())
    manager.store_key("gemini", SECRET)
    assert SECRET not in repr(manager)


def test_settings_never_persist_secrets(tmp_path):
    path = tmp_path / "agent_settings.json"
    store = JsonSettingsStore(path)
    settings = AgentSettings(enabled=True, provider_id="gemini", models={"gemini": "gemini-2.5-flash"})
    store.save(settings)
    text = path.read_text(encoding="utf-8")
    assert "api_key" not in text.lower()
    assert "AIza" not in text

    with pytest.raises(Exception):
        settings.model_copy(update={"models": {"gemini": SECRET}}).assert_secret_free()


def test_connection_test_without_a_key_reports_clearly():
    manager = ApiKeyManager(InMemoryCredentialStore())
    result = manager.test_connection("gemini")
    assert result.ok is False
    assert "no api key" in result.message.lower()


def test_settings_json_store_round_trip(tmp_path):
    store = JsonSettingsStore(tmp_path / "settings.json")
    store.save(AgentSettings(enabled=True, provider_id="local", models={"local": "llama3"}))
    loaded = store.load()
    assert loaded.provider_id == "local"
    assert loaded.model_for() == "llama3"


def test_in_memory_settings_store_isolated_copy():
    store = InMemorySettingsStore(AgentSettings(provider_id="openai"))
    loaded = store.load().model_copy(update={"provider_id": "local"})
    assert loaded.provider_id == "local"
    assert store.load().provider_id == "openai"
