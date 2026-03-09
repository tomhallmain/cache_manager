# Cache Manager

A PySide6-based application for managing out-of-cycle backups of application caches that use the shared encryption system from [utils/encryptor.py](https://github.com/tomhallmain/sd-runner/blob/master/utils/encryptor.py).

Designed for managing caches from applications that utilize the same encryption infrastructure, including:
- [Weidr](https://github.com/tomhallmain/Weidr)
- [sd-runner](https://github.com/tomhallmain/sd-runner)
- [muse](https://github.com/tomhallmain/muse)

## Features

- **Cache Backups**: Create out-of-cycle backups that won't be overwritten during normal rotation
- **Backup Tracking**: Display last operational backup timestamp and stale-backup alerting in the UI
- **Dual-Destination Backups**: Write backups to local `backups/` and an optional external backup directory
- **Recovery Bundle**: Maintain an encrypted portable recovery bundle (`cache_recovery.bundle.enc`) containing key material needed to recover decryptability on another machine
- **Recovery Import**: Import a recovery bundle from the UI to rehydrate key material and restore cache files from available backups
- **Application Management**: Add, edit, and remove applications
- **Encryption Support**: Tracks encryption strategy (None, Standard, OQS) per application
- **Automatic Rotation**: Maintains maximum of 10 backups per application
- **Self-Management**: Automatically manages its own cache configuration

### Planned Features

- **Inspect**: View cache contents and properties
- **Modify**: Edit cache property values
- **Migrate**: Switch encryption keys and strategies

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Optional: Install OQS for quantum encryption support:
   ```bash
   pip install -e /path/to/oqs-python
   ```

3. Run the application:
   ```bash
   python main.py
   ```

4. Add applications via the UI - the cache manager adds itself automatically on first run

## Configuration

Each managed application requires:
- Display name
- Service name and app identifier (for encryption keys)
- Cache file location (`.enc` format)
- Encryption strategy

Backup configuration:
- Local backup directory defaults to `backups/` (sanitized backup filenames)
- Optional external backup directory can be set in the UI (`Set External Backup Path`)
- When external backup is configured, each backup operation writes to both local and external destinations
- Recovery bundle location defaults to the active backup destination as `cache_recovery.bundle.enc`
- Recovery bundle encryption uses a user-defined recovery passphrase (set on first backup if not already configured; can be rotated via `Reset Recovery Password`)

## Usage

- Select an application and click "Create Backup" (or double-click)
- Backups are verified by decryption before being saved
- Old backups are automatically rotated when exceeding the limit

## Requirements

- Python 3.8+
- PySide6, keyring, cryptography
- Optional: oqs-python (for quantum encryption)

## License

Personal utility for managing application caches.
