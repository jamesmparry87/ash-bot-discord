"""
Moderator FAQ Handler

This module provides a clean, maintainable FAQ system that replaces
the hardcoded if/elif chain in the main bot file.
"""

from typing import Any, Dict, List, Optional

from moderator_faq_data import FAQ_DATA


class ModeratorFAQHandler:
    """Handles moderator FAQ queries using structured data"""

    def __init__(
        self,
        violation_channel_id: int,
        members_channel_id: int,
        mod_alert_channel_id: int,
        jonesy_user_id: int,
        jam_user_id: int,
        ai_status_message: str,
    ):
        """Initialize the FAQ handler with dynamic values"""
        self.violation_channel_id = violation_channel_id
        self.members_channel_id = members_channel_id
        self.mod_alert_channel_id = mod_alert_channel_id
        self.jonesy_user_id = jonesy_user_id
        self.jam_user_id = jam_user_id
        self.ai_status_message = ai_status_message

    def find_matching_faq(self, content: str) -> Optional[str]:
        """Find the FAQ topic that matches the given content"""
        content_lower = content.lower()

        for topic, faq_data in FAQ_DATA.items():
            patterns = faq_data.get("patterns", [])
            if any(pattern in content_lower for pattern in patterns):
                return topic

        return None

    def format_content_item(self, item: Any) -> str:
        """Format a content item (string or list)"""
        if isinstance(item, list):
            return "\n".join(item)
        return str(item)

    def substitute_variables(self, text: str) -> str:
        """Replace placeholder variables with actual values"""
        substitutions = {
            "{VIOLATION_CHANNEL_ID}": str(self.violation_channel_id),
            "{MEMBERS_CHANNEL_ID}": str(self.members_channel_id),
            "{MOD_ALERT_CHANNEL_ID}": str(self.mod_alert_channel_id),
            "{JONESY_USER_ID}": str(self.jonesy_user_id),
            "{JAM_USER_ID}": str(self.jam_user_id),
            "{ai_status_message}": self.ai_status_message,
        }

        for placeholder, value in substitutions.items():
            text = text.replace(placeholder, value)

        return text

    def generate_faq_response(self, topic: str) -> str:
        """Generate a formatted FAQ response for the given topic"""
        if topic not in FAQ_DATA:
            return ""

        faq_data = FAQ_DATA[topic]
        title = faq_data.get("title", "")
        sections = faq_data.get("sections", [])

        # Start with title
        response_parts = [self.substitute_variables(title)]

        # Add each section
        for section in sections:
            section_title = section.get("title", "")
            section_content = section.get("content", "")

            if section_title and section_content:
                # Format section with title
                response_parts.append(f"\n**{section_title}:**")
                formatted_content = self.format_content_item(section_content)
                response_parts.append(
                    self.substitute_variables(formatted_content))
            elif section_content:
                # Content without explicit title
                formatted_content = self.format_content_item(section_content)
                response_parts.append(
                    f"\n{self.substitute_variables(formatted_content)}")

        return "\n".join(response_parts)

    def handle_faq_query(self, content: str) -> Optional[str]:
        """Main method to handle FAQ queries"""
        topic = self.find_matching_faq(content)
        if topic:
            return self.generate_faq_response(topic)
        return None

    def get_available_topics(self) -> List[str]:
        """Get list of available FAQ topics for debugging"""
        return list(FAQ_DATA.keys())

    def get_patterns_for_topic(self, topic: str) -> List[str]:
        """Get patterns for a specific topic for debugging"""
        if topic in FAQ_DATA:
            return FAQ_DATA[topic].get("patterns", [])
        return []
