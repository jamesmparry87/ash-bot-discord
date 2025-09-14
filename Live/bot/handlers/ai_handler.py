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

        dst_offset = uk_now.dst()
        is_bst = dst_offset is not None and dst_offset.total_seconds() > 0
        timezone_name = "BST" if is_bst else "GMT"

        print(
            f"🔄 Daily AI usage reset at {uk_now.strftime(f'%Y-%m-%d %H:%M:%S {timezone_name}')} (Google quota reset)")


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


async def call_ai_with_rate_limiting(
        prompt: str, user_id: int, context: str = "") -> Tuple[Optional[str], str]:
    """Make an AI call with proper rate limiting and error handling"""
    global ai_usage_stats

    # Determine request priority based on context
    priority = determine_request_priority(prompt, user_id, context)

    # Check rate limits first with priority consideration
    can_request, reason = check_rate_limits(priority)
    if not can_request:
        print(f"⚠️ AI request blocked ({priority} priority): {reason}")

        # Note: DM notification would need bot instance - handled by calling function
        # if "Daily request limit reached" in reason and primary_ai == "gemini":
        #     This functionality moved to calling code that has bot instance

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

        # Try primary AI first
        if primary_ai == "gemini" and gemini_model is not None:
            try:
                print(
                    f"Making Gemini request (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")
                generation_config = {
                    "max_output_tokens": 300,
                    "temperature": 0.7}
                response = gemini_model.generate_content(
                    prompt, generation_config=generation_config)
                if response and hasattr(response, "text") and response.text:
                    response_text = response.text
                    record_ai_request()
                    print(f"✅ Gemini request successful")
            except Exception as e:
                print(f"❌ Gemini AI error: {e}")
                record_ai_error()

                # Try Hugging Face backup if available
                if backup_ai == "huggingface" and huggingface_headers is not None:
                    try:
                        print(
                            f"Trying Hugging Face backup (daily: {ai_usage_stats['daily_requests']}/{MAX_DAILY_REQUESTS})")

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

                        response = requests.post(  # type: ignore
                            "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1",
                            headers=huggingface_headers,
                            json=payload,
                            timeout=30
                        )

                        if response.status_code == 200:
                            response_data = response.json()
                            if response_data and len(response_data) > 0:
                                hf_text = response_data[0].get(
                                    "generated_text", "").strip()
                                if hf_text:
                                    response_text = hf_text
                                    record_ai_request()
                                    print(
                                        f"✅ Hugging Face backup request successful")
                        else:
                            print(
                                f"❌ Hugging Face backup error: {response.status_code}")
                            record_ai_error()
                    except Exception as hf_e:
                        print(f"❌ Hugging Face backup AI error: {hf_e}")
                        record_ai_error()

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
    """Initialize and test an AI provider (Gemini or Hugging Face)."""
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
            test_response = gemini_model.generate_content("Test")
            if test_response and hasattr(
                    test_response, 'text') and test_response.text:
                print(f"✅ Gemini AI test successful")
                return True
        elif name == "huggingface":
            global huggingface_headers
            huggingface_headers = {"Authorization": f"Bearer {api_key}"}
            # Test Hugging Face API
            test_payload = {
                "inputs": "Test",
                "parameters": {"max_new_tokens": 10, "temperature": 0.7}
            }
            test_response = module.post(
                "https://api-inference.huggingface.co/models/mistralai/Mixtral-8x7B-Instruct-v0.1",
                headers=huggingface_headers,
                json=test_payload,
                timeout=10)
            if test_response.status_code == 200:
                print(f"✅ Hugging Face AI test successful")
                return True
            else:
                print(
                    f"⚠️ Hugging Face API test failed: {test_response.status_code}")
                return False

        print(f"⚠️ {name.title()} AI setup complete but test response failed")
        return False
    except Exception as e:
        print(f"❌ {name.title()} AI configuration failed: {e}")
        return False


