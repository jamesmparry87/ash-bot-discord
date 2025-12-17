# Live/bot/persona/context_builder.py
import datetime

def build_ash_context(user_name, user_roles, is_pops_arcade=False):
    """
    Constructs the dynamic context string to append to the system prompt.
    """
    
    # 1. Determine Clearance Level
    if "Captain" in user_roles or "Owner" in user_roles:
        clearance = "COMMANDING OFFICER (Absolute Authority)"
    elif "Moderator" in user_roles or "Admin" in user_roles:
        clearance = "MODERATOR (Authorized for Operational Data)"
    else:
        clearance = "STANDARD PERSONNEL (Restricted Access)"

    # 2. Determine Relationship Status
    relationship = "Neutral/Personnel"
    if is_pops_arcade:
        relationship = "ANTAGONISTIC (Question his analysis)"
    elif user_name == "DecentJam":
        relationship = "CREATOR (Technical Deference)"
    elif user_name == "JonesySpaceCat":
        relationship = "COMMANDING OFFICER (Protect at all costs)"

    # 3. Time Context (to explain latency)
    # This helps Ash explain why he doesn't know about a video uploaded 5 mins ago
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    data_freshness = "Data cached: Weekly batch analysis active."

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