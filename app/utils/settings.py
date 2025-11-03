"""
Utility functions for system settings management
"""

from flask import current_app
from app.models import SystemSetting
from app import db
import logging

logger = logging.getLogger(__name__)

# Cache for settings to avoid repeated database queries
_settings_cache = {}
_cache_valid = False


def get_setting(key: str, default: str = None) -> str:
    """
    Get system setting value by key
    
    Args:
        key: Setting key
        default: Default value if setting not found
        
    Returns:
        Setting value or default
    """
    global _settings_cache, _cache_valid
    
    # Try to get from cache first
    if _cache_valid and key in _settings_cache:
        return _settings_cache[key]
    
    try:
        # Try to get from database
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting and setting.value:
            value = setting.value
            # Update cache and mark as valid
            _settings_cache[key] = value
            _cache_valid = True
            return value
        else:
            # Not found, use default
            if default is not None:
                _settings_cache[key] = default
                _cache_valid = True  # Mark cache as valid even with default values
                return default
            return None
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        # Don't mark cache as valid if DB error occurred
        return default


def get_setting_int(key: str, default: int = None) -> int:
    """Get system setting as integer"""
    value = get_setting(key, str(default) if default is not None else None)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid integer value for setting {key}: {value}, using default {default}")
        return default


def get_setting_bool(key: str, default: bool = False) -> bool:
    """Get system setting as boolean"""
    value = get_setting(key, str(default).lower())
    if value is None:
        return default
    return value.lower() in ('true', '1', 'yes', 'on')


def invalidate_cache():
    """Invalidate settings cache (call after updating settings)"""
    global _settings_cache, _cache_valid
    _settings_cache = {}
    _cache_valid = False


def get_all_settings() -> dict:
    """
    Get all settings as dictionary
    Useful for passing to templates
    """
    try:
        settings = SystemSetting.query.all()
        return {setting.key: setting.value for setting in settings}
    except Exception as e:
        logger.error(f"Error getting all settings: {e}")
        return {}


# Convenience functions for commonly used settings
def get_contact_email() -> str:
    """Get contact email from settings"""
    return get_setting('contact_email', 'support@mainstreamfs.ru')


def get_telegram_bot_username() -> str:
    """Get Telegram bot username from settings"""
    return get_setting('telegram_bot_username', '@mainstreamshopbot')


def get_whatsapp_number() -> str:
    """Get WhatsApp number from settings"""
    return get_setting('whatsapp_number', '+7 (999) 123-45-67')


def get_site_name() -> str:
    """Get site name from settings"""
    return get_setting('site_name', 'MainStream Shop')


def get_site_description() -> str:
    """Get site description from settings"""
    return get_setting('site_description', 'Профессиональные видео с турниров по фигурному катанию')


def get_auto_cancel_minutes() -> int:
    """
    Get auto cancel minutes from settings
    Checks auto_cancel_minutes first, then auto_cancel_hours (for backward compatibility)
    """
    # Try new setting first
    minutes = get_setting_int('auto_cancel_minutes', None)
    if minutes is not None:
        return minutes
    
    # Fallback to old setting (convert hours to minutes)
    hours = get_setting_int('auto_cancel_hours', None)
    if hours is not None:
        return hours * 60
    
    # Default: 15 minutes
    return 15


def get_auto_cancel_hours() -> int:
    """
    Get auto cancel hours from settings (deprecated, use get_auto_cancel_minutes instead)
    Kept for backward compatibility
    """
    minutes = get_auto_cancel_minutes()
    # Convert minutes to hours (rounded up)
    return (minutes + 59) // 60


def get_video_link_expiry_days() -> int:
    """Get video link expiry days from settings"""
    return get_setting_int('video_link_expiry_days', 90)


def get_test_mode() -> bool:
    """Get test mode from settings"""
    return get_setting_bool('test_mode', False)
