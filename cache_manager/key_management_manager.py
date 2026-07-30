import glob
import hashlib
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import keyring

from cache_manager.cache_backup_manager import sanitize_filename
from cache_manager.recovery_bundle_manager import RecoveryBundleManager
from utils.encryption_strategy import EncryptionStrategy
from utils.encryptor import ENCRYPTOR_CLASSES, ENCRYPTOR_TYPE_KEY, namespaced_key
from utils.logging_setup import get_logger
from utils.translations import _

logger = get_logger(__name__)

ROTATED_AT_KEY = "key_rotated_at"

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_VERIFY_FAILED = "verify_failed"
STATUS_NOT_APPLICABLE = "not_applicable"


class KeyManagementManager:
    """Inspect and rotate the keyring-stored keypair behind a managed application."""

    @classmethod
    def get_key_info(cls, app: Dict) -> Dict:
        service_name = app.get("service_name")
        app_identifier = app.get("app_identifier")
        configured_strategy = EncryptionStrategy.from_string(app.get("encryption_strategy"))

        info = {
            "configured_strategy": configured_strategy,
            "actual_type": None,
            "status": STATUS_NOT_APPLICABLE,
            "fingerprint": None,
            "rotated_at": keyring.get_password(service_name, namespaced_key(app_identifier, ROTATED_AT_KEY)),
        }

        if configured_strategy in (EncryptionStrategy.NONE, EncryptionStrategy.UNKNOWN):
            return info

        actual_type = keyring.get_password(service_name, namespaced_key(app_identifier, ENCRYPTOR_TYPE_KEY))
        info["actual_type"] = actual_type
        if not actual_type:
            info["status"] = STATUS_MISSING
            return info

        try:
            encryptor_cls = RecoveryBundleManager._resolve_encryptor_class(actual_type)
            public_key = encryptor_cls._retrieve_large_data(service_name, app_identifier, encryptor_cls.PUBLIC_KEY)
            if not public_key:
                info["status"] = STATUS_MISSING
                return info
            info["fingerprint"] = hashlib.sha256(public_key).hexdigest()[:16]

            private_key = encryptor_cls.load_private_key(service_name, app_identifier)
            encryptor_cls.verify_keys(public_key, private_key)
            info["status"] = STATUS_OK
        except Exception as e:
            logger.warning(_("Key check failed for '{0}': {1}").format(app.get("name"), str(e)))
            info["status"] = STATUS_VERIFY_FAILED

        return info

    @staticmethod
    def collect_rotation_targets(app: Dict, cache_backup_manager) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Every file currently encrypted under this app's key: the live cache
        plus its local and external backups. Returns (targets, skipped)."""
        targets = []
        skipped = []
        seen = set()

        def add(path):
            real_path = os.path.abspath(path)
            if real_path not in seen:
                seen.add(real_path)
                targets.append(path)

        cache_location = app.get("cache_location")
        if cache_location and os.path.isfile(cache_location):
            add(cache_location)

        for backup in cache_backup_manager.list_backups(app["name"]):
            path = backup.get("path")
            if not path:
                continue
            if os.path.isfile(path):
                add(path)
            else:
                skipped.append((path, _("backup file not found")))

        external_dir = cache_backup_manager.get_external_backup_dir()
        if external_dir:
            if os.path.isdir(external_dir):
                safe_name = sanitize_filename(app["name"])
                for entry in glob.glob(os.path.join(external_dir, f"{safe_name}_*.enc")):
                    add(entry)
            else:
                skipped.append((external_dir, _("external backup directory not reachable")))

        return targets, skipped

    @classmethod
    def rotate_key(cls, app: Dict, cache_backup_manager) -> Dict:
        """Generate a new keypair, re-encrypt every file under the old one
        (verifying each before trusting it), swap them all in, then retire
        the old key. Nothing changes if any re-encryption fails before the swap."""
        service_name = app["service_name"]
        app_identifier = app["app_identifier"]
        app_name = app["name"]
        configured_strategy = EncryptionStrategy.from_string(app.get("encryption_strategy"))

        if configured_strategy in (EncryptionStrategy.NONE, EncryptionStrategy.UNKNOWN):
            raise ValueError(_("'{0}' has no encryption keys to rotate.").format(app_name))

        actual_type = keyring.get_password(service_name, namespaced_key(app_identifier, ENCRYPTOR_TYPE_KEY))
        if not actual_type:
            raise ValueError(_("No existing key material found for '{0}'.").format(app_name))

        encryptor_cls = RecoveryBundleManager._resolve_encryptor_class(actual_type)
        old_public_key = encryptor_cls._retrieve_large_data(service_name, app_identifier, encryptor_cls.PUBLIC_KEY)
        old_private_key = encryptor_cls.load_private_key(service_name, app_identifier)
        encryptor_cls.verify_keys(old_public_key, old_private_key)

        targets, skipped = cls.collect_rotation_targets(app, cache_backup_manager)
        new_public_key, new_private_key = encryptor_cls.generate_keypair()

        temp_paths = []
        try:
            for path in targets:
                temp_path = f"{path}.rotating.tmp"
                plaintext = encryptor_cls.decrypt_data_from_file(old_private_key, path)
                encryptor_cls.encrypt_data(plaintext, new_public_key, temp_path)
                encryptor_cls.decrypt_data_from_file(new_private_key, temp_path)  # verify before trusting it
                temp_paths.append((path, temp_path))

            for path, temp_path in temp_paths:
                os.replace(temp_path, path)
        except Exception:
            for _path, temp_path in temp_paths:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            raise

        RecoveryBundleManager._purge_existing_key_material(service_name, app_identifier)
        encryptor_cls.store_key_pair(service_name, app_identifier, new_public_key, new_private_key)
        keyring.set_password(
            service_name, namespaced_key(app_identifier, ROTATED_AT_KEY), datetime.now(timezone.utc).isoformat()
        )
        ENCRYPTOR_CLASSES.pop(f"{service_name}:::{app_identifier}", None)

        return {"re_encrypted": targets, "skipped": skipped}
