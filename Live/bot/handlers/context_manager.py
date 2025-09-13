"""
Context Manager Module

Manages conversation context for natural language game queries.
Enables follow-up questions and pronoun resolution for improved user experience.
"""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..config import JONESY_USER_ID

# Global conversation context storage
# Structure: {channel_id: {user_id: ConversationContext}}
conversation_contexts: Dict[int, Dict[int, 'ConversationContext']] = {}


class ConversationContext:
    """Stores conversation context for a specific user in a channel"""

    def __init__(self, user_id: int, channel_id: int):
        self.user_id = user_id
        self.channel_id = channel_id
        self.last_activity = datetime.now(ZoneInfo("Europe/London"))

        # Context tracking
        self.last_mentioned_game: Optional[str] = None
        self.last_query_type: Optional[str] = None
        self.last_subject: str = "jonesy"  # Default subject is always Jonesy
        self.recent_games: List[str] = []  # Last few games mentioned
        # Recent message context
        self.message_history: List[Dict[str, Any]] = []

        # Statistical context
        self.last_stats_context: Optional[Dict[str, Any]] = None
        self.last_series_mentioned: Optional[str] = None

    def add_message(self, content: str, message_type: str = "user"):
        """Add a message to the conversation history"""
        self.last_activity = datetime.now(ZoneInfo("Europe/London"))

        # Keep only recent messages (last 5)
        if len(self.message_history) >= 5:
            self.message_history.pop(0)

        self.message_history.append({
            "content": content,
            "type": message_type,
            "timestamp": self.last_activity
        })

    def update_game_context(
            self,
            game_name: str,
            query_type: Optional[str] = None):
        """Update game context with new game mention"""
        self.last_mentioned_game = game_name
        if query_type:
            self.last_query_type = query_type

        # Add to recent games if not already there
        if game_name not in self.recent_games:
            self.recent_games.append(game_name)
            # Keep only last 3 games
            if len(self.recent_games) > 3:
                self.recent_games.pop(0)

    def update_series_context(self, series_name: str):
        """Update series context"""
        self.last_series_mentioned = series_name

    def is_expired(self, minutes: int = 30) -> bool:
        """Check if context has expired due to inactivity"""
        cutoff = datetime.now(ZoneInfo("Europe/London")) - \
            timedelta(minutes=minutes)
        return self.last_activity < cutoff


def get_or_create_context(
        user_id: int,
        channel_id: int) -> ConversationContext:
    """Get or create conversation context for a user in a channel"""
    if channel_id not in conversation_contexts:
        conversation_contexts[channel_id] = {}

    if user_id not in conversation_contexts[channel_id]:
        conversation_contexts[channel_id][user_id] = ConversationContext(
            user_id, channel_id)

    return conversation_contexts[channel_id][user_id]


def cleanup_expired_contexts():
    """Remove expired conversation contexts"""
    expired_contexts = []

    for channel_id, channel_contexts in conversation_contexts.items():
        for user_id, context in channel_contexts.items():
            if context.is_expired():
                expired_contexts.append((channel_id, user_id))

    for channel_id, user_id in expired_contexts:
        del conversation_contexts[channel_id][user_id]
        print(
            f"Cleaned up expired context for user {user_id} in channel {channel_id}")


def resolve_context_references(
        content: str, context: ConversationContext) -> Tuple[str, Dict[str, Any]]:
    """
    Resolve pronouns and references in content using conversation context.
    Returns (resolved_content, context_info)
    """
    resolved_content = content
    context_info = {}

    # Subject resolution (she/her -> Jonesy)
    subject_patterns = [
        (r'\bshe\b', 'jonesy'),
        (r'\bher\b', 'jonesy'),
        (r'\bcaptain\b', 'jonesy'),
        (r'\bjonesyspacecat\b', 'jonesy')
    ]

    for pattern, replacement in subject_patterns:
        if re.search(pattern, resolved_content, re.IGNORECASE):
            resolved_content = re.sub(
                pattern,
                'jonesy',
                resolved_content,
                flags=re.IGNORECASE)
            context_info['subject_resolved'] = True

    # Game/object resolution (it -> last mentioned game)
    if context.last_mentioned_game:
        object_patterns = [
            r'\bit\b',
            r'\bthat\s+(game|title)\b',
            r'\bthe\s+game\b',
            r'\bthat\s+one\b'
        ]

        for pattern in object_patterns:
            if re.search(pattern, resolved_content, re.IGNORECASE):
                resolved_content = re.sub(
                    pattern,
                    context.last_mentioned_game,
                    resolved_content,
                    flags=re.IGNORECASE
                )
                context_info['game_resolved'] = context.last_mentioned_game
                break

    # Series resolution
    if context.last_series_mentioned:
        series_patterns = [
            r'\bthat\s+series\b',
            r'\bthe\s+series\b',
            r'\bthose\s+games\b'
        ]

        for pattern in series_patterns:
            if re.search(pattern, resolved_content, re.IGNORECASE):
                resolved_content = re.sub(
                    pattern,
                    context.last_series_mentioned,
                    resolved_content,
                    flags=re.IGNORECASE
                )
                context_info['series_resolved'] = context.last_series_mentioned
                break

    return resolved_content, context_info


