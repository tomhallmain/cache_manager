# Cache Manager

A tool for managing internal application caches across your personal applications. This application provides backup functionality for encrypted cache files and displays backup status information.

## Features

- **Out-of-Cycle Backups**: Create manual backups of application caches that won't be overwritten during normal backup rotation
- **Backup Status Display**: View the last backup timestamp for each application
- **Application Management**: Add, edit, and remove applications from the management list
- **Multi-Application Support**: Manage caches for multiple applications from a single interface

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python main.py
```

3. Configure your applications using the UI:
   - Click "Add Application" to add new applications
   - Enter the following information for each application:
     - `name`: Display name for the application
     - `service_name`: Service identifier used by the application's encryptor
     - `app_identifier`: Application identifier used by the application's encryptor
     - `cache_location`: Path to the encrypted cache file

## Configuration Storage

The application uses an **encrypted cache file** (`cache_manager_config.enc`) to store all configuration data securely. This file is:
- Encrypted using the same encryption system as your application caches
- Stored locally with keys managed through the platform's secure keyring
- Not included in version control (git-ignored)
- Automatically created on first run

The `configs/config_example.json` file is provided as a reference for the configuration structure, but all actual data is stored in the encrypted cache file.

## Usage

### Creating Backups

1. Select an application from the list
2. Click "Create Backup" or double-click the application row
3. The backup will be created in the `backups/` directory with a timestamp
4. The backup is verified by attempting to decrypt it before saving

### Managing Applications

- **Add**: Click "Add Application" and fill in the details
- **Edit**: Select an application and click "Edit Application"
- **Remove**: Select an application and click "Remove Application"
- **Refresh**: Click "Refresh" to reload the applications list and update backup status

## Cache Information

The application displays:
- Application name
- Cache file location
- Last backup timestamp (Never if no backup exists)
- Cache file size

## Backup Files

Backups are stored in the `backups/` directory with the following naming convention:
```
{application_name}_{YYYYMMDD}_{HHMMSS}.enc
```

Backup metadata is stored in `{application_name}_backups.json` files containing timestamps and file paths.

## Security Notes

- **Encrypted Configuration**: All application configuration data is stored in an encrypted cache file
- Cache files remain encrypted during backup
- Backups are stored in the same encrypted format as the original cache
- The backup manager verifies backup integrity by attempting to decrypt each backup
- Configuration cache and backups are git-ignored by default

## Future Features (TODO)

- **Cache Inspection**: View specific cache properties and their values
- **Cache Modification**: Edit cache property values directly
- Backup restore functionality
- Scheduled automatic backups
- Backup retention policies

## Requirements

- Python 3.8+
- PySide6
- keyring
- cryptography
- Optional: oqs-python (for quantum encryption support)

## License

This is a personal utility for managing application caches.

