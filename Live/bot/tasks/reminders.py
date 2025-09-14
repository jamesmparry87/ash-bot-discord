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
        # Comprehensive time patterns ordered from most specific to most general
        time_patterns = [
            # Duration patterns (highest priority)
            (r'\b(?:in\s+)?(\d+)\s*(?:minute|min)(?:\'?s)?\s*(?:time)?\b', 'minutes_from_now'),
            (r'\b(?:in\s+)?(\d+)\s*(?:m)\b', 'minutes_from_now_short'),
            (r'\b(?:in\s+)?(\d+)\s*(?:hour|hr)(?:s)?\s*(?:time)?\b', 'hours_from_now'),
            (r'\b(?:in\s+)?(\d+)\s*(?:h)\b', 'hours_from_now_short'),
            (r'\b(?:in\s+)?(\d+)\s*(?:day|d)(?:s)?\s*(?:time)?\b', 'days_from_now'),
            (r'\b(?:in\s+)?(\d+)\s*(?:week|wk)(?:s)?\b', 'weeks_from_now'),
            (r'\b(?:in\s+)?(\d+)\s*(?:second|sec)(?:s)?\s*(?:time)?\b', 'seconds_from_now'),
            (r'\b(?:in\s+)?(\d+)\s*(?:s)\b', 'seconds_from_now_short'),

            # Weekday patterns with times
            (
                r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b',
                'weekday_time'),
            (
                r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b',
                'next_weekday_time'),

            # Simple time patterns with clearer matching
            (r'\b(?:at|for|on)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', 'time_12h'),
            (r'\b(?:at|for|on)\s+(\d{1,2})\.(\d{2})\s*(am|pm)\b', 'time_dot_12h'),
            (r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', 'time_12h_simple'),

            # 24-hour format times
            (r'\bat\s+(\d{1,2})(?::(\d{2}))?\b', 'time_24h'),
            (r'\bat\s+(\d{1,2})\.(\d{2})\b', 'time_dot_24h'),

            # Tomorrow patterns
            (r'\btomorrow\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', 'tomorrow_time'),
            (r'\btomorrow\b', 'tomorrow'),

            # Day-only patterns
            (r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 'weekday'),
            (r'\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', 'next_weekday'),

            # Special times
            (r'\b(?:at\s+)?(?:noon|midday|12pm)\b', 'noon'),
            (r'\b(?:at\s+)?(?:midnight|12am)\b', 'midnight'),
            (r'\b(?:at\s+)?(?:6\s*pm|18:00|1800)\b', 'six_pm'),
        ]

        # Extract reminder text and time
        original_content = content
        reminder_text = content
        scheduled_time = None
        matched_pattern = None
        uk_now = datetime.now(ZoneInfo("Europe/London"))

        for pattern, time_type in time_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                # Store the matched pattern for better text extraction
                matched_pattern = match.group(0)

                # Remove the EXACT matched text from the reminder
                reminder_text = content.replace(matched_pattern, '').strip()
                reminder_text = re.sub(r'\s+', ' ', reminder_text)  # Normalize whitespace

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

                elif time_type in ['hours_from_now', 'hours_from_now_short']:
                    hours = int(match.group(1))
                    scheduled_time = uk_now + timedelta(hours=hours)

                elif time_type in ['minutes_from_now', 'minutes_from_now_short']:
                    minutes = int(match.group(1))
                    scheduled_time = uk_now + timedelta(minutes=minutes)

                elif time_type == 'days_from_now':
                    days = int(match.group(1))
                    scheduled_time = uk_now + timedelta(days=days)

                elif time_type in ['seconds_from_now', 'seconds_from_now_short']:
                    seconds = int(match.group(1))
                    scheduled_time = uk_now + timedelta(seconds=seconds)

                elif time_type == 'weeks_from_now':
                    weeks = int(match.group(1))
                    scheduled_time = uk_now + timedelta(weeks=weeks)

                elif time_type in ['weekday_time', 'next_weekday_time']:
                    weekday_name = match.group(1).lower()
                    hour = int(match.group(2))
                    minute = int(match.group(3)) if len(match.groups()) > 2 and match.group(3) else 0
                    am_pm = match.group(4).lower() if len(match.groups()) > 3 and match.group(4) else None

                    if am_pm == 'pm' and hour != 12:
                        hour += 12
                    elif am_pm == 'am' and hour == 12:
                        hour = 0

                    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    target_weekday = weekdays.index(weekday_name)
                    current_weekday = uk_now.weekday()

                    days_ahead = target_weekday - current_weekday
                    if time_type == 'next_weekday_time':
                        days_ahead += 7 if days_ahead <= 0 else 7  # Always next week
                    elif days_ahead <= 0:  # This week or past
                        days_ahead += 7  # Next occurrence

                    target_date = uk_now + timedelta(days=days_ahead)
                    scheduled_time = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                elif time_type in ['weekday', 'next_weekday']:
                    weekday_name = match.group(1).lower()
                    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                    target_weekday = weekdays.index(weekday_name)
                    current_weekday = uk_now.weekday()

                    days_ahead = target_weekday - current_weekday
                    if time_type == 'next_weekday':
                        days_ahead += 7 if days_ahead <= 0 else 7  # Always next week
                    elif days_ahead <= 0:
                        days_ahead += 7

                    target_date = uk_now + timedelta(days=days_ahead)
                    scheduled_time = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

                elif time_type == 'time_12h_simple':
                    hour = int(match.group(1))
                    minute = int(match.group(2)) if match.group(2) else 0
                    am_pm = match.group(3).lower()

                    if am_pm == 'pm' and hour != 12:
                        hour += 12
                    elif am_pm == 'am' and hour == 12:
                        hour = 0

                    target_time = uk_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type == 'noon':
                    target_time = uk_now.replace(hour=12, minute=0, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                elif time_type == 'midnight':
                    target_time = uk_now.replace(hour=0, minute=0, second=0, microsecond=0)
                    target_time += timedelta(days=1)  # Always next midnight
                    scheduled_time = target_time

                elif time_type in ['time_dot_12h', 'time_dot_24h']:
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    am_pm = match.group(3).lower() if len(match.groups()) > 2 and match.group(3) else None

                    # Handle AM/PM for 12h format
                    if time_type == 'time_dot_12h' and am_pm:
                        if am_pm == 'pm' and hour != 12:
                            hour += 12
                        elif am_pm == 'am' and hour == 12:
                            hour = 0

                    # Validate hour for 24h format
                    if time_type == 'time_dot_24h' and hour > 23:
                        continue

                    target_time = uk_now.replace(
                        hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

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

                elif time_type == 'six_pm':
                    target_time = uk_now.replace(
                        hour=18, minute=0, second=0, microsecond=0)
                    if target_time <= uk_now:
                        target_time += timedelta(days=1)
                    scheduled_time = target_time

                break

        # Clean up reminder text - normalize whitespace first
        reminder_text = re.sub(r'\s+', ' ', reminder_text).strip()

        # Remove command prefixes more comprehensively
        reminder_text = re.sub(
            r'^(?:remind\s+me\s*(?:to\s+|of\s+|at\s+|in\s+)?|'
            r'set\s+(?:a\s+)?remind(?:er)?\s*(?:for\s+|to\s+|of\s+)?|'
            r'create\s+(?:a\s+)?remind(?:er)?\s*(?:for\s+|to\s+|of\s+)?|'
            r'schedule\s+(?:a\s+)?remind(?:er)?\s*(?:for\s+|to\s+|of\s+)?|'
            r'(?:ash\s+)?remind\s+me\s*(?:to\s+|of\s+|at\s+|in\s+)?)',
            '', reminder_text, flags=re.IGNORECASE).strip()

        # Remove standalone prepositions and connectors
        reminder_text = re.sub(r'^(?:to\s+|of\s+|about\s+|that\s+|for\s+|at\s+)',
                               '', reminder_text, flags=re.IGNORECASE).strip()

        # Remove leftover command fragments
        reminder_text = re.sub(r'^(?:remind(?:er)?\s*|set\s*|create\s*|schedule\s*)',
                               '', reminder_text, flags=re.IGNORECASE).strip()

        # Remove any leftover time fragments that weren't caught by the initial replacement
        reminder_text = re.sub(r'^\d+\.\d+\s*', '', reminder_text).strip()
        reminder_text = re.sub(r'^\.?\d+\s+', '', reminder_text).strip()

        # Final cleanup pass - remove any remaining artifacts
        reminder_text = re.sub(r'^(?:to\s+|of\s+|about\s+|that\s+|for\s+|at\s+)',
                               '', reminder_text, flags=re.IGNORECASE).strip()

        # Remove common leftover words that aren't meaningful
        reminder_text = re.sub(r'^(?:me\s+|a\s+)', '', reminder_text, flags=re.IGNORECASE).strip()

        # Validate the parsed result
        validation_result = _validate_parsed_reminder(
            original_content, reminder_text, scheduled_time, matched_pattern
        )

        if not validation_result["success"]:
            # Return the validation error for better user feedback
            return validation_result

        # Default to 1 hour from now if no time found
        if not scheduled_time:
            scheduled_time = uk_now + timedelta(hours=1)

        return {
            "reminder_text": reminder_text,
            "scheduled_time": scheduled_time,
            "success": bool(reminder_text.strip()),
            "confidence": "high" if matched_pattern else "low",
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


def _validate_parsed_reminder(original_content: str, reminder_text: str,
                              scheduled_time: Optional[datetime], matched_pattern: Optional[str]) -> Dict[str, Any]:
    """Validate that the parsed reminder makes logical sense"""

    # Check if we have a meaningful reminder message
    if not reminder_text or not reminder_text.strip():
        return {
            "success": False,
            "error_type": "missing_message",
            "error_message": "No reminder message found. Please specify what you want to be reminded about.",
            "suggestion": "Try: 'remind me in 5 minutes to check the server' or 'set reminder for 7pm to review reports'"}

    # Check if the reminder text is too short or meaningless
    if len(reminder_text.strip()) < 3:
        return {
            "success": False,
            "error_type": "message_too_short",
            "error_message": "Reminder message is too short. Please provide a meaningful reminder.",
            "suggestion": "Example: 'remind me in 10 minutes to check on the stream'"
        }

    # Check for meaningless reminder text patterns
    meaningless_patterns = [
        r'^\s*[.!?]+\s*$',  # Just punctuation
        r'^\s*\d+\s*$',     # Just numbers
        r'^\s*[a-zA-Z]\s*$',  # Just single letter
        r'^\s*time\s*$',    # Just "time" leftover
        r'^\s*for\s*$',     # Just "for" leftover
        r'^\s*to\s*$',      # Just "to" leftover
        r'^\s*at\s*$',      # Just "at" leftover
        r'^\s*of\s*$',      # Just "of" leftover
        r'^\s*about\s*$',   # Just "about" leftover
        r'^\s*that\s*$',    # Just "that" leftover
        r'^\s*\'s\s*time\s*$',  # "'s time" leftover
        r'^\s*tomorrow\s*$',   # Just "tomorrow" leftover from command
    ]

    for pattern in meaningless_patterns:
        if re.match(pattern, reminder_text, re.IGNORECASE):
            return {
                "success": False,
                "error_type": "missing_message",
                "error_message": f"I understood the timing, but what should I remind you about?",
                "suggestion": f"For example: 'remind me {matched_pattern} to check the server' or specify what you need to remember"}

    # Check if the parsing seems to have failed badly (e.g., time pattern matched but left weird text)
    suspicious_patterns = [
        r'^\s*\'s\s+time\s*$',  # "minute's time" became "'s time"
        r'^\s*s\s+time\s*$',    # "minutes time" became "s time"
        r'^\d+\s*$',            # Just leftover number
    ]

    for pattern in suspicious_patterns:
        if re.match(pattern, reminder_text, re.IGNORECASE):
            # This suggests the parsing went wrong - ask for clarification
            return {
                "success": False,
                "error_type": "parsing_ambiguous",
                "error_message": "I'm not sure I understood that correctly. Could you rephrase your reminder request?",
                "suggestion": "Try something like: 'remind me in 1 minute to check the server' or 'set reminder for 7pm'"}

    return {"success": True}


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
    """Format a scheduled time for display with 12-hour format and proper timezone"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Determine timezone display (GMT/BST)
    is_dst = scheduled_time.dst() != timedelta(0)
    tz_name = "BST" if is_dst else "GMT"

    # Format time in 12-hour format
    time_12h = scheduled_time.strftime(f'%I:%M %p {tz_name}')

    # Calculate time difference
    time_diff = scheduled_time - uk_now

    if time_diff.days > 0:
        if time_diff.days == 1:
            return f"tomorrow at {time_12h}"
        else:
            date_str = scheduled_time.strftime('%B %d')
            return f"in {time_diff.days} days at {time_12h} on {date_str}"
    else:
        hours = int(time_diff.total_seconds() // 3600)
        minutes = int((time_diff.total_seconds() % 3600) // 60)

        # Fix the "1 minutes" vs "1 minute" issue and handle edge cases
        if hours > 0:
            hour_str = f"{hours} hour{'s' if hours != 1 else ''}"
            if minutes > 0:
                min_str = f" {minutes} minute{'s' if minutes != 1 else ''}"
                return f"in {hour_str}{min_str} at {time_12h}"
            else:
                return f"in {hour_str} at {time_12h}"
        elif minutes > 0:
            min_str = f"{minutes} minute{'s' if minutes != 1 else ''}"
            return f"in {min_str} at {time_12h}"
        else:
            # For times less than a minute, check if it's close to 1 minute
            total_seconds = time_diff.total_seconds()
            if total_seconds >= 30:  # Round up to 1 minute if >= 30 seconds
                return f"in 1 minute at {time_12h}"
            else:
                return f"in less than a minute at {time_12h}"


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