def detect_follow_up_intent(
        content: str, context: ConversationContext) -> Optional[Dict[str, Any]]:
    """
    Detect if this is a follow-up question that needs context resolution.
    Returns intent information or None if not a follow-up.
    """
    content_lower = content.lower()

    # Follow-up question patterns
    follow_up_patterns = [
        # Duration/time follow-ups
        {
            'patterns': [
                r'how long.*played.*it',
                r'how much time.*it',
                r'what.*playtime.*it',
                r'how many hours.*it',
                r'how long.*take.*complete.*it'
            ],
            'intent': 'duration_followup',
            'needs_game': True
        },

        # Status follow-ups
        {
            'patterns': [
                r'did.*complete.*it',
                r'finish.*it',
                r'what.*status.*it',
                r'still playing.*it'
            ],
            'intent': 'status_followup',
            'needs_game': True
        },

        # Episode follow-ups
        {
            'patterns': [
                r'how many episodes.*it',
                r'episode count.*it',
                r'how many parts.*it'
            ],
            'intent': 'episode_followup',
            'needs_game': True
        },

        # Series follow-ups
        {
            'patterns': [
                r'other.*games.*series',
                r'more.*that.*series',
                r'what else.*series'
            ],
            'intent': 'series_followup',
            'needs_series': True
        },

        # General follow-ups
        {
            'patterns': [
                r'what about.*her',
                r'how about.*she',
                r'tell me more.*her',
                r'what else.*she'
            ],
            'intent': 'general_followup',
            'needs_subject': True
        }
    ]

    for follow_up in follow_up_patterns:
        for pattern in follow_up['patterns']:
            if re.search(pattern, content_lower):
                # Check if we have required context
                if follow_up.get(
                        'needs_game') and not context.last_mentioned_game:
                    continue
                if follow_up.get(
                        'needs_series') and not context.last_series_mentioned:
                    continue

                return {
                    'intent': follow_up['intent'],
                    'original_content': content,
                    'context_game': context.last_mentioned_game,
                    'context_series': context.last_series_mentioned,
                    'matched_pattern': pattern
                }

    return None


def extract_mentioned_games(content: str) -> List[str]:
    """Extract potential game names mentioned in content"""
    # This is a simple implementation - could be enhanced with NLP
    games_mentioned = []

    # Look for quoted game names
    quoted_games = re.findall(r"['\"]([^'\"]+)['\"]", content)
    games_mentioned.extend(quoted_games)

    # Look for common game name patterns
    # This could be enhanced with a database lookup
    game_patterns = [
        r'\b([A-Z][a-z]+(?: [A-Z][a-z]+)*)\b(?:\s+(?:game|series))?',
    ]

    for pattern in game_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            if len(match.split()) <= 4:  # Reasonable game name length
                games_mentioned.append(match)

    return list(set(games_mentioned))  # Remove duplicates


def generate_contextual_response_hints(context: ConversationContext) -> str:
    """Generate response hints based on conversation context"""
    hints = []

    if context.last_mentioned_game:
        hints.append(f"Last discussed: {context.last_mentioned_game}")

    if context.last_series_mentioned:
        hints.append(f"Series context: {context.last_series_mentioned}")

    if context.recent_games:
        recent = ", ".join(context.recent_games[-2:])  # Last 2 games
        hints.append(f"Recent games: {recent}")

    return " | ".join(hints) if hints else ""


def should_use_context(content: str) -> bool:
    """
    Determine if a query should use conversation context.
    Returns True for ambiguous queries that likely need context resolution.
    """
    content_lower = content.lower()

    # Ambiguous pronouns that need context
    ambiguous_patterns = [
        r'\bit\b',
        r'\bshe\b',
        r'\bher\b',
        r'\bthat\s+(game|one|series)\b',
        r'\bthe\s+game\b',
        r'\bthose\s+games\b'
    ]

    for pattern in ambiguous_patterns:
        if re.search(pattern, content_lower):
            return True

    # Short follow-up questions
    if len(content.split()) <= 6:
        follow_up_starters = [
            'how long', 'how much', 'what about', 'tell me',
            'did she', 'has she', 'when did', 'where did',
            'how many', 'which one'
        ]

        for starter in follow_up_starters:
            if content_lower.startswith(starter):
                return True

    return False
