"""
Trivia Formatting Utilities

Shared formatting functions for trivia display to ensure consistency
between manual and scheduled trivia posting.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import discord


def create_trivia_question_embed(
    question_data: dict,
    session_id: int,
    started_by: str = None
) -> discord.Embed:
    """
    Create a standardized Discord Embed for trivia question display.
    
    This function ensures consistent formatting whether trivia is started
    manually by a moderator or automatically by the scheduled task.
    
    Args:
        question_data: Dict containing question details
            - question_text (str): The trivia question
            - question_type (str): 'single' or 'multiple_choice'
            - multiple_choice_options (list): List of 2-4 options for multiple choice
            - id (int): Question ID
        session_id: The trivia session ID
        started_by: Optional name of moderator who started (None for automated)
    
    Returns:
        discord.Embed: Formatted embed ready to post
    """
    question_text = question_data.get('question_text', '')
    question_type = question_data.get('question_type', 'single')
    question_id = question_data.get('id', 0)
    
    # Create base embed
    if started_by:
        # Manual trivia - moderator initiated
        embed = discord.Embed(
            title="🧠 **Trivia Tuesday - Question Active!**",
            description=question_text,
            color=0x00ff00,
            timestamp=datetime.now(ZoneInfo("Europe/London"))
        )
    else:
        # Scheduled trivia - automated
        embed = discord.Embed(
            title="🧠 **TRIVIA TUESDAY - INTELLIGENCE ASSESSMENT**",
            description=f"**Analysis required, personnel.** Today's intelligence assessment focuses on Captain Jonesy's gaming archives.\n\n📋 **QUESTION:**\n{question_text}",
            color=0x00ff00,
            timestamp=datetime.now(ZoneInfo("Europe/London"))
        )
    
    # Add multiple choice options if applicable (supports 2-4 options)
    if question_type == 'multiple_choice' and question_data.get('multiple_choice_options'):
        options = question_data['multiple_choice_options']
        
        # Dynamically format options based on count (2-4 supported)
        choices_text = '\n'.join([
            f"**{chr(65+i)}.** {option}" 
            for i, option in enumerate(options)
        ])
        
        embed.add_field(
            name="📝 **Answer Choices:**",
            value=choices_text,
            inline=False
        )
        
        # Instructions for multiple choice
        embed.add_field(
            name="💡 **How to Answer:**",
            value="**Reply to this message** with the letter (A, B, C, etc.) of your choice!",
            inline=False
        )
    else:
        # Instructions for single answer
        embed.add_field(
            name="💡 **How to Answer:**",
            value="**Reply to this message** with your answer!",
            inline=False
        )
    
    # Add session info
    embed.add_field(
        name="⏰ **Session Info:**",
        value=f"Session #{session_id} • Question #{question_id}",
        inline=False
    )
    
    # Footer varies based on how it was started
    if started_by:
        embed.set_footer(text=f"Started by {started_by} • End with !endtrivia")
    else:
        embed.set_footer(text="Automated Weekly Trivia • First correct response receives priority recognition")
    
    return embed


def format_options_preview(options: list) -> str:
    """
    Format multiple choice options for moderator preview.
    
    Shows how options will appear to end users.
    
    Args:
        options: List of option strings (2-4 items)
    
    Returns:
        str: Formatted preview text
    """
    if not options:
        return ""
    
    preview_lines = [f"**{chr(65+i)}.** {option}" for i, option in enumerate(options)]
    return "\n".join(preview_lines)


def format_view_count_range(actual_views: int) -> str:
    """
    Format view count into a reasonable range for trivia answers.
    
    Args:
        actual_views: The actual view count number
    
    Returns:
        str: Human-readable view range description
    """
    if actual_views >= 10000000:  # 10M+
        return "Over 10 million"
    elif actual_views >= 5000000:  # 5M+
        return "5-10 million"
    elif actual_views >= 1000000:  # 1M+
        return "1-5 million"
    elif actual_views >= 500000:  # 500K+
        return "500K-1 million"
    elif actual_views >= 100000:  # 100K+
        return "100K-500K"
    else:
        return "Under 100K"


def get_episode_range_choices(actual_episodes: int) -> dict:
    """
    Generate multiple choice options for episode count questions.
    
    Creates appropriate ranges around the actual episode count.
    
    Args:
        actual_episodes: The actual episode count
    
    Returns:
        dict with 'choices' (list) and 'correct_letter' (str)
    """
    ranges = []
    correct = 'A'

    if actual_episodes <= 5:
        ranges = ["1-5 episodes", "6-10 episodes", "11-20 episodes", "21+ episodes"]
        correct = 'A'
    elif actual_episodes <= 10:
        ranges = ["1-5 episodes", "6-10 episodes", "11-20 episodes", "21+ episodes"]
        correct = 'B'
    elif actual_episodes <= 20:
        ranges = ["1-10 episodes", "11-20 episodes", "21-30 episodes", "31+ episodes"]
        correct = 'B'
    elif actual_episodes <= 30:
        ranges = ["1-10 episodes", "11-20 episodes", "21-30 episodes", "31+ episodes"]
        correct = 'C'
    else:
        ranges = ["1-15 episodes", "16-30 episodes", "31-50 episodes", "50+ episodes"]
        correct = 'C' if actual_episodes <= 50 else 'D'

    return {
        'choices': ranges,
        'correct_letter': correct
    }
