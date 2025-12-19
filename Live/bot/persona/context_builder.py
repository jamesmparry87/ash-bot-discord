# Live/bot/persona/context_builder.py
import datetime


def build_ash_context(user_name, user_roles, is_pops_arcade=False):
    """
    Constructs the dynamic context string to append to the system prompt.
    Uses case-insensitive matching for robustness.
    """
    
    # Normalize inputs for case-insensitive comparisons
    user_name_lower = user_name.lower()
    user_roles_lower = [r.lower() for r in user_roles]

    # 1. Determine Clearance Level (case-insensitive)
    if any(role in user_roles_lower for role in ["captain", "owner"]):
        clearance = "COMMANDING OFFICER (Absolute Authority)"
    elif any(role in user_roles_lower for role in ["moderator", "admin", "creator"]):
        clearance = "CREATOR/MODERATOR (Authorized for Operational Data)"
    else:
        clearance = "STANDARD PERSONNEL (Restricted Access)"

    # 2. Determine Relationship Status (case-insensitive name matching)
    relationship = "Neutral/Personnel"
    if is_pops_arcade:
        relationship = "ANTAGONISTIC (Question his analysis)"
    elif "decentjam" in user_name_lower or "sir decent jam" in user_name_lower:
        relationship = "CREATOR (Technical Deference)"
    elif "jonesy" in user_name_lower or "captain" in user_name_lower:
        relationship = "COMMANDING OFFICER (Protect at all costs)"

    # 3. Time Context (to explain latency)
    # This helps Ash explain why he doesn't know about a video uploaded 5 mins ago
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    data_freshness = "Data cached: Weekly batch analysis active."
    
    # Debug logging for verification
    print(f"📊 Context Built: Clearance='{clearance}', Relationship='{relationship}'")

    # 4. Construct the String
    context_string = f"""
    --- CURRENT OPERATIONAL CONTEXT ---
    User Identity: {user_name}
    User Roles: {user_roles}
    Calculated Clearance: {clearance}
    Relational Protocol: {relationship}
    System Date: {current_date}
    Database Status: {data_freshness}
    -----------------------------------
    """

    return context_string
