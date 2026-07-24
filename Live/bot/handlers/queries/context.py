import re
from typing import Any, Match, Optional, Tuple

import discord

from ...config import GAME_RECOMMENDATION_CHANNEL_ID, POPS_ARCADE_USER_ID
from ...database import get_database
from ...persona.sarcasm import apply_pops_arcade_sarcasm
from ...utils.text_processing import smart_truncate_response
from ..context_manager import ConversationContext, cleanup_expired_contexts, get_or_create_context
from ..message_handler import get_user_communication_tier

db = get_database()


async def _handle_ranking_follow_up(message: discord.Message, context: 'ConversationContext') -> bool:
    """Handles follow-up questions about a previously generated ranked list."""
    content = message.content.lower()
    ranked_list = context.last_ranked_list
    if not ranked_list:
        return False

    # Find numbers in the user's query (e.g., "third", "4th", "5")
    ranks_to_show = []
    word_to_num = {"third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}

    # Simple number parsing
    for word in content.split():
        clean_word = word.strip('.,?!').replace('rd', '').replace('th', '').replace('st', '')
        if clean_word.isdigit():
            ranks_to_show.append(int(clean_word))
        elif clean_word in word_to_num:
            ranks_to_show.append(word_to_num[clean_word])

    # Handle "next three", "other five", etc.
    if not ranks_to_show:
        if "next" in content or "other" in content or "rest" in content:
            # Assume they want the next few after the last ones shown (usually 2)
            start_index = 2
            count = 3  # Default to showing the next 3
            ranks_to_show.extend(range(start_index + 1, start_index + 1 + count))

    if not ranks_to_show:
        # Default to showing the 3rd, 4th, 5th if no numbers are found
        ranks_to_show.extend([3, 4, 5])

    ranks_to_show = sorted(list(set(ranks_to_show)))  # Remove duplicates and sort

    response_parts = []
    for rank in ranks_to_show:
        index = rank - 1
        if 0 <= index < len(ranked_list):
            game = ranked_list[index]
            response_parts.append(f"**#{rank}:** '{game['canonical_name']}' ({game.get('youtube_views', 0):,} views)")
        else:
            response_parts.append(f"**#{rank}:** No data available.")

    if not response_parts:
        await message.reply("Analysis indicates no further data is available for the requested ranks.")
        return True

    full_response = "Continuing analysis of YouTube engagement data:\n\n" + "\n".join(response_parts)
    await message.reply(full_response)
    return True


async def handle_context_aware_query(message: discord.Message) -> bool:
    """
    Handle queries with conversation context awareness.
    Returns True if query was processed, False if it should fall back to normal processing.
    """
    from ..message_handler import route_query
    from ..context_manager import detect_follow_up_intent, resolve_context_references, should_use_context
    from .details import (
        handle_game_details_query,
        handle_game_status_query,
        handle_genre_query,
        handle_recommendation_query,
        handle_year_query,
    )
    from .statistical import handle_statistical_query

    try:
        # Clean up expired contexts periodically
        cleanup_expired_contexts()

        # Get or create conversation context for this user/channel
        context = get_or_create_context(message.author.id, message.channel.id)

        # FIRST: Check if this is a pending clarification response (Issue #1 Fix)
        if context.pending_clarification == "playtime_vs_episodes":
            content_lower = message.content.lower()

            if any(word in content_lower for word in ["playtime", "hours", "time", "longest"]):
                # User wants playtime metric
                playtime_stats = context.clarification_data.get('playtime_stats', [])
                if playtime_stats:
                    top_game = playtime_stats[0]
                    hours = round(top_game['total_playtime_minutes'] / 60, 1)
                    response = f"Playtime analysis confirmed. '{top_game['canonical_name']}' has the most playtime with **{hours} hours**."

                    # Add follow-up suggestion
                    if len(playtime_stats) > 1:
                        second_game = playtime_stats[1]
                        second_hours = round(second_game['total_playtime_minutes'] / 60, 1)
                        response += f" Secondary analysis: '{second_game['canonical_name']}' follows with {second_hours} hours. Would you like me to analyze the complete playtime rankings or compare completion efficiency patterns?"

                    await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))
                    context.clear_pending_clarification()
                    context.add_message(message.content, "user")
                    context.add_message("clarification_resolved_playtime", "bot")
                    return True

            elif any(word in content_lower for word in ["episode", "episodes", "parts", "series"]):
                # User wants episodes metric
                episode_stats = context.clarification_data.get('episode_stats', [])
                if episode_stats:
                    top_game = episode_stats[0]
                    response = f"Episode analysis confirmed. '{top_game['canonical_name']}' has the most episodes with **{top_game['total_episodes']} parts**."

                    # Add follow-up suggestion
                    if len(episode_stats) > 1:
                        second_game = episode_stats[1]
                        response += f" Secondary analysis: '{second_game['canonical_name']}' follows with {second_game['total_episodes']} episodes. Would you like me to examine episode pacing patterns or analyze completion timelines?"

                    await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))
                    context.clear_pending_clarification()
                    context.add_message(message.content, "user")
                    context.add_message("clarification_resolved_episodes", "bot")
                    return True
            else:
                # User response didn't match either option clearly
                await message.reply("Clarification incomplete. Please specify either 'By Playtime' (total hours invested) or 'By Episodes' (number of parts/videos) for accurate ranking analysis.")
                return True

        # SECOND: Check for "comprehensive list" follow-up (Issue #2 Fix)
        content_lower = message.content.lower()
        if any(
            phrase in content_lower for phrase in [
                "comprehensive list",
                "full list",
                "show all",
                "complete list",
                "show me all",
                "see all",
                "list all"]):

            if context.last_query_results and len(context.last_query_results) > 8:
                # User wants the full list
                games = context.last_query_results
                query_type = context.last_query_type or "query"
                query_param = context.last_query_parameter or "requested"

                # Format comprehensive list (with pagination for very long lists)
                if len(games) <= 20:
                    # Show all at once
                    game_list = []
                    for game in games:
                        episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                            "total_episodes", 0) > 0 else ""
                        status = game.get("completion_status", "unknown")
                        status_emoji = {
                            "completed": "✅",
                            "ongoing": "🔄",
                            "dropped": "❌",
                            "unknown": "❓"}.get(
                            status,
                            "❓")
                        game_list.append(f"{status_emoji} {game['canonical_name']}{episodes}")

                    response = f"Comprehensive {query_param} analysis - {len(games)} games total:\n\n" + "\n".join(
                        game_list)
                else:
                    # Paginate for very long lists
                    page_size = 20
                    game_list = []
                    for i, game in enumerate(games[:page_size]):
                        episodes = f" ({game.get('total_episodes', 0)} eps)" if game.get(
                            "total_episodes", 0) > 0 else ""
                        status = game.get("completion_status", "unknown")
                        status_emoji = {
                            "completed": "✅",
                            "ongoing": "🔄",
                            "dropped": "❌",
                            "unknown": "❓"}.get(
                            status,
                            "❓")
                        game_list.append(f"{status_emoji} {game['canonical_name']}{episodes}")

                    remaining = len(games) - page_size
                    response = f"Comprehensive {query_param} analysis - Displaying first {page_size} of {len(games)} total games:\n\n"
                    response += "\n".join(game_list)

                    if remaining > 0:
                        response += f"\n\n*{remaining} additional entries available. Request 'next page' for continuation.*"

                response = smart_truncate_response(response)
                await message.reply(apply_pops_arcade_sarcasm(response, message.author.id))
                context.add_message(message.content, "user")
                context.add_message("comprehensive_list_provided", "bot")
                return True

            elif context.last_query_results and len(context.last_query_results) <= 8:
                await message.reply("Analysis complete. The previous query already displayed all available results. No additional data to present.")
                context.add_message(message.content, "user")
                context.add_message("comprehensive_list_all_shown", "bot")
                return True
            else:
                await message.reply("Context analysis incomplete. No previous query results available for expansion. Please specify your query parameters first.")
                context.add_message(message.content, "user")
                context.add_message("comprehensive_list_no_context", "bot")
                return True

        # THIRD: Check if this is a disambiguation response
        if context.awaiting_disambiguation:
            is_disambiguation, matched_game = context.is_disambiguation_response(message.content)

            if is_disambiguation and matched_game:
                print(f"Context: Detected disambiguation response: '{message.content}' -> '{matched_game}'")

                # Clear disambiguation state
                disambiguation_type = context.disambiguation_type
                context.clear_disambiguation_state()

                # Process the resolved query based on the original disambiguation type
                if disambiguation_type == "game_status":
                    # Create a resolved game status query
                    resolved_query = f"has jonesy played {matched_game}"
                    print(f"Context: Processing resolved game status query: {resolved_query}")

                    match = re.search(r"has jonesy played (.+?)$", resolved_query)
                    if match:
                        await handle_game_status_query(message, match)
                        context.add_message(message.content, "user")
                        context.update_game_context(matched_game, "game_status")
                        context.add_message("disambiguation_resolved", "bot")
                        return True

                elif disambiguation_type == "game_details":
                    # Create a resolved game details query
                    resolved_query = f"how long did jonesy play {matched_game}"
                    print(f"Context: Processing resolved game details query: {resolved_query}")

                    match = re.search(r"how long did jonesy play (.+?)$", resolved_query)
                    if match:
                        await handle_game_details_query(message, match)
                        context.add_message(message.content, "user")
                        context.update_game_context(matched_game, "game_details")
                        context.add_message("disambiguation_resolved", "bot")
                        return True

                # If we get here, something went wrong with the disambiguation
                await message.reply(f"Database analysis: Game '{matched_game}' identified, however query type resolution failed. Please specify your analysis requirements.")
                context.add_message(message.content, "user")
                context.add_message("disambiguation_failed", "bot")
                return True
            elif context.awaiting_disambiguation:
                # User responded but it didn't match any available options
                available_games = ", ".join(f"'{game}'" for game in context.available_options[:5])
                if len(context.available_options) > 5:
                    available_games += f" and {len(context.available_options) - 5} more"

                await message.reply(f"Database analysis: Unable to match '{message.content}' with available options. Available games include: {available_games}. Please specify the exact game title for accurate data retrieval.")
                context.add_message(message.content, "user")
                context.add_message("disambiguation_no_match", "bot")
                return True

        # Check if this query needs context resolution
        if not should_use_context(message.content):
            # Still update context with any games mentioned in regular queries
            # This will be handled by the normal query processors
            return False

        # Detect if this is a follow-up question
        follow_up_intent = detect_follow_up_intent(message.content, context)

        if follow_up_intent:
            print(
                f"Context: Detected follow-up intent: {follow_up_intent['intent']}")

            # Handle duration follow-ups
            if follow_up_intent['intent'] == 'duration_followup':
                if context.last_mentioned_game:
                    # Create a new query with resolved context
                    resolved_query = f"how long did jonesy play {context.last_mentioned_game}"
                    print(
                        f"Context: Resolved duration query: {resolved_query}")

                    # Use existing game details handler
                    match = re.search(
                        r"how long did jonesy play (.+?)$", resolved_query)
                    if match:
                        await handle_game_details_query(message, match)
                        context.add_message(message.content, "user")
                        context.add_message(
                            "duration_followup_processed", "bot")
                        return True

            # Handle status follow-ups
            elif follow_up_intent['intent'] == 'status_followup':
                if context.last_mentioned_game:
                    # Create a resolved status query
                    resolved_query = f"has jonesy played {context.last_mentioned_game}"
                    print(f"Context: Resolved status query: {resolved_query}")

                    # Use existing game status handler
                    match = re.search(
                        r"has jonesy played (.+?)$", resolved_query)
                    if match:
                        await handle_game_status_query(message, match)
                        context.add_message(message.content, "user")
                        context.add_message("status_followup_processed", "bot")
                        return True

            # Handle episode follow-ups
            elif follow_up_intent['intent'] == 'episode_followup':
                if context.last_mentioned_game:
                    # Query for episode information
                    game_data = db.get_played_game(
                        context.last_mentioned_game)  # type: ignore
                    if game_data:
                        episodes = game_data.get('total_episodes', 0)
                        canonical_name = game_data['canonical_name']

                        if episodes > 0:
                            response = f"Database analysis: '{canonical_name}' comprises {episodes} episodes. "

                            # Add contextual follow-up
                            status = game_data.get(
                                'completion_status', 'unknown')
                            if status == 'completed':
                                response += f"This represents a complete viewing commitment. I could analyze her episode pacing patterns or compare this against other completed series if you require additional data."
                            elif status == 'ongoing':
                                response += f"Mission status: ongoing. I can track progress metrics or provide episode timeline analysis if you require mission updates."
                            else:
                                response += f"I can examine her engagement patterns or compare episode counts across similar titles if additional analysis is required."
                        else:
                            response = f"Database analysis: '{canonical_name}' episode data insufficient. Mission parameters require enhanced logging for accurate episode metrics."

                        await message.reply(response)
                        context.add_message(message.content, "user")
                        context.add_message(
                            "episode_followup_processed", "bot")
                        return True
                    else:
                        await message.reply(f"Database analysis: Unable to locate episode data for previously referenced game. Context resolution requires enhancement.")
                        return True

        # Try general context resolution
        resolved_content, context_info = resolve_context_references(
            message.content, context)

        # If we resolved something, try processing with the resolved content
        if context_info and resolved_content != message.content:
            print(
                f"Context: Resolved '{message.content}' -> '{resolved_content}'")
            print(f"Context info: {context_info}")

            # Route the resolved query through normal processing
            from ..message_handler import route_query
            from .details import (
                handle_game_details_query,
                handle_game_status_query,
                handle_genre_query,
                handle_recommendation_query,
                handle_year_query,
            )
            from .statistical import handle_statistical_query

            query_type, match = route_query(resolved_content)

            if query_type != "unknown" and match:
                # Process the resolved query
                context.add_message(message.content, "user")

                if query_type == "game_status":
                    await handle_game_status_query(message, match)
                    # Update context with the game mentioned
                    game_name = match.group(1).strip()
                    context.update_game_context(game_name, "game_status")
                elif query_type == "game_details":
                    await handle_game_details_query(message, match)
                    # Update context with the game mentioned
                    game_name = match.group(1).strip()
                    context.update_game_context(game_name, "game_details")
                elif query_type == "genre":
                    await handle_genre_query(message, match)
                    # Update context with series if relevant
                    series_name = match.group(1).strip()
                    context.update_series_context(series_name)
                elif query_type == "year":
                    await handle_year_query(message, match)
                elif query_type == "statistical":
                    await handle_statistical_query(message, resolved_content)
                elif query_type == "recommendation":
                    await handle_recommendation_query(message, match)

                context.add_message("context_resolved_response", "bot")
                return True
            else:
                # Context resolution didn't lead to a valid query, provide
                # helpful feedback
                if context_info.get('game_resolved'):
                    await message.reply(f"Sir Decent Jam, I resolved your reference to '{context_info['game_resolved']}', however insufficient information provided for specific analysis. Please clarify your query parameters for accurate data retrieval.")
                elif context_info.get('subject_resolved'):
                    await message.reply(f"Sir Decent Jam, accessing player data. I understand you're referencing Captain Jonesy, however insufficient information provided. Please specify the game title or analysis type for accurate data retrieval.")
                else:
                    await message.reply(f"Sir Decent Jam, context parameters detected but query resolution incomplete. Please provide additional specificity for accurate mission data analysis.")

                context.add_message(message.content, "user")
                context.add_message("context_resolution_failed", "bot")
                return True

        # If we detected ambiguous content but couldn't resolve it
        from ..context_manager import should_use_context
        if should_use_context(message.content):
            # Provide helpful error message indicating missing context
            await message.reply(f"Sir Decent Jam, accessing player data. insufficient information provided. Please specify the \"she\" and the game title for accurate playtime retrieval.")

            context.add_message(message.content, "user")
            context.add_message("insufficient_context", "bot")
            return True

        return False

    except Exception as e:
        print(f"Error in context-aware query processing: {e}")
        import traceback
        traceback.print_exc()
        return False
