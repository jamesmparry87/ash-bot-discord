"""
Reminder Processing Module

Handles reminder parsing, natural language processing, and time calculations
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ..integrations.youtube import extract_youtube_urls, has_youtube_content


def parse_natural_reminder(content: str, user_id: int) -> Dict[str, Any]:
    """Parse natural language reminder requests"""
    try:
        # Enhanced time patterns with more flexible matching
        time_patterns = [
            # Simple relative times (most common)
            (r'\bin\s+(\d+)\s*(?:minute|min|m)s?\b', 'minutes_from_now'),
            (r'\bin\s+(\d+)\s*(?:hour|hr|h)s?\b', 'hours_from_now'),
            (r'\bin\s+(\d+)\s*(?:second|sec|s)\b', 'seconds_from_now'),
            (r'\bin\s+(\d+)\s*(?:day|d)s?\b', 'days_from_now'),

            # Specific times with flexible format
            (r'\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)\b', 'time_12h'),
            (r'\bat\s+(\d{1,2})(?::(\d{2}))?\b', 'time_24h'),
            (r'\bat\s+(\d{1,2})\.(\d{2})\s*(am|pm|AM|PM)?\b',
             'time_dot_format'),

            # Flexible PM times
            (r'\bfor\s+(\d{1,2})(?::(\d{2}))?\s*pm\b', 'for_pm_time'),
            (r'\bfor\s+(\d{1,2})\.(\d{2})\s*pm\b', 'for_pm_dot_time'),
            (
                r'\bset\s+reminder\s+for\s+(\d{1,2})(?::(\d{2}))?\s*pm\b',
                'set_reminder_pm'),

            # Tomorrow patterns
            (
                r'\btomorrow\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?\b',
                'tomorrow_time'),
            (r'\btomorrow\b', 'tomorrow'),

            # Special times
            (r'\bat\s+(?:6\s*pm|18:00|1800)\b', 'six_pm'),
        ]

        # Extract reminder text and time
        reminder_text = content
        scheduled_time = None
        uk_now = datetime.now(ZoneInfo("Europe/London"))

        for pattern, time_type in time_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                # Remove time specification from reminder text
                reminder_text = re.sub(
                    pattern, '', content, flags=re.IGNORECASE).strip()
                reminder_text = re.sub(
                    r'\s+', ' ', reminder_text)  # Normalize whitespace

                if time_type == 'time_12h':
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0
                    am_pm = match.group(3).lower()

                    if am_pm == 'pm' and hour != 12:
                        hour += 12
                    elif am_pm == 'am' and hour == 12:
                        hour = 0

                    # Schedule for today if time hasn't passed, otherwise
                    # tomorrow
                    target_time = uk_now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type == 'time_24h':
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0

                    if hour > 23:  # Probably meant 12-hour format
                        continue

                    target_time = uk_now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type == 'hours_from_now':
                    hours = int(match.group(1))
                    scheduled_time = uk_now + timedelta(hours=hours)

                elif time_type == 'minutes_from_now':
                    minutes = int(match.group(1))
                    scheduled_time = uk_now + timedelta(minutes=minutes)

                elif time_type == 'days_from_now':
                    days = int(match.group(1))
                    scheduled_time = uk_now + timedelta(days=days)

                elif time_type == 'tomorrow':
                    scheduled_time = (
                        uk_now +
                        timedelta(
                            days=1)).replace(
                        hour=9,
                        minute=0,
                        second=0,
                        microsecond=0)

                elif time_type == 'tomorrow_time':
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0
                    am_pm = match.group(3).lower() if match.group(3) else None

                    if am_pm == 'pm' and hour != 12:
                        hour += 12
                    elif am_pm == 'am' and hour == 12:
                        hour = 0

                    scheduled_time = (uk_now + timedelta(days=1)).replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )

                elif time_type == 'seconds_from_now':
                    seconds = int(match.group(1))
                    scheduled_time = uk_now + timedelta(seconds=seconds)

                elif time_type == 'time_dot_format':
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0
                    am_pm = match.group(3).lower() if match.group(3) else None

                    if am_pm == 'pm' and hour != 12:
                        hour += 12
                    elif am_pm == 'am' and hour == 12:
                        hour = 0

                    target_time = uk_now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type in ['for_pm_time', 'set_reminder_pm']:
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0

                    # Always PM for these patterns
                    if hour != 12:
                        hour += 12

                    target_time = uk_now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type == 'for_pm_dot_time':
                    hour = int(match.group(1))
                    minute = int(match.group(2))

                    # Always PM for this pattern
                    if hour != 12:
                        hour += 12

                    target_time = uk_now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type == 'six_pm':
                    target_time = uk_now.replace(
                        hour=18, minute=0, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                break

        # Clean up reminder text
        reminder_text = re.sub(r'\s+', ' ', reminder_text).strip()
        reminder_text = re.sub(
            r'^(remind\s+me\s+(?:to\s+|of\s+)?)',
            '',
            reminder_text,
            flags=re.IGNORECASE).strip()
        reminder_text = re.sub(
            r'^(ash\s+)?remind\s+me\s+(?:to\s+|of\s+)?',
            '',
            reminder_text,
            flags=re.IGNORECASE).strip()

        # Default to 1 hour from now if no time found
        if not scheduled_time:
            scheduled_time = uk_now + timedelta(hours=1)

        return {
            "reminder_text": reminder_text,
            "scheduled_time": scheduled_time,
            "success": bool(reminder_text.strip()),
        }
    except Exception as e:
        print(f"❌ Error parsing natural reminder: {e}")
        return {
            "reminder_text": content,
            "scheduled_time": datetime.now(
                ZoneInfo("Europe/London")) +
            timedelta(
                hours=1),
            "success": False,
        }


def detect_auto_action_type(
        reminder_request: str) -> tuple[Optional[str], Dict[str, Any]]:
    """Detect if reminder request should have auto-actions and return type and data"""
    youtube_urls = extract_youtube_urls(reminder_request)

    if youtube_urls or has_youtube_content(reminder_request):
        # YouTube auto-posting detected
        auto_action_type = "youtube_post"

        youtube_url = None
        if youtube_urls:
            youtube_url = youtube_urls[0]

        auto_action_data = {
            "youtube_url": youtube_url,
            "custom_message": "New video uploaded - check it out!",
        }

        return auto_action_type, auto_action_data

    return None, {}


def format_reminder_time(scheduled_time: datetime) -> str:
    """Format a scheduled time for display"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Calculate time difference
    time_diff = scheduled_time - uk_now

    if time_diff.days > 0:
        if time_diff.days == 1:
            return f"tomorrow at {scheduled_time.strftime('%H:%M UK')}"
        else:
            return f"in {time_diff.days} days at {scheduled_time.strftime('%H:%M UK on %B %d')}"
    else:
        hours = int(time_diff.total_seconds() // 3600)
        minutes = int((time_diff.total_seconds() % 3600) // 60)

        if hours > 0:
            return f"in {hours}h {minutes}m at {scheduled_time.strftime('%H:%M UK')}"
        elif minutes > 0:
            return f"in {minutes} minutes at {scheduled_time.strftime('%H:%M UK')}"
        else:
            return f"in less than a minute at {scheduled_time.strftime('%H:%M UK')}"


def validate_reminder_text(text: str) -> bool:
    """Validate that reminder text is meaningful"""
    if not text or not text.strip():
        return False

    # Check minimum length
    if len(text.strip()) < 3:
        return False

    # Check for common meaningless patterns
    meaningless_patterns = [
        r'^\s*test\s*$',
        r'^\s*[.!?]+\s*$',
        r'^\s*\d+\s*$',
        r'^\s*[a-zA-Z]\s*$',
    ]

    for pattern in meaningless_patterns:
        if re.match(pattern, text, re.IGNORECASE):
            return False

    return True


def extract_reminder_keywords(text: str) -> List[str]:
    """Extract important keywords from reminder text for searching"""
    # Remove common words
    stop_words = {
        'the',
        'a',
        'an',
        'and',
        'or',
        'but',
        'in',
        'on',
        'at',
        'to',
        'for',
        'of',
        'with',
        'by'}

    # Extract words (alphanumeric sequences)
    words = re.findall(r'\b\w+\b', text.lower())

    # Filter out stop words and short words
    keywords = [
        word for word in words if word not in stop_words and len(word) > 2]

    return keywords
