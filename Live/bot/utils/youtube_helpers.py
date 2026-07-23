from typing import Any, Dict, Optional

async def attempt_youtube_api_analysis(
        game_name: Optional[str] = None, query_type: str = "general") -> Optional[Dict[str, Any]]:
    """Attempt to use YouTube API for real view count data with intelligent context awareness."""
    try:
        import os
        youtube_api_key = os.getenv('YOUTUBE_API_KEY')

        if not youtube_api_key:
            print("⚠️ YouTube API key not configured, falling back to database analysis")
            return None

        # Try to import and use YouTube integration
        try:
            from ..integrations.youtube import get_most_viewed_game_overall, get_youtube_analytics_for_game

            if game_name:
                # Get analytics for specific game
                print(f"🔄 Attempting YouTube API analysis for game: '{game_name}', query type: {query_type}")
                youtube_data = await get_youtube_analytics_for_game(game_name, query_type)

                if youtube_data and 'error' not in youtube_data:
                    print(f"✅ YouTube API analysis successful for '{game_name}'")
                    return youtube_data
                else:
                    print(f"⚠️ YouTube API returned no valid data for '{game_name}', falling back to database analysis")
                    return None
            else:
                # General query - use new overall analytics function
                print("🔄 General YouTube query requested, attempting overall YouTube analytics")
                youtube_data = await get_most_viewed_game_overall()

                if youtube_data and 'error' not in youtube_data:
                    print("✅ Overall YouTube API analysis successful")
                    return youtube_data
                else:
                    print("⚠️ Overall YouTube API failed, falling back to database analysis")
                    return None

        except ImportError as import_error:
            print(f"⚠️ YouTube integration import failed: {import_error}, falling back to database analysis")
            return None
        except Exception as api_error:
            print(f"⚠️ YouTube API error: {api_error}, falling back to database analysis")
            return None
    except Exception as e:
        print(f"⚠️ Unexpected error in YouTube analysis: {e}")
        return None