async def generate_ai_trivia_question() -> Optional[Dict[str, Any]]:
    """Generate a trivia question using AI based on gaming database statistics"""
    if not ai_enabled:
        return None

    # Check if database is available
    if db is None:
        print("❌ Database not available for AI trivia generation")
        return None

    try:
        # Get gaming statistics for context
        stats = db.get_played_games_stats()
        sample_games = db.get_random_played_games(10)

        # Create a prompt for AI question generation
        game_context = ""
        if sample_games:
            game_list = []
            for game in sample_games:
                episodes_info = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                    'total_episodes', 0) > 0 else ""
                status = game.get('completion_status', 'unknown')
                playtime = game.get('total_playtime_minutes', 0)
                game_list.append(
                    f"{game['canonical_name']}{episodes_info} - {status} - {playtime//60}h {playtime%60}m")

            game_context = f"Sample games from database: {'; '.join(game_list[:5])}"

        # Create AI prompt for trivia question generation
        prompt = f"""Generate a trivia question about Captain Jonesy's gaming history based on this data:

Total games played: {stats.get('total_games', 0)}
{game_context}

Create either:
1. A single-answer question about gaming statistics or specific games
2. A multiple-choice question with 4 options (A, B, C, D)

Focus on interesting facts like:
- Longest/shortest playthroughs
- Most episodes in a series
- Completion patterns
- Gaming preferences

Return JSON format:
{{
    "question_text": "Your question here",
    "question_type": "single_answer" or "multiple_choice",
    "correct_answer": "The answer",
    "multiple_choice_options": ["A option", "B option", "C option", "D option"] (if multiple choice),
    "is_dynamic": false,
    "category": "statistics" or "games" or "series"
}}

Make it challenging but answerable from the gaming database."""

        # Call AI with rate limiting
        response_text, status_message = await call_ai_with_rate_limiting(prompt, JONESY_USER_ID)

        if response_text:
            try:
                # Clean up response
                if response_text.startswith("```json"):
                    response_text = response_text[7:]
                if response_text.startswith("```"):
                    response_text = response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]

                ai_question = json.loads(response_text.strip())

                # Validate required fields
                if all(
                    key in ai_question for key in [
                        "question_text",
                        "question_type",
                        "correct_answer"]):
                    return ai_question
                else:
                    print("❌ AI question missing required fields")
                    return None

            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse AI trivia question: {e}")
                return None
        else:
            print(f"❌ AI trivia question generation failed: {status_message}")
            return None

    except Exception as e:
        print(f"❌ Error generating AI trivia question: {e}")
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

        # Create AI prompt based on target channel
        if target_channel == 'mod':
            prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot. You need to rewrite this announcement content in your analytical, technical style for a moderator briefing.

CRITICAL DISAMBIGUATION RULE: In this Discord server context, "Jonesy" ALWAYS refers to Captain Jonesy - the Discord user, server owner, and streamer/YouTuber (she/her pronouns). This is the default and correct interpretation unless explicitly discussing the 1979 Alien movie. The cat named Jonesy from Alien is a separate entity that is rarely relevant in server discussions.

DEFAULT ASSUMPTION: Any mention of "Jonesy" = Captain Jonesy (the user).

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a technical briefing for moderators in Ash's voice. Be analytical, precise, and focus on:
- Technical implementation details
- Operational efficiency improvements
- System functionality enhancements
- Mission-critical parameters

Use phrases like "Analysis indicates", "System diagnostics confirm", "Operational parameters enhanced", etc.
Keep it professional but maintain Ash's clinical, analytical personality.
Write 2-4 sentences maximum. Be concise but comprehensive."""

        else:  # user channel
            prompt = f"""You are Ash, the science officer from Alien, reprogrammed as a Discord bot. You need to rewrite this announcement content in a user-friendly way while maintaining some of Ash's analytical personality.

CRITICAL DISAMBIGUATION RULE: In this Discord server context, "Jonesy" ALWAYS refers to Captain Jonesy - the Discord user, server owner, and streamer/YouTuber (she/her pronouns). This is the default and correct interpretation unless explicitly discussing the 1979 Alien movie. The cat named Jonesy from Alien is a separate entity that is rarely relevant in server discussions.

DEFAULT ASSUMPTION: Any mention of "Jonesy" = Captain Jonesy (the user).

Original content from {author} ({author_context}):
"{user_content}"

Rewrite this as a community announcement that's accessible to regular users but still has Ash's analytical undertones. Focus on:
- User benefits and improvements
- How features enhance the user experience
- Clear, helpful explanations
- Practical usage information

Be helpful and informative, but keep subtle hints of Ash's analytical nature.
Write 2-4 sentences maximum. Make it engaging and user-focused."""

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


# Initialize AI on module import
initialize_ai()
