"""
Utility functions for working with Moscow timezone
All datetime operations in the application should use Moscow time (UTC+3)
"""

from datetime import datetime, timedelta
try:
    import pytz
    _HAS_PYTZ = True
    MOSCOW_TZ = pytz.timezone('Europe/Moscow')
except ImportError:
    _HAS_PYTZ = False
    # Fallback to UTC+3 offset if pytz is not available
    from datetime import timezone
    MOSCOW_TZ = timezone(timedelta(hours=3))


def moscow_now():
    """
    Get current datetime in Moscow timezone (timezone-aware)
    
    Returns:
        datetime: Current time in Moscow timezone
    """
    if _HAS_PYTZ:
        return datetime.now(MOSCOW_TZ)
    else:
        # Fallback: UTC+3
        return datetime.now(MOSCOW_TZ)


def moscow_now_naive():
    """
    Get current datetime in Moscow timezone as naive datetime
    (without timezone info, but time is Moscow time)
    
    This is useful for database columns that don't store timezone info
    
    Returns:
        datetime: Current time in Moscow timezone (naive, no timezone info)
    """
    if _HAS_PYTZ:
        return datetime.now(MOSCOW_TZ).replace(tzinfo=None)
    else:
        # Simple UTC+3 offset (Moscow time)
        utc_now = datetime.utcnow()
        moscow_offset = timedelta(hours=3)
        moscow_now = utc_now + moscow_offset
        return moscow_now


def to_moscow_time(dt):
    """
    Convert datetime to Moscow timezone
    
    Args:
        dt: datetime object (naive or timezone-aware)
        
    Returns:
        datetime: datetime in Moscow timezone (naive)
    """
    if dt is None:
        return None
    
    # If naive datetime, assume it's already in Moscow time
    if dt.tzinfo is None:
        return dt
    
    # Convert to Moscow timezone
    if _HAS_PYTZ:
        try:
            # If dt has timezone info, convert it
            if dt.tzinfo == pytz.UTC:
                # Convert from UTC to Moscow
                moscow_dt = dt.replace(tzinfo=pytz.UTC).astimezone(MOSCOW_TZ)
            else:
                moscow_dt = dt.astimezone(MOSCOW_TZ)
            return moscow_dt.replace(tzinfo=None)
        except Exception:
            # If conversion fails, just remove timezone
            return dt.replace(tzinfo=None)
    else:
        # Simple conversion: if UTC, add 3 hours
        return dt.replace(tzinfo=None)
