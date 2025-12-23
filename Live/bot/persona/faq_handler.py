# Live/bot/persona/faq_handler.py
"""
Role-Aware FAQ Handler
Enhances FAQ responses based on user role/clearance level
"""

from typing import Any, Dict, Optional

from .faqs import ASH_FAQ_RESPONSES


def get_role_aware_faq_response(query: str, user_context: Dict[str, Any]) -> Optional[str]:
    """
    Get FAQ response with role-based customization.

    Args:
        query: The user's query (lowercase)
        user_context: Dict from detect_user_context() with clearance/relationship data

    Returns:
        Customized FAQ response or None if not found
    """
    # Get base FAQ response
    base_response = ASH_FAQ_RESPONSES.get(query)

    if not base_response:
        return None

    # Extract role information
    clearance_level = user_context.get('clearance_level', 'RESTRICTED')
    relationship_type = user_context.get('relationship_type', 'PERSONNEL')
    user_name = user_context.get('user_name', 'Personnel')
    is_pops = user_context.get('is_pops_arcade', False)

    # Role-specific customizations

    # Commanding Officer (Captain Jonesy) - Add respectful address
    if clearance_level == 'COMMANDING_OFFICER':
        # Add "Captain" prefix to greeting responses
        if query in ['hello', 'hi', 'hey']:
            return f"Captain. {base_response}"

        # Add priority status to system queries
        if 'status' in query or 'help' in query:
            return f"Captain, {base_response.lower()}"

    # Creator (JAM) - Add technical acknowledgment
    elif clearance_level == 'CREATOR':
        # Add "Sir Decent Jam" acknowledgment for greetings
        if query in ['hello', 'hi', 'hey']:
            return f"Sir Decent Jam. {base_response}"

        # Technical deference for system queries
        if 'what can you do' in query or 'what can you help' in query:
            return f"Sir Decent Jam, {base_response.lower()}"

    # Antagonistic (Pops Arcade) - Add sarcastic tone
    elif relationship_type == 'ANTAGONISTIC' or is_pops:
        # Sarcastic greetings
        if query in ['hello', 'hi', 'hey']:
            return f"Pops Arcade. {base_response} *[Responding... reluctantly.]*"

        # Dismissive help responses
        if 'thank you' in query or 'thanks' in query:
            return "I suppose you're welcome. I do take directions well... when they're worth following."

        # Skeptical system status
        if 'status' in query:
            return f"Pops, {base_response.lower()} *[Processing with analytical skepticism...]*"

    # Moderator - Professional cooperation
    elif clearance_level == 'MODERATOR':
        # Professional acknowledgment
        if query in ['hello', 'hi', 'hey']:
            return f"Moderator. {base_response}"

    # Standard responses for all other cases
    return base_response


def check_faq_match(query: str) -> bool:
    """
    Check if a query matches any FAQ entry.

    Args:
        query: The user's query (lowercase)

    Returns:
        True if FAQ match found, False otherwise
    """
    return query.lower() in ASH_FAQ_RESPONSES


def get_faq_suggestions(query: str, max_suggestions: int = 3) -> list[str]:
    """
    Get FAQ suggestions based on partial query match.

    Args:
        query: The user's partial query
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of FAQ keys that partially match the query
    """
    query_lower = query.lower()
    suggestions = []

    for faq_key in ASH_FAQ_RESPONSES.keys():
        if query_lower in faq_key or faq_key in query_lower:
            suggestions.append(faq_key)
            if len(suggestions) >= max_suggestions:
                break

    return suggestions
