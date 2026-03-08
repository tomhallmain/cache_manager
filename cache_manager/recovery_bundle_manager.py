import base64
import glob
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import keyring

from utils.encryptor import (
    ENCRYPTOR_CLASSES,
    ENCRYPTOR_TYPE_KEY,
    KeyEncapsulation,
    PassphraseManager,
    PersonalQuantumEncryptor,
    PersonalStandardEncryptor,
    SymmetricEncryptor,
    get_key_base,
    namespaced_key,
)
from utils.logging_setup import get_logger
from utils.translations import I18N
from cache_manager.cache_backup_manager import sanitize_filename

logger = get_logger(__name__)
_ = I18N._


class RecoveryBundleManager:
    """Export/import portable encrypted recovery bundles for app decryptability."""

    SCHEMA_VERSION = 1
    BUNDLE_FILENAME = "cache_recovery.bundle.enc"
    PASSPHRASE_SERVICE = "cache_manager_recovery_bundle"
    PASSPHRASE_KEY = "recovery_passphrase"

    @classmethod
    def get_saved_passphrase(cls) -> Optional[str]:
        """Get saved recovery-bundle passphrase from secure keyring storage."""
        return keyring.get_password(cls.PASSPHRASE_SERVICE, cls.PASSPHRASE_KEY)

    @classmethod
    def set_saved_passphrase(cls, passphrase: str):
        """Persist recovery-bundle passphrase in secure keyring storage."""
        if not passphrase:
            raise ValueError(_("Recovery passphrase cannot be empty."))
        keyring.set_password(cls.PASSPHRASE_SERVICE, cls.PASSPHRASE_KEY, passphrase)

    @classmethod
    def get_default_bundle_path(cls, backup_dir: str) -> str:
        """Get default recovery bundle path for a given backup directory."""
        return os.path.join(os.path.abspath(backup_dir), cls.BUNDLE_FILENAME)

    @classmethod
    def export_bundle(cls, applications: List[Dict], bundle_path: str, recovery_passphrase: str) -> Dict:
        """
        Export decryptability metadata + key material for applications to an encrypted bundle.
        The resulting file is portable across machines when imported with the same passphrase.
        """
        if not recovery_passphrase:
            raise ValueError(_("Recovery passphrase is required for bundle export."))

        payload_apps = []
        errors = []

        for app in applications:
            try:
                payload_apps.append(cls._build_export_entry(app))
            except Exception as e:
                app_name = app.get("name") or app.get("app_identifier") or "unknown"
                errors.append(f"{app_name}: {str(e)}")
                logger.error(_("Failed to export key material for app '{0}': {1}").format(app_name, str(e)))

        payload = {
            "schema_version": cls.SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "applications": payload_apps,
        }
        payload_sha256 = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        envelope = {
            "payload": payload,
            "payload_sha256": payload_sha256,
        }

        bundle_dir = os.path.dirname(os.path.abspath(bundle_path))
        if bundle_dir:
            os.makedirs(bundle_dir, exist_ok=True)

        SymmetricEncryptor.encrypt_data(
            data=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            passphrase=recovery_passphrase.encode("utf-8"),
            output_path=bundle_path,
            compress=True,
        )

        return {
            "bundle_path": os.path.abspath(bundle_path),
            "exported_count": len(payload_apps),
            "error_count": len(errors),
            "errors": errors,
        }

    @classmethod
    def import_bundle(cls, bundle_path: str, recovery_passphrase: str, overwrite_existing: bool = False) -> Dict:
        """
        Import a previously exported recovery bundle and rehydrate local keyring key material.
        """
        if not recovery_passphrase:
            raise ValueError(_("Recovery passphrase is required for bundle import."))

        envelope_bytes = SymmetricEncryptor.decrypt_data(
            encrypted_file=bundle_path,
            passphrase=recovery_passphrase.encode("utf-8"),
        )
        envelope = json.loads(envelope_bytes.decode("utf-8"))

        payload = envelope.get("payload")
        expected_sha = envelope.get("payload_sha256")
        if payload is None or not expected_sha:
            raise ValueError(_("Invalid recovery bundle format."))

        actual_sha = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if actual_sha != expected_sha:
            raise ValueError(_("Recovery bundle integrity check failed."))

        schema_version = payload.get("schema_version")
        if schema_version != cls.SCHEMA_VERSION:
            raise ValueError(_("Unsupported recovery bundle schema version: {0}").format(schema_version))

        imported = 0
        skipped = 0
        failed = 0
        errors = []

        bundle_dir = os.path.dirname(os.path.abspath(bundle_path))
        for app_entry in payload.get("applications", []):
            try:
                status = cls._import_app_entry(
                    app_entry,
                    overwrite_existing=overwrite_existing,
                    bundle_dir=bundle_dir,
                    restore_cache_file=True,
                )
                if status == "imported":
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                failed += 1
                app_name = app_entry.get("name") or app_entry.get("app_identifier") or "unknown"
                error_text = f"{app_name}: {str(e)}"
                errors.append(error_text)
                logger.error(_("Failed to import recovery material for '{0}': {1}").format(app_name, str(e)))

        return {
            "imported_count": imported,
            "skipped_count": skipped,
            "failed_count": failed,
            "errors": errors,
        }

    @classmethod
    def _build_export_entry(cls, app: Dict) -> Dict:
        service_name = app.get("service_name")
        app_identifier = app.get("app_identifier")
        if not service_name or not app_identifier:
            raise ValueError(_("Missing service/app identifier in application config."))

        encryptor_type = keyring.get_password(
            service_name,
            namespaced_key(app_identifier, ENCRYPTOR_TYPE_KEY),
        )
        if not encryptor_type:
            raise ValueError(_("No stored encryptor type found in keyring."))

        encryptor_cls = cls._resolve_encryptor_class(encryptor_type)
        public_key = encryptor_cls._retrieve_large_data(service_name, app_identifier, encryptor_cls.PUBLIC_KEY)
        if public_key is None:
            raise ValueError(_("Unable to retrieve public key from keyring."))
        private_key = encryptor_cls.load_private_key(service_name, app_identifier)

        return {
            "name": app.get("name"),
            "service_name": service_name,
            "app_identifier": app_identifier,
            "cache_location": app.get("cache_location"),
            "encryption_strategy": app.get("encryption_strategy"),
            "encryptor_type": encryptor_type,
            "public_key_b64": base64.b64encode(public_key).decode("ascii"),
            "private_key_b64": base64.b64encode(private_key).decode("ascii"),
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def _import_app_entry(
        cls,
        app_entry: Dict,
        overwrite_existing: bool = False,
        bundle_dir: Optional[str] = None,
        restore_cache_file: bool = True,
    ) -> str:
        service_name = app_entry.get("service_name")
        app_identifier = app_entry.get("app_identifier")
        encryptor_type = app_entry.get("encryptor_type")
        if not service_name or not app_identifier or not encryptor_type:
            raise ValueError(_("Recovery entry is missing required fields."))

        existing_type = keyring.get_password(service_name, namespaced_key(app_identifier, ENCRYPTOR_TYPE_KEY))
        if existing_type and not overwrite_existing:
            return "skipped_existing"

        if overwrite_existing:
            cls._purge_existing_key_material(service_name, app_identifier)

        encryptor_cls = cls._resolve_encryptor_class(encryptor_type)
        public_key = base64.b64decode(app_entry["public_key_b64"])
        private_key = base64.b64decode(app_entry["private_key_b64"])

        passphrase = PassphraseManager.get_passphrase(service_name, app_identifier)
        salt = os.urandom(16)
        storage_key = encryptor_cls._derive_key(passphrase, salt, 32)
        nonce = os.urandom(12)

        cipher = Cipher(algorithms.AES(storage_key), modes.GCM(nonce), default_backend())
        encryptor = cipher.encryptor()
        encrypted_priv = encryptor.update(private_key) + encryptor.finalize()

        keyring.set_password(service_name, namespaced_key(app_identifier, encryptor_cls.SALT_KEY), salt.hex())
        keyring.set_password(service_name, namespaced_key(app_identifier, encryptor_cls.NONCE_KEY), nonce.hex())
        keyring.set_password(service_name, namespaced_key(app_identifier, encryptor_cls.TAG_KEY), encryptor.tag.hex())
        keyring.set_password(service_name, namespaced_key(app_identifier, ENCRYPTOR_TYPE_KEY), encryptor_type)
        cls._store_large_data(service_name, app_identifier, encryptor_cls.ENCRYPTED_PRIV_KEY, encrypted_priv)
        cls._store_large_data(service_name, app_identifier, encryptor_cls.PUBLIC_KEY, public_key)

        cls._verify_imported_key_material(service_name, app_identifier, encryptor_cls, public_key)
        if restore_cache_file:
            cls._restore_cache_file_if_available(
                app_entry=app_entry,
                encryptor_cls=encryptor_cls,
                service_name=service_name,
                app_identifier=app_identifier,
                bundle_dir=bundle_dir,
            )

        cache_key = f"{service_name}:::{app_identifier}"
        ENCRYPTOR_CLASSES.pop(cache_key, None)
        return "imported"

    @classmethod
    def _verify_imported_key_material(cls, service_name: str, app_identifier: str, encryptor_cls, public_key: bytes):
        """Validate imported key material can be loaded and matches."""
        private_key = encryptor_cls.load_private_key(service_name, app_identifier)
        encryptor_cls.verify_keys(public_key, private_key)

    @classmethod
    def _restore_cache_file_if_available(
        cls,
        app_entry: Dict,
        encryptor_cls,
        service_name: str,
        app_identifier: str,
        bundle_dir: Optional[str],
    ):
        """Restore latest matching backup file to configured cache location and verify decryptability."""
        cache_location = app_entry.get("cache_location")
        app_name = app_entry.get("name")
        if not cache_location or not app_name or not bundle_dir:
            return

        backup_path = cls._find_latest_backup_for_app(bundle_dir, app_name)
        if not backup_path:
            logger.warning(_("No backup file found in bundle directory for '{0}'").format(app_name))
            return

        private_key = encryptor_cls.load_private_key(service_name, app_identifier)
        try:
            # Ensure imported keys can decrypt this backup before restoring it.
            encryptor_cls.decrypt_data_from_file(private_key, backup_path)
        except Exception as e:
            raise ValueError(_("Imported keys cannot decrypt backup file for '{0}': {1}").format(app_name, str(e)))

        cache_dir = os.path.dirname(cache_location)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        with open(backup_path, "rb") as src, open(cache_location, "wb") as dst:
            dst.write(src.read())

    @classmethod
    def _find_latest_backup_for_app(cls, bundle_dir: str, app_name: str) -> Optional[str]:
        """Find newest backup file for an app based on backup naming convention."""
        safe_name = sanitize_filename(app_name)
        pattern = os.path.join(bundle_dir, f"{safe_name}_*.enc")
        matches = glob.glob(pattern)
        if not matches:
            return None
        matches.sort(key=os.path.getmtime, reverse=True)
        return matches[0]

    @staticmethod
    def _resolve_encryptor_class(encryptor_type: str):
        if encryptor_type == PersonalStandardEncryptor.KEY_TYPE:
            return PersonalStandardEncryptor
        if encryptor_type == PersonalQuantumEncryptor.KEY_TYPE:
            if not KeyEncapsulation:
                raise RuntimeError(_("Quantum key material requires OQS support on this machine."))
            return PersonalQuantumEncryptor
        raise ValueError(_("Unsupported encryptor type: {0}").format(encryptor_type))

    @classmethod
    def _store_large_data(cls, service_name: str, app_identifier: str, key: str, data: bytes):
        key_base = get_key_base(app_identifier, key)
        hex_data = data.hex()
        chunk_size = 500
        chunks = [hex_data[i:i + chunk_size] for i in range(0, len(hex_data), chunk_size)]

        keyring.set_password(service_name, namespaced_key(key_base, "count"), str(len(chunks)))
        for i, chunk in enumerate(chunks):
            keyring.set_password(service_name, namespaced_key(key_base, i), chunk)

    @classmethod
    def _purge_large_data(cls, service_name: str, app_identifier: str, key: str):
        key_base = get_key_base(app_identifier, key)
        count_key = namespaced_key(key_base, "count")
        count_str = keyring.get_password(service_name, count_key)
        if count_str:
            try:
                count = int(count_str)
                for i in range(count):
                    try:
                        keyring.delete_password(service_name, namespaced_key(key_base, i))
                    except Exception:
                        pass
            except ValueError:
                pass
        try:
            keyring.delete_password(service_name, count_key)
        except Exception:
            pass

    @classmethod
    def _purge_existing_key_material(cls, service_name: str, app_identifier: str):
        for key in ("salt", "nonce", "tag", ENCRYPTOR_TYPE_KEY):
            try:
                keyring.delete_password(service_name, namespaced_key(app_identifier, key))
            except Exception:
                pass
        cls._purge_large_data(service_name, app_identifier, "encrypted_priv")
        cls._purge_large_data(service_name, app_identifier, "public_key")
