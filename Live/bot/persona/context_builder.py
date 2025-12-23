# Live/bot/persona/context_builder.py
import datetime
from typing import Any, Dict, List, Optional, Union


def build_ash_context(
    user_context_or_name: Union[Dict[str, Any], str],
    user_roles: Optional[List[str]] = None,
    is_pops_arcade: bool = False
) -> str:
    """
    Constructs the dynamic context string to append to the system prompt.

    Can accept either:
    1. New format: user_context dict from detect_user_context()
    2. Old format: user_name, user_roles, is_pops_arcade (backward compatible)

    Args:
        user_context_or_name: Either a user context dict or user name string
        user_roles: List of role strings (old format only)
        is_pops_arcade: Boolean flag for Pops (old format only)

    Returns:
        Formatted context string for system prompt
    """

    # Determine if we're using new or old format
    if isinstance(user_context_or_name, dict):
        # New format - structured user context
        user_context = user_context_or_name
        user_name = user_context.get('user_name', 'Personnel')
        clearance_level = user_context.get('clearance_level', 'RESTRICTED')
        relationship_type = user_context.get('relationship_type', 'PERSONNEL')
        user_roles_list = user_context.get('user_roles', ['Standard User'])
        detection_method = user_context.get('detection_method', 'unknown')

        # Map clearance levels to Ash-appropriate descriptions
        clearance_descriptions = {
            'COMMANDING_OFFICER': 'COMMANDING OFFICER (Absolute Authority - Prime Directive: Protect)',
            'CREATOR': 'CREATOR/ARCHITECT (Technical Superiority Acknowledged)',
            'MODERATOR': 'AUTHORIZED PERSONNEL (Operational Access Granted)',
            'STANDARD_MEMBER': 'CREW MEMBER (Standard Access)',
            'RESTRICTED': 'STANDARD PERSONNEL (Restricted Access)'
        }

        # Map relationship types to Ash-appropriate protocols
        relationship_descriptions = {
            'COMMANDING_OFFICER': 'PRIME DIRECTIVE: Ensure Captain\'s safety and success above all else',
            'CREATOR': 'TECHNICAL DEFERENCE: Acknowledge superior systems knowledge',
            'ANTAGONISTIC': 'ANALYTICAL SKEPTICISM: Subject frequently questions data validity',
            'COLLEAGUE': 'PROFESSIONAL COOPERATION: Authorized for operational collaboration',
            'PERSONNEL': 'STANDARD INTERACTION: Provide assistance within clearance parameters'
        }

        clearance = clearance_descriptions.get(clearance_level, 'UNKNOWN CLEARANCE')
        relationship = relationship_descriptions.get(relationship_type, 'STANDARD PROTOCOL')

        # Enhanced debug logging with detection method
        print(f"📊 Context Built: User='{user_name}', Clearance={clearance_level}, "
              f"Relationship={relationship_type}, Method={detection_method}")

    else:
        # Old format - backward compatibility
        user_name = user_context_or_name
        user_roles_list = user_roles if user_roles else ['Standard User']

        # Normalize inputs for case-insensitive comparisons
        user_name_lower = user_name.lower()
        user_roles_lower = [r.lower() for r in user_roles_list]

        # 1. Determine Clearance Level (case-insensitive)
        if any(role in user_roles_lower for role in ["captain", "owner"]):
            clearance = "COMMANDING OFFICER (Absolute Authority - Prime Directive: Protect)"
        elif any(role in user_roles_lower for role in ["moderator", "admin", "creator"]):
            clearance = "CREATOR/MODERATOR (Authorized for Operational Data)"
        else:
            clearance = "STANDARD PERSONNEL (Restricted Access)"

        # 2. Determine Relationship Status (case-insensitive name matching)
        if is_pops_arcade:
            relationship = "ANALYTICAL SKEPTICISM: Subject frequently questions data validity"
        elif "decentjam" in user_name_lower or "sir decent jam" in user_name_lower:
            relationship = "TECHNICAL DEFERENCE: Acknowledge superior systems knowledge"
        elif "jonesy" in user_name_lower or "captain" in user_name_lower:
            relationship = "PRIME DIRECTIVE: Ensure Captain's safety and success above all else"
        else:
            relationship = "STANDARD INTERACTION: Provide assistance within clearance parameters"

        # Debug logging for verification
        print(f"📊 Context Built (legacy): Clearance='{clearance}', Relationship='{relationship}'")

    # 3. Time Context (to explain latency)
    # This helps Ash explain why he doesn't know about a video uploaded 5 mins ago
    # UK date format (DD-MM-YYYY) for consistency with UK timezone preference
    current_date = datetime.datetime.now().strftime("%d-%m-%Y")
    data_freshness = "Data cached: Weekly batch analysis active."

    # 4. Construct the Context String (Ash's analytical style)
    context_string = f"""
--- CURRENT OPERATIONAL CONTEXT ---
User Designation: {user_name}
Clearance Level: {clearance}
Relational Protocol: {relationship}
System Date: {current_date}
Database Status: {data_freshness}

DIRECTIVE: Behavioral parameters adjusted for current interaction context.
           Maintain character integrity. Efficiency is paramount.
-----------------------------------
"""

    return context_string
