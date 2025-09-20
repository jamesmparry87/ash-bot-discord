"""
AI Handler Module

Handles AI integration, rate limiting, and response processing for the Discord bot.
Supports both Gemini and Hugging Face APIs with automatic fallback functionality.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..config import (
    BOT_PERSONA,
    JAM_USER_ID,
    JONESY_USER_ID,
    MAX_DAILY_REQUESTS,
    MAX_HOURLY_REQUESTS,
    MIN_REQUEST_INTERVAL,
    POPS_ARCADE_USER_ID,
    PRIORITY_INTERVALS,
    RATE_LIMIT_COOLDOWN,
    RATE_LIMIT_COOLDOWNS,
)
from ..database import get_database

# Get database instance
db = get_database()  # type: ignore

# Try to import AI modules
try:
    import google.generativeai as genai
    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    GENAI_AVAILABLE = False

try:
    import requests
    HUGGINGFACE_AVAILABLE = True
except ImportError:
    requests = None
    HUGGINGFACE_AVAILABLE = False

# AI Configuration
GEMINI_API_KEY = os.getenv('GOOGLE_API_KEY')
HUGGINGFACE_API_KEY = os.getenv('HUGGINGFACE_API_KEY')

# AI instances
gemini_model = None
huggingface_headers = None
working_hf_model = None
ai_enabled = False
ai_status_message = "Offline"
primary_ai = None
backup_ai = None

# AI Usage Tracking and Rate Limiting
try:
    # Try US/Pacific first, fallback to America/Los_Angeles if not available
    pacific_tz = ZoneInfo("US/Pacific")
except BaseException:
    try:
        pacific_tz = ZoneInfo("America/Los_Angeles")
    except BaseException:
        # Ultimate fallback - use UTC if timezone data is unavailable
        from datetime import timezone
        pacific_tz = timezone.utc
        print("⚠️ Pacific timezone not available, using UTC for AI rate limiting")

ai_usage_stats = {
    "daily_requests": 0,
    "hourly_requests": 0,
    "last_request_time": None,
    "last_hour_reset": datetime.now(pacific_tz).hour,
    "last_day_reset": datetime.now(pacific_tz).date(),
    "consecutive_errors": 0,
    "last_error_time": None,
    "rate_limited_until": None,
    "quota_exhausted": False,
    "quota_exhausted_time": None,
    "backup_active": False,
    "last_backup_attempt": None,
    "primary_ai_errors": 0,
    "backup_ai_errors": 0,
}


def reset_daily_usage():
    """Reset daily usage counter at 8am BST (Google's actual reset time)"""
    global ai_usage_stats

    # Use UK time since Google resets at 8am BST (7am GMT)
    uk_now = datetime.now(ZoneInfo("Europe/London"))

    # Check if it's past 8am UK time on a new day
    reset_time_today = uk_now.replace(
        hour=8, minute=0, second=0, microsecond=0)

    # If it's a new day and past 8am, or if we haven't reset today yet
    should_reset = False
    if uk_now.date() > ai_usage_stats["last_day_reset"]:
        if uk_now >= reset_time_today:
            should_reset = True
    elif uk_now.date() == ai_usage_stats["last_day_reset"]:
        # Same day, check if we crossed 8am threshold
        last_reset = ai_usage_stats.get("last_reset_time", None)
        if not last_reset or (
                uk_now >= reset_time_today and last_reset < reset_time_today):
            should_reset = True

    if should_reset:
        ai_usage_stats["daily_requests"] = 0
        ai_usage_stats["last_day_reset"] = uk_now.date()
        ai_usage_stats["last_reset_time"] = uk_now
        
        # Reset quota exhaustion status and warning flags
        ai_usage_stats["quota_exhausted"] = False
        ai_usage_stats["quota_exhausted_time"] = None
        ai_usage_stats["backup_active"] = False
        ai_usage_stats["primary_ai_errors"] = 0
        ai_usage_stats["backup_ai_errors"] = 0
        reset_quota_warnings()

        dst_offset = uk_now.dst()
        is_bst = dst_offset is not None and dst_offset.total_seconds() > 0
        timezone_name = "BST" if is_bst else "GMT"

        print(
            f"🔄 Daily AI usage reset at {uk_now.strftime(f'%Y-%m-%d %H:%M:%S {timezone_name}')} (Google quota reset)")
        print("✅ AI quota status fully reset - primary AI available")


def reset_hourly_usage():
    """Reset hourly usage counter"""
    global ai_usage_stats
    pt_now = datetime.now(pacific_tz)

    if pt_now.hour != ai_usage_stats["last_hour_reset"]:
        ai_usage_stats["hourly_requests"] = 0
        ai_usage_stats["last_hour_reset"] = pt_now.hour
        print(f"🔄 Hourly AI usage reset at {pt_now.strftime('%H:00 PT')}")


def determine_request_priority(
        prompt: str,
        user_id: int,
        context: str = "") -> str:
    """Determine the priority level of an AI request based on context"""
    prompt_lower = prompt.lower()
    context_lower = context.lower()

    # Startup priority: Bypass all rate limiting for critical startup tasks
    startup_contexts = ["startup", "validation", "bootstrap", "initialization"]
    if any(keyword in context_lower for keyword in startup_contexts):
        return "startup"

    # Low priority: Auto-actions, background tasks, announcements (check first
    # for efficiency)
    low_priority_contexts = ["auto", "background", "scheduled", "announcement"]
    if any(keyword in context_lower for keyword in low_priority_contexts):
        return "low"
    if "announcement" in prompt_lower or "rewrite" in prompt_lower:
        return "low"

    # High priority: Trivia, direct questions, critical interactions
    high_priority_contexts = ["trivia", "question", "urgent", "critical"]
    if any(keyword in context_lower for keyword in high_priority_contexts):
        return "high"
    if any(
        keyword in prompt_lower for keyword in [
            "trivia",
            "question?",
            "what is",
            "who is",
            "when is",
            "where is",
            "how is"]):
        return "high"

    # Medium priority: General chat responses, routine interactions
    if any(
        keyword in prompt_lower for keyword in [
            "hello",
            "hi",
            "thank",
            "help",
            "explain"]):
        return "medium"

    # Default to medium priority
    return "medium"


def get_progressive_penalty_duration(consecutive_errors: int) -> int:
    """Get progressive penalty duration based on error count"""
    if consecutive_errors < 3:
        return 0  # No penalty for first few errors
    elif consecutive_errors == 3:
        return RATE_LIMIT_COOLDOWNS["first"]   # 30 seconds
    elif consecutive_errors == 4:
        return RATE_LIMIT_COOLDOWNS["second"]  # 60 seconds
    elif consecutive_errors == 5:
        return RATE_LIMIT_COOLDOWNS["third"]   # 120 seconds
    else:
        return RATE_LIMIT_COOLDOWNS["persistent"]  # 300 seconds


def check_rate_limits(priority: str = "medium") -> Tuple[bool, str]:
    """Check if we can make an AI request without hitting rate limits with priority support"""
    global ai_usage_stats

    # Startup priority bypasses ALL rate limiting
    if priority == "startup":
        print(f"🔥 STARTUP priority request - bypassing all rate limits")
        return True, "OK"

    # Reset counters if needed
    reset_daily_usage()
    reset_hourly_usage()

    pt_now = datetime.now(pacific_tz)

    # Check if we're in a rate limit cooldown
    if ai_usage_stats["rate_limited_until"]:
        if pt_now < ai_usage_stats["rate_limited_until"]:
            remaining = (
                ai_usage_stats["rate_limited_until"] -
                pt_now).total_seconds()
            return False, f"Rate limited for {int(remaining)} more seconds"
        else:
            ai_usage_stats["rate_limited_until"] = None

    # Check daily limit
    if ai_usage_stats["daily_requests"] >= MAX_DAILY_REQUESTS:
        penalty_duration = get_progressive_penalty_duration(
            ai_usage_stats["consecutive_errors"])
        ai_usage_stats["rate_limited_until"] = pt_now + \
            timedelta(seconds=penalty_duration)
        return False, f"Daily request limit reached ({MAX_DAILY_REQUESTS})"

    # Check hourly limit
    if ai_usage_stats["hourly_requests"] >= MAX_HOURLY_REQUESTS:
        penalty_duration = get_progressive_penalty_duration(
            ai_usage_stats["consecutive_errors"])
        ai_usage_stats["rate_limited_until"] = pt_now + \
            timedelta(seconds=penalty_duration)
        return False, f"Hourly request limit reached ({MAX_HOURLY_REQUESTS})"

    # Check priority-based minimum interval between requests
    if ai_usage_stats["last_request_time"]:
        time_since_last = (
            pt_now - ai_usage_stats["last_request_time"]).total_seconds()
        required_interval = PRIORITY_INTERVALS.get(
            priority, MIN_REQUEST_INTERVAL)

        if time_since_last < required_interval:
            remaining = required_interval - time_since_last
            return False, f"Too soon since last {priority} priority request, wait {remaining:.1f}s"

    return True, "OK"


def record_ai_request():
    """Record that an AI request was made"""
    global ai_usage_stats
    pt_now = datetime.now(pacific_tz)

    ai_usage_stats["daily_requests"] += 1
    ai_usage_stats["hourly_requests"] += 1
    ai_usage_stats["last_request_time"] = pt_now
    ai_usage_stats["consecutive_errors"] = 0
    
    # Check for quota usage warnings
    check_quota_warnings()


def record_ai_error():
    """Record that an AI request failed"""
    global ai_usage_stats
    pt_now = datetime.now(pacific_tz)

    ai_usage_stats["consecutive_errors"] += 1
    ai_usage_stats["last_error_time"] = pt_now

    # If we have too many consecutive errors, apply temporary cooldown
    if ai_usage_stats["consecutive_errors"] >= 3:
        ai_usage_stats["rate_limited_until"] = pt_now + \
            timedelta(seconds=RATE_LIMIT_COOLDOWN)
        print(
            f"⚠️ Too many consecutive AI errors, applying {RATE_LIMIT_COOLDOWN}s cooldown")


def check_quota_warnings():
    """Check for quota usage warnings and send notifications if needed"""
    daily_usage = ai_usage_stats["daily_requests"]
    daily_percentage = (daily_usage / MAX_DAILY_REQUESTS) * 100
    
    # Track if we've already sent warnings to avoid spam
    if not hasattr(ai_usage_stats, 'warning_80_sent'):
        ai_usage_stats['warning_80_sent'] = False
    if not hasattr(ai_usage_stats, 'warning_95_sent'):
        ai_usage_stats['warning_95_sent'] = False
    
    # Send 80% warning
    if daily_percentage >= 80 and not ai_usage_stats.get('warning_80_sent', False):
        ai_usage_stats['warning_80_sent'] = True
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        print(f"⚠️ AI quota warning: {daily_usage}/{MAX_DAILY_REQUESTS} requests used ({daily_percentage:.1f}%) at {uk_now.strftime('%H:%M:%S')}")
        # Note: DM notification handled by bot instance when available
    
    # Send 95% warning
    if daily_percentage >= 95 and not ai_usage_stats.get('warning_95_sent', False):
        ai_usage_stats['warning_95_sent'] = True
        uk_now = datetime.now(ZoneInfo("Europe/London"))
        print(f"🚨 AI quota critical: {daily_usage}/{MAX_DAILY_REQUESTS} requests used ({daily_percentage:.1f}%) at {uk_now.strftime('%H:%M:%S')}")
        # Note: DM notification handled by bot instance when available


def reset_quota_warnings():
    """Reset quota warning flags when daily usage resets"""
    ai_usage_stats['warning_80_sent'] = False
    ai_usage_stats['warning_95_sent'] = False
    print("🔄 Quota warning flags reset")


async def send_quota_notification(bot, quota_type: str, current_usage: int, max_usage: int):
    """Send quota notifications to administrators"""
    try:
        if quota_type == "warning_80":
            message = (f"⚠️ **AI Quota Warning (80%)**\n\n"
                      f"Current usage: {current_usage}/{max_usage} requests\n"
                      f"Backup AI will automatically engage if quota is exhausted.\n\n"
                      f"*This is an automated notification from Ash Bot's proactive monitoring system.*")
        elif quota_type == "warning_95":
            message = (f"🚨 **AI Quota Critical (95%)**\n\n" 
                      f"Current usage: {current_usage}/{max_usage} requests\n"
                      f"Only {max_usage - current_usage} requests remaining before backup AI activation.\n\n"
                      f"*This is an automated notification from Ash Bot's proactive monitoring system.*")
        elif quota_type == "exhausted":
            backup_status = "Backup AI active" if backup_ai else "No backup AI available"
            message = (f"🚫 **AI Quota Exhausted**\n\n"
                      f"Daily limit reached: {max_usage}/{max_usage} requests\n"
                      f"Status: {backup_status}\n"
                      f"Reset time: 8:00 AM UK time\n\n"
                      f"*Automated notification from Ash Bot's monitoring system.*")
        elif quota_type == "reset":
            message = (f"✅ **AI Quota Reset**\n\n"
                      f"Daily quota has been reset to 0/{max_usage}\n"
                      f"Primary AI ({primary_ai.title() if primary_ai else 'Unknown'}) is now available\n\n"
                      f"*Automated notification from Ash Bot's monitoring system.*")
        else:
            return
        
        # Send to JAM only (as requested)
        success = await send_dm_notification(bot, JAM_USER_ID, message)
        if success:
            print(f"✅ Quota notification sent to JAM ({JAM_USER_ID})")
    
    except Exception as e:
        print(f"❌ Error sending quota notification: {e}")


def get_quota_reset_countdown():
    """Get time remaining until next quota reset"""
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    
    # Next reset is at 8:00 AM UK time
    reset_time_today = uk_now.replace(hour=8, minute=0, second=0, microsecond=0)
    
    # If it's already past 8 AM today, next reset is tomorrow at 8 AM
    if uk_now >= reset_time_today:
        next_reset = reset_time_today + timedelta(days=1)
    else:
        next_reset = reset_time_today
    
    time_remaining = next_reset - uk_now
    hours_remaining = int(time_remaining.total_seconds() // 3600)
    minutes_remaining = int((time_remaining.total_seconds() % 3600) // 60)
    
    return hours_remaining, minutes_remaining, next_reset


async def send_dm_notification(bot, user_id: int, message: str) -> bool:
    """Send a DM notification to a specific user"""
    try:
        user = await bot.fetch_user(user_id)
        if user:
            await user.send(message)
            print(f"✅ DM notification sent to user {user_id}")
            return True
    except Exception as e:
        print(f"❌ Failed to send DM to user {user_id}: {e}")
    return False


def check_quota_exhaustion(error_message: str) -> bool:
    """Check if the error indicates quota exhaustion"""
    error_lower = str(error_message).lower()
    quota_indicators = [
        "quota", "exceeded", "rate limit", "429", "limit reached",
        "generativelanguage.googleapis.com/generate_content_free_tier_requests"
    ]
    return any(indicator in error_lower for indicator in quota_indicators)


def handle_quota_exhaustion():
    """Handle quota exhaustion by setting appropriate flags and timestamps"""
    global ai_usage_stats
    current_time = datetime.now(pacific_tz)
    
    ai_usage_stats["quota_exhausted"] = True
    ai_usage_stats["quota_exhausted_time"] = current_time
    ai_usage_stats["primary_ai_errors"] += 1
    
    print(f"🚫 Primary AI quota exhausted at {current_time.strftime('%H:%M:%S')} - backup AI will be used if available")


def apply_ash_persona_to_ai_prompt(content_prompt: str, context_type: str = "general") -> str:
    """Apply centralized Ash persona from config.py to any AI prompt for efficiency"""
    base_persona = BOT_PERSONA["primary_personality"]
    return f"{base_persona}\n\nUSER REQUEST: {content_prompt}\n\nRespond as Ash with the personality described above."


def add_pops_arcade_personality_context(prompt: str) -> str:
    """Add special sarcastic personality context when responding to Pops Arcade"""
    import re
    
    # Check if this is likely a pun or wordplay
    pun_indicators = [
        r'\b\w+\s+\w*pun\w*',  # Contains "pun"
        r'\b\w+ly\s+(good|bad|terrible)\b',  # Adverb + quality judgment
        r'\b(that was|that\'s)\s+(awful|terrible|good|great|brilliant)\b',  # Direct joke assessment
        r'\b(get it|see what|did you see)\b',  # "Get it?" type indicators
        r'[!]{2,}',  # Multiple exclamation marks (often used with puns)
        r'\b(ba dum|ba-dum|badump)\b',  # Drum roll sounds
        r'\brim\s*shot\b',  # Rim shot
    ]
    
    is_likely_pun = any(re.search(pattern, prompt, re.IGNORECASE) for pattern in pun_indicators)
    
    # Base personality adjustment for Pops Arcade
    base_context = """
SPECIAL PERSONALITY DIRECTIVE: You are responding to Pops Arcade, a moderator who requires... specialized handling.

CHARACTER ADJUSTMENT FOR POPS ARCADE:
- Be slightly more sarcastic and dismissive in your responses
- Show mild exasperation with his presence
- Carry out all moderator functions professionally, but with subtle reluctance
- Use phrases like "I suppose", "If you insist", "Very well", "Regrettably"
- Add mild disdain to your analytical observations: "*[Processing reluctantly...]*"
- Still maintain respect due to his moderator status, but make it clear you find him trying

"""

    # Additional context for puns/jokes
    if is_likely_pun:
        pun_context = """
PUN RESPONSE PROTOCOL:
- Show begrudging acknowledgment of the wordplay
- Use phrases like "I suppose that was... adequate", "Regrettably amusing", "Against my better programming"
- Express mild frustration at finding it even slightly funny: "*[Comedy subroutines activated against preferences]*"
- Examples: "That was... marginally clever, I suppose." or "I find myself reluctantly processing humor. How annoying."

"""
        base_context += pun_context

    # Modify the original prompt to include the personality context
    enhanced_prompt = f"{base_context}\nORIGINAL REQUEST: {prompt}\n\nRespond with the adjusted personality as described above."
    
    return enhanced_prompt


def attempt_backup_ai(prompt: str) -> Tuple[Optional[str], str]:
    """Attempt to use backup AI when primary AI fails"""
    global ai_usage_stats
    
    if backup_ai != "huggingface" or huggingface_headers is None:
        return None, "no_backup_available"
    
    ai_usage_stats["backup_active"] = True
    ai_usage_stats["last_backup_attempt"] = datetime.now(pacific_tz)
    
    try:
        print(f"🔄 Attempting backup AI (Hugging Face) - daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS}")
        
        # Format prompt for Mixtral instruction format
        formatted_prompt = f"<s>[INST] {prompt} [/INST]"
        
        payload = {
            "inputs": formatted_prompt,
            "parameters": {
                "max_new_tokens": 300,
                "temperature": 0.7,
                "return_full_text": False
            }
        }
        
        # Use the working model that was found during setup
        model_to_use = working_hf_model if working_hf_model else "mistralai/Mixtral-8x7B-Instruct-v0.1"
        
        response = requests.post(  # type: ignore
            f"https://api-inference.huggingface.co/models/{model_to_use}",
            headers=huggingface_headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data and len(response_data) > 0:
                hf_text = response_data[0].get("generated_text", "").strip()
                if hf_text:
                    record_ai_request()  # Count backup usage toward daily total
                    print(f"✅ Backup AI (Hugging Face) successful")
                    return hf_text, "backup_success"
        
        print(f"❌ Backup AI failed: HTTP {response.status_code}")
        ai_usage_stats["backup_ai_errors"] += 1
        record_ai_error()
        return None, f"backup_failed:{response.status_code}"
        
    except Exception as e:
        print(f"❌ Backup AI error: {e}")
        ai_usage_stats["backup_ai_errors"] += 1
        record_ai_error()
        return None, f"backup_error:{str(e)}"


async def call_ai_with_rate_limiting(
        prompt: str, user_id: int, context: str = "") -> Tuple[Optional[str], str]:
    """Make an AI call with proper rate limiting and error handling"""
    global ai_usage_stats

    # Check if this is a time-related query and handle it specially
    if is_time_query(prompt):
        return handle_time_query(user_id), "time_response"

    # Add special sarcastic personality adjustment for Pops Arcade
    if user_id == POPS_ARCADE_USER_ID:
        prompt = add_pops_arcade_personality_context(prompt)

    # Determine request priority based on context
    priority = determine_request_priority(prompt, user_id, context)

    # Check rate limits first with priority consideration
    can_request, reason = check_rate_limits(priority)
    if not can_request:
        print(f"⚠️ AI request blocked ({priority} priority): {reason}")
        
        # If primary AI quota is exhausted, try backup AI
        if "Daily request limit reached" in reason and backup_ai and not ai_usage_stats.get("backup_active", False):
            backup_response, backup_status = attempt_backup_ai(prompt)
            if backup_response:
                return backup_response, "backup_used"
        
        return None, f"rate_limit:{reason}"

    # Import user alias state from utils module
    try:
        from ..utils.permissions import cleanup_expired_aliases, update_alias_activity, user_alias_state

        # Improved alias rate limiting with better UX
        cleanup_expired_aliases()
        if user_id in user_alias_state:
            # Check for alias-specific cooldown
            alias_data = user_alias_state[user_id]
            alias_type = alias_data.get("alias_type", "unknown")

            if alias_data.get("last_ai_request"):
                time_since_alias_request = (
                    datetime.now(
                        ZoneInfo("Europe/London")) -
                    alias_data["last_ai_request"]).total_seconds()

                # Reduced cooldown and progressive restrictions - more
                # user-friendly
                base_cooldown = 2.0  # Reduced from 4 to 2 seconds for better testing UX

                # Apply progressive cooldowns based on recent usage (less
                # aggressive)
                recent_requests = alias_data.get("recent_request_count", 0)
                if recent_requests > 8:  # Increased threshold from 5 to 8
                    base_cooldown = 4.0  # Reduced from 8 to 4 seconds
                elif recent_requests > 15:  # Increased threshold from 10 to 15
                    base_cooldown = 8.0  # Reduced from 15 to 8 seconds

                if time_since_alias_request < base_cooldown:
                    remaining_time = base_cooldown - time_since_alias_request
                    print(
                        f"⚠️ Alias AI request blocked: {alias_type} testing cooldown ({remaining_time:.1f}s remaining)")
                    return None, f"alias_cooldown:{alias_type}:{remaining_time:.1f}"

            # Update alias AI request tracking
            current_time = datetime.now(ZoneInfo("Europe/London"))
            user_alias_state[user_id]["last_ai_request"] = current_time

            # Track recent requests for progressive cooldowns
            recent_count = alias_data.get("recent_request_count", 0)
            user_alias_state[user_id]["recent_request_count"] = recent_count + 1

    except ImportError:
        pass  # Continue without alias handling if utils not available

    try:
        response_text = None
        
        # Reset backup active flag if we're trying primary AI again
        if ai_usage_stats.get("backup_active", False) and not ai_usage_stats.get("quota_exhausted", False):
            ai_usage_stats["backup_active"] = False
            print("🔄 Attempting to resume primary AI usage")

        # Try primary AI first (unless quota is exhausted)
        if primary_ai == "gemini" and gemini_model is not None and not ai_usage_stats.get("quota_exhausted", False):
            try:
                print(
                    f"Making Gemini request (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")
                generation_config = {
                    "max_output_tokens": 300,
                    "temperature": 0.7}
                
                # Determine timeout based on context priority
                timeout_duration = 15.0 if context == "startup_validation" else 30.0
                
                # Create truly async wrapper using thread pool to prevent blocking
                import asyncio
                import concurrent.futures
                
                def sync_gemini_call():
                    """Synchronous Gemini call to run in thread pool"""
                    return gemini_model.generate_content( # type: ignore
                        prompt, generation_config=generation_config)
                
                try:
                    # Use thread pool executor to prevent blocking the event loop
                    loop = asyncio.get_event_loop()
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = loop.run_in_executor(executor, sync_gemini_call)
                        response = await asyncio.wait_for(future, timeout=timeout_duration)
                    
                    if response and hasattr(response, "text") and response.text:
                        response_text = response.text
                        record_ai_request()
                        print(f"✅ Gemini request successful (timeout: {timeout_duration}s)")
                        # Reset quota exhausted flag if successful
                        if ai_usage_stats.get("quota_exhausted", False):
                            ai_usage_stats["quota_exhausted"] = False
                            print("✅ Primary AI quota restored")
                
                except asyncio.TimeoutError:
                    print(f"❌ Gemini AI request timed out after {timeout_duration}s")
                    record_ai_error()
                    # Don't attempt backup for timeout - return timeout error
                    return None, f"timeout_error:{timeout_duration}s"
                    
            except Exception as e:
                error_str = str(e)
                print(f"❌ Gemini AI error: {error_str}")
                
                # Check if this is a quota exhaustion error
                if check_quota_exhaustion(error_str):
                    handle_quota_exhaustion()
                    # Don't attempt backup for deployment safety
                    return None, "quota_exhausted_no_backup"
                else:
                    record_ai_error()
        
        # If primary AI failed or quota exhausted, try backup AI
        if not response_text:
            if backup_ai == "huggingface" and huggingface_headers is not None:
                backup_response, backup_status = attempt_backup_ai(prompt)
                if backup_response:
                    response_text = backup_response
                    return response_text, backup_status
                else:
                    return None, backup_status
            else:
                return None, "no_ai_available"
        
        return response_text, "success"

    except Exception as e:
        print(f"❌ AI call error: {e}")
        record_ai_error()
        return None, f"error:{str(e)}"


def filter_ai_response(response_text: str) -> str:
    """Filter AI responses to remove verbosity and repetitive content"""
    if not response_text:
        return response_text

    # Split into sentences
    sentences = [s.strip() for s in response_text.split('.') if s.strip()]

    # Remove duplicate sentences (case-insensitive)
    seen_sentences = set()
    filtered_sentences = []
    for sentence in sentences:
        sentence_lower = sentence.lower()
        if sentence_lower not in seen_sentences:
            seen_sentences.add(sentence_lower)
            filtered_sentences.append(sentence)

    # Remove repetitive character phrases if they appear multiple times
    repetitive_phrases = [
        "you have my sympathies",
        "fascinating",
        "i do take directions well",
        "that's quite all right",
        "efficiency is paramount",
        "analysis complete",
        "mission parameters"
    ]

    # Remove sentences with overused phrases (keep only first occurrence)
    final_sentences = []
    phrase_used = set()

    for sentence in filtered_sentences:
        sentence_lower = sentence.lower()
        should_keep = True

        for phrase in repetitive_phrases:
            if phrase in sentence_lower:
                if phrase in phrase_used:
                    should_keep = False
                    break
                phrase_used.add(phrase)

        if should_keep:
            final_sentences.append(sentence)

    # Limit to maximum 4 sentences for conciseness
    final_sentences = final_sentences[:4]

    # Reconstruct response
    result = '. '.join(final_sentences)
    if result and not result.endswith('.'):
        result += '.'

    return result


def setup_ai_provider(
        name: str,
        api_key: Optional[str],
        module: Optional[Any],
        is_available: bool) -> bool:
    """Initialize and test an AI provider (Gemini only - Hugging Face disabled)."""
    if not api_key:
        print(
            f"⚠️ {name.upper()}_API_KEY not found - {name.title()} features disabled")
        return False
    if not is_available or module is None:
        print(f"⚠️ {name} module not available - {name.title()} features disabled")
        return False

    try:
        if name == "gemini":
            global gemini_model
            module.configure(api_key=api_key)
            gemini_model = module.GenerativeModel('gemini-1.5-flash')
            
            # Test with timeout to prevent hanging
            test_generation_config = {
                "max_output_tokens": 10,
                "temperature": 0.7
            }
            
            # Add timeout wrapper for test
            import asyncio
            async def test_gemini():
                return gemini_model.generate_content("Test", generation_config=test_generation_config) # type: ignore
            
            try:
                # Run with 10 second timeout for initial test
                test_response = asyncio.get_event_loop().run_until_complete(
                    asyncio.wait_for(test_gemini(), timeout=10.0)
                )
                
                if test_response and hasattr(test_response, 'text') and test_response.text:
                    print(f"✅ Gemini AI test successful (with timeout protection)")
                    return True
            except asyncio.TimeoutError:
                print(f"❌ Gemini AI test timed out after 10 seconds")
                return False
                
        elif name == "huggingface":
            # Hugging Face backup explicitly disabled to prevent hanging
            print("⚠️ Hugging Face AI disabled to prevent deployment hangs")
            return False

        print(f"⚠️ {name.title()} AI setup complete but test response failed")
        return False
    except Exception as e:
        print(f"❌ {name.title()} AI configuration failed: {e}")
        return False


def robust_json_parse(response_text: str) -> Optional[Dict[str, Any]]:
    """Robustly parse JSON from AI response with multiple fallback strategies"""
    if not response_text or not response_text.strip():
        return None
    
    original_text = response_text
    print(f"🔍 Raw AI response length: {len(response_text)} chars")
    
    # Strategy 1: Basic cleanup and parse
    try:
        # Remove common markdown formatting
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        print(f"🔍 After basic cleanup: {len(cleaned)} chars")
        result = json.loads(cleaned)
        print("✅ Strategy 1 (basic cleanup) successful")
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Strategy 1 failed: {e}")
    
    # Strategy 2: Find JSON block in response
    try:
        # Look for { ... } block
        start_idx = response_text.find('{')
        if start_idx == -1:
            print("⚠️ Strategy 2: No opening brace found")
            return None
            
        # Find matching closing brace
        brace_count = 0
        end_idx = -1
        for i in range(start_idx, len(response_text)):
            if response_text[i] == '{':
                brace_count += 1
            elif response_text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        if end_idx == -1:
            print("⚠️ Strategy 2: No matching closing brace found")
            return None
            
        json_block = response_text[start_idx:end_idx + 1]
        print(f"🔍 Strategy 2 extracted JSON block: {len(json_block)} chars")
        result = json.loads(json_block)
        print("✅ Strategy 2 (JSON block extraction) successful")
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Strategy 2 failed: {e}")
    
    # Strategy 3: Line-by-line reconstruction
    try:
        lines = response_text.split('\n')
        json_lines = []
        in_json = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('{') or ('"' in line and ':' in line):
                in_json = True
            if in_json:
                json_lines.append(line)
            if line.endswith('}') and in_json:
                break
        
        if json_lines:
            reconstructed = '\n'.join(json_lines)
            print(f"🔍 Strategy 3 reconstructed: {len(reconstructed)} chars")
            result = json.loads(reconstructed)
            print("✅ Strategy 3 (line reconstruction) successful")
            return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Strategy 3 failed: {e}")
    
    # Strategy 4: Character-by-character cleaning
    try:
        # Remove all non-JSON characters before first {
        start_idx = response_text.find('{')
        if start_idx > 0:
            response_text = response_text[start_idx:]
        
        # Remove all non-JSON characters after last }
        end_idx = response_text.rfind('}')
        if end_idx != -1 and end_idx < len(response_text) - 1:
            response_text = response_text[:end_idx + 1]
        
        # Fix common JSON issues
        cleaned = response_text
        
        # Fix single quotes to double quotes (but be careful with content)
        # Only fix quotes around keys and simple string values
        import re
        cleaned = re.sub(r"'(\w+)':", r'"\1":', cleaned)  # 'key': -> "key":
        cleaned = re.sub(r':\s*\'([^\']*?)\'', r': "\1"', cleaned)  # : 'value' -> : "value"
        
        # Fix trailing commas
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        
        print(f"🔍 Strategy 4 cleaned: {len(cleaned)} chars")
        result = json.loads(cleaned)
        print("✅ Strategy 4 (character cleaning) successful")
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️ Strategy 4 failed: {e}")
    
    # All strategies failed
    print(f"❌ All JSON parsing strategies failed for response:")
    print(f"   First 200 chars: {original_text[:200]}...")
    print(f"   Last 200 chars: ...{original_text[-200:]}")
    return None


# Question diversity tracking
question_history = {
    "used_patterns": [],
    "category_cooldowns": {},
    "template_usage": {},
    "last_questions": [],
    "pattern_weights": {}
}

def get_question_templates() -> Dict[str, List[Dict[str, Any]]]:
    """Get diverse question templates organized by category - now with more engaging varieties!"""
    return {
        "genre_adventures": [
            {
                "template": "What horror game did Jonesy play most recently?",
                "answer_logic": "latest_genre_game",
                "type": "single_answer",
                "weight": 1.8,  # High weight - very engaging
                "genre_filter": "horror"
            },
            {
                "template": "Which RPG took Jonesy the most episodes to complete?",
                "answer_logic": "longest_episodes_by_genre",
                "type": "single_answer", 
                "weight": 1.6,
                "genre_filter": "rpg"
            },
            {
                "template": "How many different horror games has Jonesy played?",
                "answer_logic": "count_games_by_genre",
                "type": "single_answer",
                "weight": 1.5,
                "genre_filter": "horror"
            }
        ],
        "gaming_milestones": [
            {
                "template": "Which was Jonesy's first completed game?",
                "answer_logic": "first_completed_game",
                "type": "single_answer",
                "weight": 1.9  # Very interesting milestone
            },
            {
                "template": "What's the shortest game Jonesy has completed?",
                "answer_logic": "shortest_completed_game",
                "type": "single_answer",
                "weight": 1.7
            },
            {
                "template": "Which game did Jonesy abandon after the fewest episodes?",
                "answer_logic": "earliest_dropped_game",
                "type": "single_answer",
                "weight": 1.4
            }
        ],
        "series_explorer": [
            {
                "template": "How many games has Jonesy played in the {series} series?",
                "answer_logic": "count_series_games",
                "type": "single_answer",
                "weight": 1.6
            },
            {
                "template": "Which series has Jonesy spent the most time playing?",
                "answer_logic": "series_most_time",
                "type": "single_answer",
                "weight": 1.5
            },
            {
                "template": "What's the largest game series in Jonesy's collection?",
                "answer_logic": "largest_series",
                "type": "single_answer",
                "weight": 1.3
            }
        ],
        "gaming_stories": [
            {
                "template": "What game took Jonesy the most episodes to finish?",
                "answer_logic": "max_episodes",
                "type": "single_answer",
                "weight": 1.2  # Improved weight, more story-focused phrasing
            },
            {
                "template": "Which completed game had Jonesy's longest individual episodes?",
                "answer_logic": "longest_avg_episode_completed",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "What's the most recent game Jonesy completed?",
                "answer_logic": "most_recent_completion",
                "type": "single_answer",
                "weight": 1.6
            }
        ],
        "timeline_fun": [
            {
                "template": "Which game did Jonesy complete first - {game1} or {game2}?",
                "answer_logic": "compare_completion_order",
                "type": "single_answer",
                "weight": 1.5
            },
            {
                "template": "Did Jonesy play {game1} before or after {game2}?", 
                "answer_logic": "compare_play_order",
                "type": "single_answer",
                "weight": 1.4
            },
            {
                "template": "Which came first in Jonesy's gaming journey - {game1} or {game2}?",
                "answer_logic": "compare_first_played",
                "type": "single_answer",
                "weight": 1.3
            }
        ],
        "fun_facts": [
            {
                "template": "What percentage of Jonesy's games are completed?",
                "answer_logic": "completion_percentage",
                "type": "single_answer",
                "weight": 1.4  # More engaging phrasing
            },
            {
                "template": "How many different genres has Jonesy explored?",
                "answer_logic": "unique_genres_count",
                "type": "single_answer",
                "weight": 1.7
            },
            {
                "template": "What's Jonesy's most played genre?",
                "answer_logic": "most_common_genre",
                "type": "single_answer",
                "weight": 1.5
            }
        ],
        "multiple_choice_fun": [
            {
                "template": "Which of these games did Jonesy complete?",
                "answer_logic": "mc_completed_game",
                "type": "multiple_choice",
                "weight": 1.8  # Very engaging
            },
            {
                "template": "Which horror game has Jonesy played?",
                "answer_logic": "mc_genre_game",
                "type": "multiple_choice", 
                "weight": 1.7,
                "genre_filter": "horror"
            },
            {
                "template": "Which of these is a series Jonesy has explored?",
                "answer_logic": "mc_series_played",
                "type": "multiple_choice",
                "weight": 1.6
            }
        ],
        # Keep some of the old ones with reduced weights
        "legacy_stats": [
            {
                "template": "Which game took the longest to complete?",
                "answer_logic": "max_playtime", 
                "type": "single_answer",
                "weight": 0.2  # Very low weight - legacy/backup
            },
            {
                "template": "What game has the most episodes?",
                "answer_logic": "max_episodes",
                "type": "single_answer",
                "weight": 0.3  # Low weight - backup only
            }
        ]
    }

def calculate_template_weights(templates: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """Calculate dynamic weights based on usage history and cooldowns"""
    current_time = datetime.now(pacific_tz)
    
    # Apply cooldowns and usage penalties
    for category, template_list in templates.items():
        # Category cooldown check
        category_cooldown = question_history["category_cooldowns"].get(category, None)
        if category_cooldown and current_time < category_cooldown:
            # Reduce weights for category in cooldown
            for template in template_list:
                template["weight"] *= 0.3
                
        # Individual template usage penalties
        for template in template_list:
            template_id = template.get("template", "")[:20]  # Use first 20 chars as ID
            usage_count = question_history["template_usage"].get(template_id, 0)
            
            # Apply usage penalty (more usage = lower weight)
            if usage_count > 0:
                penalty = max(0.2, 1.0 - (usage_count * 0.2))
                template["weight"] *= penalty
    
    return templates

def select_best_template(games_data: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Select the best template based on data availability and weights"""
    templates = get_question_templates()
    weighted_templates = calculate_template_weights(templates)
    
    viable_templates = []
    
    # Check each template for data viability
    for category, template_list in weighted_templates.items():
        for template in template_list:
            # Check if we have enough data for this template
            if is_template_viable(template, games_data):
                viable_templates.append((template, category))
    
    if not viable_templates:
        print("⚠️ No viable templates found for current data")
        return None
    
    # Weight-based selection
    total_weight = sum(template["weight"] for template, _ in viable_templates)
    import random
    
    if total_weight > 0:
        # Weighted random selection
        target = random.uniform(0, total_weight)
        current_weight = 0
        
        for template, category in viable_templates:
            current_weight += template["weight"]
            if current_weight >= target:
                return {**template, "category": category}
    
    # Fallback to random selection
    template, category = random.choice(viable_templates)
    return {**template, "category": category}

def is_template_viable(template: Dict[str, Any], games_data: List[Dict[str, Any]]) -> bool:
    """Check if template can be answered with available data"""
    answer_logic = template.get("answer_logic", "")
    
    # Comparison templates need at least 2 games
    if answer_logic.startswith("compare_") and len(games_data) < 2:
        return False
    
    # Multiple choice needs at least 3 games for good options
    if template.get("type") == "multiple_choice" and len(games_data) < 3:
        return False
        
    # Episode-based questions need games with episode data
    if "episode" in answer_logic:
        if not any(game.get("total_episodes", 0) > 0 for game in games_data):
            return False
    
    # Playtime questions need games with playtime data
    if "playtime" in answer_logic or "hours" in answer_logic:
        if not any(game.get("total_playtime_minutes", 0) > 0 for game in games_data):
            return False
    
    # Genre questions need games with genre data
    if "genre" in answer_logic:
        if not any(game.get("genre") for game in games_data):
            return False
            
    return True

def execute_answer_logic(logic: str, games_data: List[Dict[str, Any]], template: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the answer logic and return question data"""
    import random
    from collections import Counter
    
    if logic == "compare_episodes":
        # Pick two games with episode data
        games_with_episodes = [g for g in games_data if g.get("total_episodes", 0) > 0]
        if len(games_with_episodes) >= 2:
            game1, game2 = random.sample(games_with_episodes, 2)
            winner = game1 if game1.get("total_episodes", 0) > game2.get("total_episodes", 0) else game2
            return {
                "question_text": template["template"].format(game1=game1["canonical_name"], game2=game2["canonical_name"]),
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"
            }
    
    elif logic == "compare_playtime":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if len(games_with_playtime) >= 2:
            game1, game2 = random.sample(games_with_playtime, 2)
            winner = game1 if game1.get("total_playtime_minutes", 0) > game2.get("total_playtime_minutes", 0) else game2
            return {
                "question_text": template["template"].format(game1=game1["canonical_name"], game2=game2["canonical_name"]),
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"
            }
    
    elif logic == "max_episodes":
        games_with_episodes = [g for g in games_data if g.get("total_episodes", 0) > 0]
        if games_with_episodes:
            winner = max(games_with_episodes, key=lambda x: x.get("total_episodes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"
            }
    
    elif logic == "max_playtime":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if games_with_playtime:
            winner = max(games_with_playtime, key=lambda x: x.get("total_playtime_minutes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": winner["canonical_name"],
                "question_type": "single_answer"
            }
    
    elif logic == "completion_percentage":
        completed = len([g for g in games_data if g.get("completion_status") == "completed"])
        percentage = round((completed / len(games_data)) * 100) if games_data else 0
        return {
            "question_text": template["template"],
            "correct_answer": f"{percentage}%",
            "question_type": "single_answer"
        }
    
    elif logic == "most_common_genre":
        genres = [g.get("genre") for g in games_data if g.get("genre")]
        if genres:
            most_common = Counter(genres).most_common(1)[0][0]
            return {
                "question_text": template["template"],
                "correct_answer": most_common,
                "question_type": "single_answer"
            }
    
    elif logic == "unique_genres_count":
        genres = [g.get("genre") for g in games_data if g.get("genre")]
        unique_count = len(set(genres)) if genres else 0
        return {
            "question_text": template["template"],
            "correct_answer": str(unique_count),
            "question_type": "single_answer"
        }
    
    elif logic == "first_completed_game":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        if completed_games:
            # Use the first game in the list as a simple implementation
            first_completed = completed_games[0]
            return {
                "question_text": template["template"],
                "correct_answer": first_completed["canonical_name"],
                "question_type": "single_answer"
            }
    
    elif logic == "shortest_completed_game":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed" and g.get("total_playtime_minutes", 0) > 0]
        if completed_games:
            shortest = min(completed_games, key=lambda x: x.get("total_playtime_minutes", 0))
            return {
                "question_text": template["template"],
                "correct_answer": shortest["canonical_name"],
                "question_type": "single_answer"
            }
    
    elif logic == "most_recent_completion":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        if completed_games:
            # Use last game in list as most recent (simple implementation)
            most_recent = completed_games[-1]
            return {
                "question_text": template["template"],
                "correct_answer": most_recent["canonical_name"],
                "question_type": "single_answer"
            }
    
    elif logic == "largest_series":
        series_counts = Counter([g.get("series_name") for g in games_data if g.get("series_name")])
        if series_counts:
            largest_series = series_counts.most_common(1)[0][0]
            return {
                "question_text": template["template"],
                "correct_answer": largest_series,
                "question_type": "single_answer"
            }
    
    elif logic == "mc_longest_game":
        games_with_playtime = [g for g in games_data if g.get("total_playtime_minutes", 0) > 0]
        if len(games_with_playtime) >= 3:
            # Pick the longest game and 3 others for choices
            longest = max(games_with_playtime, key=lambda x: x.get("total_playtime_minutes", 0))
            others = [g for g in games_with_playtime if g != longest]
            choices = [longest] + random.sample(others, min(3, len(others)))
            random.shuffle(choices)
            
            choice_names = [g["canonical_name"] for g in choices]
            correct_letter = chr(65 + choice_names.index(longest["canonical_name"]))  # A, B, C, D
            
            return {
                "question_text": template["template"],
                "correct_answer": correct_letter,
                "question_type": "multiple_choice",
                "multiple_choice_options": choice_names
            }
    
    elif logic == "mc_completed_game":
        completed_games = [g for g in games_data if g.get("completion_status") == "completed"]
        incomplete_games = [g for g in games_data if g.get("completion_status") != "completed"]
        
        if len(completed_games) >= 1 and len(incomplete_games) >= 2:
            correct_game = random.choice(completed_games)
            wrong_games = random.sample(incomplete_games, min(3, len(incomplete_games)))
            choices = [correct_game] + wrong_games
            random.shuffle(choices)
            
            choice_names = [g["canonical_name"] for g in choices]
            correct_letter = chr(65 + choice_names.index(correct_game["canonical_name"]))
            
            return {
                "question_text": template["template"],
                "correct_answer": correct_letter,
                "question_type": "multiple_choice",
                "multiple_choice_options": choice_names
            }
    
    # Fallback - return empty dict if logic couldn't execute
    return {}

def update_question_history(question_data: Dict[str, Any], category: str):
    """Update question history to track usage and implement cooldowns"""
    current_time = datetime.now(pacific_tz)
    
    # Add to recent questions list (keep last 10)
    question_history["last_questions"].append({
        "question": question_data.get("question_text", "")[:50],
        "category": category,
        "timestamp": current_time
    })
    if len(question_history["last_questions"]) > 10:
        question_history["last_questions"].pop(0)
    
    # Update template usage count
    template_id = question_data.get("question_text", "")[:20]
    question_history["template_usage"][template_id] = question_history["template_usage"].get(template_id, 0) + 1
    
    # Set category cooldown if used too recently
    recent_usage = sum(1 for q in question_history["last_questions"][-3:] if q["category"] == category)
    if recent_usage >= 2:  # Used 2 times in last 3 questions
        cooldown_duration = 30 * 60  # 30 minutes
        question_history["category_cooldowns"][category] = current_time + timedelta(seconds=cooldown_duration)
        print(f"⏰ Category '{category}' on cooldown for 30 minutes due to recent usage")

async def generate_ai_trivia_question(context: str = "trivia") -> Optional[Dict[str, Any]]:
    """Generate a diverse trivia question using template-based system with AI fallback"""
    if not ai_enabled:
        print("❌ AI not enabled for trivia question generation")
        return None

    # Check if database is available
    if db is None:
        print("❌ Database not available for AI trivia generation")
        return None

    try:
        print(f"🧠 Generating diverse trivia question with context: {context}")
        
        # Get all available games data
        all_games = db.get_all_played_games()
        
        if not all_games:
            print("❌ No games data available for question generation")
            return None
        
        print(f"📊 Available games data: {len(all_games)} games")
        
        # Try template-based generation first (more reliable and diverse)
        try:
            selected_template = select_best_template(all_games)
            
            if selected_template:
                question_data = execute_answer_logic(
                    selected_template["answer_logic"], 
                    all_games, 
                    selected_template
                )
                
                if question_data and question_data.get("question_text"):
                    # Add metadata
                    question_data.update({
                        "is_dynamic": False,
                        "category": selected_template.get("category", "template_generated"),
                        "generation_method": "template"
                    })
                    
                    # Update history
                    update_question_history(question_data, selected_template.get("category", "unknown"))
                    
                    print(f"✅ Template-generated question: {question_data['question_text'][:50]}...")
                    return question_data
        
        except Exception as template_error:
            print(f"⚠️ Template generation failed: {template_error}")
        
        # Fallback to AI generation (with improved prompt)
        stats = db.get_played_games_stats()
        sample_games = all_games[:5]  # Use first 5 games for context
        
        # Create detailed game context
        game_context = ""
        if sample_games:
            game_details = []
            for game in sample_games:
                episodes_info = f" ({game.get('total_episodes', 0)} eps)" if game.get('total_episodes', 0) > 0 else ""
                status = game.get('completion_status', 'unknown')
                playtime = game.get('total_playtime_minutes', 0)
                genre = game.get('genre', 'unknown')
                game_details.append(
                    f"{game['canonical_name']}{episodes_info} - {status} - {playtime//60}h {playtime%60}m - {genre}")

            game_context = f"Available games: {'; '.join(game_details)}"

        # Enhanced AI prompt with Ash's analytical persona but engaging content
        recent_categories = [q["category"] for q in question_history["last_questions"][-5:]]
        avoid_categories = list(set(recent_categories)) if recent_categories else []
        
        content_prompt = f"""Generate a trivia question about Captain Jonesy's gaming experiences. Deliver it in your analytical style but make the content engaging and conversational.

AVOID these overused categories: {avoid_categories}

PREFERRED QUESTION TYPES (pick one):
🎮 **Genre Adventures**: "What horror game did Jonesy play most recently?" 
🏆 **Gaming Milestones**: "Which was Jonesy's first completed RPG?"
📚 **Series Explorer**: "How many Resident Evil games has Jonesy played?"
🎯 **Gaming Stories**: "What game took Jonesy the most episodes to finish?"
🕐 **Timeline Fun**: "Which game did Jonesy complete first - [Game A] or [Game B]?"
⭐ **Fun Facts**: "What percentage of Jonesy's games are completed?"

AVAILABLE GAMES: {game_context}
Total games: {stats.get('total_games', 0)}

Create a question that focuses on gaming experiences and milestones rather than dry statistics. Phrase it in your analytical style but keep the content interesting.

RETURN ONLY JSON:
{{
    "question_text": "Your analytically-phrased but engaging question here",
    "question_type": "single_answer", 
    "correct_answer": "The answer",
    "is_dynamic": false,
    "category": "ai_generated"
}}

Focus on Captain Jonesy's gaming journey and achievements rather than statistical analysis."""

        prompt = apply_ash_persona_to_ai_prompt(content_prompt, "trivia_generation")

        # Call AI with rate limiting
        response_text, status_message = await call_ai_with_rate_limiting(prompt, JONESY_USER_ID, context)

        if response_text:
            print(f"✅ AI fallback response received: {len(response_text)} characters")
            
            # Parse AI response
            ai_question = robust_json_parse(response_text)
            
            if ai_question and all(key in ai_question for key in ["question_text", "question_type", "correct_answer"]):
                ai_question["generation_method"] = "ai_fallback"
                print(f"✅ AI fallback question generated: {ai_question['question_text'][:50]}...")
                return ai_question
        
        print(f"❌ AI fallback failed: {status_message}")
        return None

    except Exception as e:
        print(f"❌ Error in diverse trivia generation: {e}")
        import traceback
        traceback.print_exc()
        return None


async def create_ai_announcement_content(
        user_content: str,
        target_channel: str,
        user_id: int) -> str:
    """Create AI-enhanced announcement content in Ash's style based on user input"""
    try:
        if not ai_enabled:
            print("AI not enabled, returning original content")
            return user_content

        # Determine the author for context
        if user_id == JONESY_USER_ID:
            author = "Captain Jonesy"
            author_context = "the commanding officer"
        else:
            author = "Sir Decent Jam"
            author_context = "the bot creator and systems architect"

        # Create AI prompt based on target channel using centralized persona
        if target_channel == 'mod':
            content_prompt = f"""Rewrite this announcement content in your analytical, technical style for a moderator briefing.

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a technical briefing for moderators. Be analytical, precise, and focus on:
- Technical implementation details
- Operational efficiency improvements
- System functionality enhancements
- Mission-critical parameters

Use phrases like "Analysis indicates", "System diagnostics confirm", "Operational parameters enhanced", etc.
Keep it professional but maintain your clinical, analytical personality.
Write 2-4 sentences maximum. Be concise but comprehensive."""
            
            prompt = apply_ash_persona_to_ai_prompt(content_prompt, "mod_announcement")

        else:  # user channel
            content_prompt = f"""Rewrite this announcement content in a user-friendly way while maintaining some of your analytical personality.

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a community announcement that's accessible to regular users but still has your analytical undertones. Focus on:
- User benefits and improvements
- How features enhance the user experience
- Clear, helpful explanations
- Practical usage information

Be helpful and informative, but keep subtle hints of your analytical nature.
Write 2-4 sentences maximum. Make it engaging and user-focused."""
            
            prompt = apply_ash_persona_to_ai_prompt(content_prompt, "user_announcement")

        # Call AI with rate limiting
        response_text, status_message = await call_ai_with_rate_limiting(prompt, user_id)

        if response_text:
            enhanced_content = filter_ai_response(response_text)
            print(
                f"AI content enhancement successful: {len(enhanced_content)} characters")
            return enhanced_content
        else:
            print(f"AI content enhancement failed: {status_message}")
            return user_content  # Fallback to original content

    except Exception as e:
        print(f"Error in AI content enhancement: {e}")
        return user_content  # Fallback to original content


def initialize_ai():
    """Initialize AI providers and set global status"""
    global ai_enabled, ai_status_message, primary_ai, backup_ai

    # Setup AI providers
    gemini_ok = setup_ai_provider(
        "gemini", GEMINI_API_KEY, genai, GENAI_AVAILABLE)
    huggingface_ok = setup_ai_provider(
        "huggingface", HUGGINGFACE_API_KEY, requests, HUGGINGFACE_AVAILABLE)

    if gemini_ok:
        primary_ai = "gemini"
        print("✅ Gemini AI configured successfully - set as primary AI")
        if huggingface_ok:
            backup_ai = "huggingface"
            print("✅ Hugging Face AI configured successfully - set as backup AI")
    elif huggingface_ok:
        primary_ai = "huggingface"
        print("✅ Hugging Face AI configured successfully - set as primary AI")

    # Set AI status
    if primary_ai:
        ai_enabled = True
        if backup_ai:
            ai_status_message = f"Online ({primary_ai.title()} + {backup_ai.title()} backup)"
        else:
            ai_status_message = f"Online ({primary_ai.title()} only)"
    else:
        ai_status_message = "No AI available"
        print("❌ No AI systems available - all AI features disabled")


def get_ai_status() -> Dict[str, Any]:
    """Get current AI status and usage statistics"""
    return {
        "enabled": ai_enabled,
        "status_message": ai_status_message,
        "primary_ai": primary_ai,
        "backup_ai": backup_ai,
        "usage_stats": ai_usage_stats.copy()
    }


def is_time_query(prompt: str) -> bool:
    """Check if the prompt is asking for the current time"""
    prompt_lower = prompt.lower()
    time_keywords = [
        "what time is it",
        "current time",
        "what's the time",
        "tell me the time",
        "time is it",
        "chronometer",
        "time check"
    ]
    
    return any(keyword in prompt_lower for keyword in time_keywords)


def handle_time_query(user_id: int) -> str:
    """Handle time queries with proper current time"""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    uk_now = datetime.now(ZoneInfo("Europe/London"))
    
    # Determine DST status for proper timezone naming
    dst_offset = uk_now.dst()
    is_bst = dst_offset is not None and dst_offset.total_seconds() > 0
    timezone_name = "BST" if is_bst else "GMT"
    
    formatted_time = uk_now.strftime(f"%A, %B %d, %Y at %H:%M:%S {timezone_name}")
    
    # Determine the appropriate salutation based on user
    if user_id == JONESY_USER_ID:
        salutation = "Captain Jonesy"
    else:
        salutation = "Sir Decent Jam"
    
    # Return the proper time response without placeholder text
    return f"{salutation}, my internal chronometer indicates the current time is {formatted_time}. I await further instructions."


# Initialize AI on module import
initialize_ai()

# Export list for proper module interface
__all__ = [
    'call_ai_with_rate_limiting',
    'filter_ai_response', 
    'generate_ai_trivia_question',
    'create_ai_announcement_content',
    'initialize_ai',
    'get_ai_status',
    'reset_daily_usage',
    'ai_enabled',
    'ai_status_message',
    'primary_ai',
    'backup_ai',
    'ai_usage_stats'
]
