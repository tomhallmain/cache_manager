"""
PassphraseManager._fallback_get_passphrase returns a str on the "create new"
branch but raw bytes on the "load existing" branch, while
BaseEncryptor._derive_key unconditionally calls passphrase.encode() on
whatever it's given. This fallback path (used for platforms other than
win32/darwin/linux) is also exercised from the *local* storage-wrapping
passphrase derivation during recovery-bundle import
(RecoveryBundleManager._import_app_entry -> PassphraseManager.get_passphrase),
so it can break a recovery import performed on such a platform.

This test forces the fallback path (by faking sys.platform) and exercises
the real encrypt-then-reload flow that triggers it: the first
get_passphrase() call (during key generation) returns a str and works fine;
the second call (during a later load_private_key(), simulating decrypting
the cache on a subsequent run) returns bytes and currently crashes
_derive_key with AttributeError.
"""

import utils.encryptor as encryptor_module
from utils.encryptor import PersonalStandardEncryptor

SERVICE_NAME = "FallbackPassphraseService"
APP_IDENTIFIER = "fallback_passphrase_app"


def test_fallback_passphrase_reload_does_not_crash_derive_key(tmp_path, monkeypatch):
    # _fallback_get_passphrase reads/writes under ~/.config/<service>/<app>.enc;
    # redirect HOME so this never touches the real user's home directory.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(encryptor_module.sys, "platform", "totally_fake_platform_for_test")

    # First call (inside generate_and_store_keys): passphrase file doesn't
    # exist yet -> "create new" branch -> returns str. Works today.
    PersonalStandardEncryptor.generate_and_store_keys(SERVICE_NAME, APP_IDENTIFIER)

    # Second call (inside load_private_key): passphrase file now exists ->
    # "load existing" branch -> returns bytes -> _derive_key's
    # passphrase.encode() raises AttributeError today.
    private_key = PersonalStandardEncryptor.load_private_key(SERVICE_NAME, APP_IDENTIFIER)
    assert isinstance(private_key, bytes)
    assert len(private_key) > 0
