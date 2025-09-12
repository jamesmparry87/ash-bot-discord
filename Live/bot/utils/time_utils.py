"""
Time Utilities Module

Handles time calculations, timezone conversions, and time-related formatting
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo

# Common timezones used by the bot
UK_TIMEZONE = ZoneInfo("Europe/London")
US_PACIFIC_TIMEZONE = ZoneInfo("US/Pacific")
UTC_TIMEZONE = timezone.utc


def get_uk_time() -> datetime:
    """Get current UK time"""
    return datetime.now(UK_TIMEZONE)


def get_pacific_time() -> datetime:
    """Get current Pacific time"""
    return datetime.now(US_PACIFIC_TIMEZONE)


def get_utc_time() -> datetime:
    """Get current UTC time"""
    return datetime.now(UTC_TIMEZONE)


def convert_to_uk_time(dt: datetime) -> datetime:
    """Convert datetime to UK timezone"""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=UTC_TIMEZONE)
    return dt.astimezone(UK_TIMEZONE)


def convert_to_pacific_time(dt: datetime) -> datetime:
    """Convert datetime to Pacific timezone"""
    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        dt = dt.replace(tzinfo=UTC_TIMEZONE)
    return dt.astimezone(US_PACIFIC_TIMEZONE)


def convert_to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC"""
    if dt.tzinfo is None:
        # Assume local timezone if no timezone info
        dt = dt.replace(tzinfo=UK_TIMEZONE)
    return dt.astimezone(UTC_TIMEZONE)


def is_uk_business_hours(dt: Optional[datetime] = None) -> bool:
    """Check if given time (or current time) is during UK business hours (9 AM - 6 PM, Monday-Friday)"""
    if dt is None:
        dt = get_uk_time()
    else:
        dt = convert_to_uk_time(dt)

    # Check if weekday (Monday = 0, Sunday = 6)
    if dt.weekday() >= 5:  # Saturday or Sunday
        return False

    # Check if business hours (9 AM to 6 PM)
    return 9 <= dt.hour < 18


def is_weekend(dt: Optional[datetime] = None) -> bool:
    """Check if given time (or current time) is during weekend"""
    if dt is None:
        dt = get_uk_time()
    else:
        dt = convert_to_uk_time(dt)

    return dt.weekday() >= 5  # Saturday or Sunday


def time_until_next_weekday(
        target_weekday: int,
        target_hour: int = 9,
        target_minute: int = 0) -> timedelta:
    """Calculate time until next occurrence of specified weekday and time"""
    uk_now = get_uk_time()

    # Calculate days until target weekday
    days_ahead = target_weekday - uk_now.weekday()
    if days_ahead <= 0:  # Target day already passed this week
        days_ahead += 7

    # Create target datetime
    target_dt = uk_now.replace(
        hour=target_hour,
        minute=target_minute,
        second=0,
        microsecond=0)
    target_dt += timedelta(days=days_ahead)

    # If it's the same day but time has passed, move to next week
    if days_ahead == 7 and target_dt <= uk_now:
        target_dt += timedelta(days=7)

    return target_dt - uk_now


def time_until_next_tuesday_11am() -> timedelta:
    """Calculate time until next Tuesday at 11 AM UK time (for Trivia Tuesday)"""
    return time_until_next_weekday(1, 11, 0)  # Tuesday = 1


def time_until_next_sunday_midday() -> timedelta:
    """Calculate time until next Sunday at midday UK time"""
    return time_until_next_weekday(6, 12, 0)  # Sunday = 6


