from enum import Enum


class EncryptionStrategy(Enum):
    """Encryption strategy for application caches"""
    UNKNOWN = "unknown"
    NONE = "none"
    STANDARD = "standard"
    OQS = "oqs"
    
    @classmethod
    def from_string(cls, value):
        """Convert string to EncryptionStrategy enum"""
        if value is None:
            return cls.UNKNOWN
        value_lower = value.lower()
        for strategy in cls:
            if strategy.value == value_lower:
                return strategy
        return cls.UNKNOWN
    
    def __str__(self):
        return self.value
    
    def display_value(self, translate_func):
        """Get the translated display value for this strategy"""
        translations = {
            self.UNKNOWN: lambda _: _("Unknown"),
            self.NONE: lambda _: _("None"),
            self.STANDARD: lambda _: _("Standard"),
            self.OQS: lambda _: _("OQS (Quantum)")
        }
        if self in translations:
            return translations[self](translate_func)
        return self.value

