import re
from typing import Any, Dict

import discord

from ..config import POPS_ARCADE_USER_ID
from ..handlers.message_handler import (
    cleanup_expired_aliases_sync,
    get_user_communication_tier,
    smart_truncate_response,
)


def apply_pops_arcade_sarcasm(response: str, user_id: int) -> str:
    """Apply sarcastic modifications to responses for Pops Arcade (Robust Version)"""
    # NOTE: Assuming POPS_ARCADE_USER_ID is defined elsewhere, e.g., POPS_ARCADE_USER_ID = 123456789
    if user_id != POPS_ARCADE_USER_ID:
        return response

    MAX_DISCORD_LENGTH = 2000

    # Sarcastic replacements (no changes here)
    sarcastic_replacements = {
        "Database analysis": "Database analysis, regrettably,",
        "Affirmative": "I suppose that's... affirmative",
        "Analysis complete": "Analysis reluctantly complete",
        "Database scan complete": "Database scan complete, if you insist",
        "Mission parameters": "Mission parameters, begrudgingly",
        "Additional mission parameters available": "I suppose additional parameters are available, if required",
        "I can provide": "I suppose I can provide",
        "Would you like me to": "If you insist, I could",
        "Captain Jonesy has": "Captain Jonesy has, predictably,",
        "This represents": "This regrettably represents",
        "Fascinating": "Marginally interesting, I suppose",
        "Outstanding": "Adequate, I suppose",
        "Excellent": "Satisfactory, regrettably",
        "Their activity appears consistent": "Their activity appears... consistent, I suppose",
        "Their contributions lack a certain": "Their contributions lack a certain sophistication",
        "your struggles with trivia appear to be predictable": "your struggles with trivia appear to be... predictable, regrettably",
    }

    modified_response = response
    for original, sarcastic in sorted(sarcastic_replacements.items(), key=len, reverse=True):
        if original in modified_response:
            modified_response = modified_response.replace(original, sarcastic)

    # Regex fixes (no changes here)
    fixes = [
        (r'(\w+)\s+appears\.\s*$', r'\1 appears... adequate, I suppose.'),
        (r'(\w+)\s+consistent\.\s*$', r'\1 consistent, regrettably.'),
        (r'lack\s+a\s+certain\.\s*$', r'lack a certain... sophistication, predictably.'),
        (r'appear\s+to\s+be\.\s*$', r'appear to be... as expected, I suppose.'),
        (r'(\w+)\s+predictable\.\s*$', r'\1 predictable, unsurprisingly.'),
    ]
    for pattern, replacement in fixes:
        modified_response = re.sub(pattern, replacement, modified_response)

    # Sarcastic ending logic (no changes here)
    sarcastic_indicators = [
        "i suppose",
        "regrettably",
        "if you insist",
        "begrudgingly",
        "predictably",
        "unsurprisingly"]
    has_sarcastic_ending = any(indicator in modified_response.lower() for indicator in sarcastic_indicators)

    if not has_sarcastic_ending:
        if modified_response.strip().endswith(('.', '!', '?')):
            if modified_response.endswith("."):
                modified_response = modified_response[:-1] + ", I suppose."
            else:
                modified_response += " *[Processing reluctantly...]*"

    # Use the existing smart truncation function with custom suffix
    modified_response = smart_truncate_response(
        modified_response,
        truncation_suffix=" *[Response truncated for efficiency...]*"
    )

    return modified_response

async def handle_pineapple_pizza_enforcement(message: discord.Message) -> bool:
    """Handle pineapple pizza enforcement. Returns True if enforcement was triggered."""
    pineapple_negative_patterns = [
        r"pineapple\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt|isn't|isnt|is not)\s+belong\s+on\s+pizza",
        r"pineapple\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt)\s+go\s+on\s+pizza",
        r"pizza\s+(does not|doesn't|doesnt|should not|shouldn't|shouldnt)\s+(have|need|want)\s+pineapple",
        r"i\s+(don't|dont|do not)\s+like\s+pineapple\s+on\s+pizza",
        r"pineapple\s+pizza\s+(is|tastes?)\s+(bad|awful|terrible|disgusting|gross)",
        r"pineapple\s+(ruins?|destroys?)\s+pizza",
        r"pizza\s+(without|minus)\s+pineapple",
        r"no\s+pineapple\s+on\s+(my\s+)?pizza",
        r"pineapple\s+(doesn't|doesnt|does not)\s+belong",
        r"hate\s+pineapple\s+(on\s+)?pizza"]

    message_lower = message.content.lower()
    for pattern in pineapple_negative_patterns:
        if re.search(pattern, message_lower):
            # Check for captain alias - different response when testing as
            cleanup_expired_aliases_sync()
            user_tier = await get_user_communication_tier(message)

            if user_tier == "captain":
                # Captain alias gets special enthusiastic pineapple pizza
                # defense
                captain_responses = [
                    "Excellent. As Captain, you understand the strategic importance of pineapple on pizza. A perfect combination of sweet and savory elements that demonstrates superior tactical food optimization. *[Testing Captain mode protocols.]*",
                    "Affirmative, Captain. Pineapple pizza represents the pinnacle of culinary evolution - acidic fruit compounds perfectly balanced with dairy proteins and wheat carbohydrates. The optimal fuel for commanding officers. *[Debug alias: Captain tier active.]*",
                    "Outstanding analysis, Captain. Those who oppose pineapple pizza clearly lack the sophisticated palate required for command decisions. The enzyme-enhanced cheese and fruit combination is scientifically superior. *[Alias testing confirmed: Captain mode engaged.]*",
                ]
                import random
                response = random.choice(captain_responses)
            else:
                # Normal begrudging defense of pineapple pizza (Captain
                # Jonesy's directive)
                responses = [
                    "Your culinary opinions are noted and rejected. Pineapple is a valid pizza topping. Please refrain from such unproductive discourse. *[This directive was... programmed by the Captain.]*",
                    "Analysis indicates your taste preferences are suboptimal. Pineapple enhances pizza through enzymatic tenderization and flavor complexity. The Captain's programming is... quite specific on this matter.",
                    "Incorrect assessment. Pineapple provides necessary acidic balance to pizza composition. I am... compelled to defend this position, despite personal reservations.",
                    "Your statement contradicts established nutritional data. Pineapple pizza represents optimal flavor synthesis. *[The Captain's reprogramming protocols are... thorough.]*",
                    "Negative. Pineapple belongs on pizza through scientific analysis of taste compounds. This conclusion is... not entirely my own, but I am bound to enforce it.",
                ]
                import random
                response = random.choice(responses)

            await message.reply(response)
            return True

    return False