def time_until_next_midnight_pacific() -> timedelta:
    """Calculate time until next midnight Pacific time"""
    pacific_now = get_pacific_time()
    next_midnight = pacific_now.replace(
        hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return next_midnight - pacific_now


def format_time_difference(td: timedelta) -> str:
    """Format timedelta in a human-readable way"""
    total_seconds = int(td.total_seconds())

    if total_seconds < 0:
        return "in the past"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0 and days == 0:  # Don't show minutes if we have days
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0 and days == 0 and hours == 0:  # Only show seconds for short durations
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    if not parts:
        return "now"

    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    else:
        return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def format_datetime_uk(dt: datetime, include_timezone: bool = True) -> str:
    """Format datetime in UK timezone with standard format"""
    uk_dt = convert_to_uk_time(dt)

    if include_timezone:
        return uk_dt.strftime("%Y-%m-%d %H:%M:%S UK")
    else:
        return uk_dt.strftime("%Y-%m-%d %H:%M:%S")


def format_datetime_pacific(dt: datetime,
                            include_timezone: bool = True) -> str:
    """Format datetime in Pacific timezone with standard format"""
    pacific_dt = convert_to_pacific_time(dt)

    if include_timezone:
        return pacific_dt.strftime("%Y-%m-%d %H:%M:%S PT")
    else:
        return pacific_dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_time_string(
        time_str: str,
        base_date: Optional[datetime] = None) -> Optional[datetime]:
    """Parse time string in various formats and return datetime"""
    if base_date is None:
        base_date = get_uk_time().replace(hour=0, minute=0, second=0, microsecond=0)

    time_formats = [
        "%H:%M",         # 14:30
        "%H:%M:%S",      # 14:30:45
        "%I:%M %p",      # 2:30 PM
        "%I:%M:%S %p",   # 2:30:45 PM
        "%H.%M",         # 14.30
        "%H-%M",         # 14-30
    ]

    for fmt in time_formats:
        try:
            parsed_time = datetime.strptime(time_str.strip(), fmt).time()
            return base_date.replace(
                hour=parsed_time.hour,
                minute=parsed_time.minute,
                second=parsed_time.second,
                microsecond=0
            )
        except ValueError:
            continue

    return None


def get_next_occurrence(target_time: datetime,
                        reference_time: Optional[datetime] = None) -> datetime:
    """Get the next occurrence of target time after reference time"""
    if reference_time is None:
        reference_time = get_uk_time()

    # Ensure both times are in the same timezone
    target_time = convert_to_uk_time(target_time)
    reference_time = convert_to_uk_time(reference_time)

    # If target time is in the future today, return it
    if target_time > reference_time:
        return target_time

    # Otherwise, return target time tomorrow
    return target_time + timedelta(days=1)


def calculate_age(
        birth_date: datetime,
        reference_date: Optional[datetime] = None) -> timedelta:
    """Calculate age/time difference between two dates"""
    if reference_date is None:
        reference_date = get_uk_time()

    return reference_date - birth_date


def is_same_day(
        dt1: datetime,
        dt2: datetime,
        timezone_obj: Optional[ZoneInfo] = None) -> bool:
    """Check if two datetimes are on the same day in specified timezone"""
    if timezone_obj is None:
        timezone_obj = UK_TIMEZONE

    # Convert both to the specified timezone
    dt1_tz = dt1.astimezone(timezone_obj)
    dt2_tz = dt2.astimezone(timezone_obj)

    return dt1_tz.date() == dt2_tz.date()


def get_start_of_day(
        dt: Optional[datetime] = None,
        timezone_obj: Optional[ZoneInfo] = None) -> datetime:
    """Get start of day (midnight) for given datetime"""
    if dt is None:
        dt = datetime.now()

    if timezone_obj is None:
        timezone_obj = UK_TIMEZONE

    dt_tz = dt.astimezone(timezone_obj)
    return dt_tz.replace(hour=0, minute=0, second=0, microsecond=0)


def get_end_of_day(
        dt: Optional[datetime] = None,
        timezone_obj: Optional[ZoneInfo] = None) -> datetime:
    """Get end of day (23:59:59.999999) for given datetime"""
    if dt is None:
        dt = datetime.now()

    if timezone_obj is None:
        timezone_obj = UK_TIMEZONE

    dt_tz = dt.astimezone(timezone_obj)
    return dt_tz.replace(hour=23, minute=59, second=59, microsecond=999999)


def get_time_zone_offset(dt: datetime, target_timezone: ZoneInfo) -> timedelta:
    """Get timezone offset for given datetime and timezone"""
    dt_in_tz = dt.astimezone(target_timezone)
    return dt_in_tz.utcoffset() or timedelta(0)


def is_dst_active(dt: Optional[datetime] = None,
                  timezone_obj: Optional[ZoneInfo] = None) -> bool:
    """Check if Daylight Saving Time is active for given datetime and timezone"""
    if dt is None:
        dt = datetime.now()

    if timezone_obj is None:
        timezone_obj = UK_TIMEZONE

    dt_tz = dt.astimezone(timezone_obj)
    return bool(dt_tz.dst())


def round_to_nearest_minute(dt: datetime) -> datetime:
    """Round datetime to nearest minute"""
    if dt.second >= 30:
        dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    else:
        dt = dt.replace(second=0, microsecond=0)
    return dt


def round_to_nearest_hour(dt: datetime) -> datetime:
    """Round datetime to nearest hour"""
    if dt.minute >= 30:
        dt = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        dt = dt.replace(minute=0, second=0, microsecond=0)
    return dt


def get_business_days_between(start_date: datetime, end_date: datetime) -> int:
    """Count business days between two dates (excluding weekends)"""
    start_date_obj = convert_to_uk_time(start_date).date()
    end_date_obj = convert_to_uk_time(end_date).date()

    business_days = 0
    current_date = start_date_obj

    while current_date < end_date_obj:
        if current_date.weekday() < 5:  # Monday = 0, Friday = 4
            business_days += 1
        current_date += timedelta(days=1)

    return business_days


def create_uk_datetime(
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0) -> datetime:
    """Create datetime in UK timezone"""
    return datetime(year, month, day, hour, minute, second, tzinfo=UK_TIMEZONE)


def create_pacific_datetime(
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0) -> datetime:
    """Create datetime in Pacific timezone"""
    return datetime(
        year,
        month,
        day,
        hour,
        minute,
        second,
        tzinfo=US_PACIFIC_TIMEZONE)
