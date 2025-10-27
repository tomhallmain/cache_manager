from utils.app_info_cache import app_info_cache
from utils.logging_setup import get_logger
from utils.translations import I18N

logger = get_logger(__name__)
_ = I18N._


class ConfigManager:
    """
    Configuration manager using encrypted cache storage.
    All configuration data is stored in an encrypted cache file.
    """
    
    def __init__(self):
        # Use the global encrypted cache instance
        self.cache = app_info_cache
    
    def get_applications(self):
        """Get list of all configured applications"""
        return self.cache.get_applications()
    
    def add_application(self, name: str, service_name: str, app_identifier: str, cache_location: str, encryption_strategy: str = None):
        """Add a new application to the configuration"""
        self.cache.add_application(name, service_name, app_identifier, cache_location, encryption_strategy)
    
    def remove_application(self, index: int):
        """Remove an application from the configuration"""
        self.cache.remove_application(index)
    
    def update_application(self, index: int, name: str, service_name: str, app_identifier: str, cache_location: str, encryption_strategy: str = None):
        """Update an existing application in the configuration"""
        self.cache.update_application(index, name, service_name, app_identifier, cache_location, encryption_strategy)

