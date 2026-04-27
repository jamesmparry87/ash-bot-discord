"""
Database-Driven Trivia Question Templates

These templates guarantee correct answers by mapping directly to database queries.
Templates are organized by category for easy maintenance and expansion.
"""

DATABASE_QUESTION_TEMPLATES = {
    'series_battles': [
        {
            'question': "Which series has more total playtime: God of War or Resident Evil?",
            'query_type': 'series_playtime_comparison',
            'parameter': 'God of War vs Resident Evil',
            'category': 'series_comparison'
        },
        {
            'question': "Which series has more episodes: Uncharted or Tomb Raider?",
            'query_type': 'series_episode_comparison',
            'parameter': 'Uncharted vs Tomb Raider',
            'category': 'series_comparison'
        },
        {
            'question': "Which series has Jonesy completed more games from: God of War or The Last of Us?",
            'query_type': 'series_completion_comparison',
            'parameter': 'God of War vs The Last of Us',
            'category': 'series_comparison'
        },
        {
            'question': "Which series has more total YouTube views: Resident Evil or Silent Hill?",
            'query_type': 'series_views_comparison',
            'parameter': 'Resident Evil vs Silent Hill',
            'category': 'series_comparison'
        },
    ],
    'genre_insights': [
        {
            'question': "What genre has Jonesy played the most games from?",
            'query_type': 'most_played_genre',
            'parameter': None,
            'category': 'genre_insight'
        },
        {
            'question': "Which genre has the most total playtime on the channel?",
            'query_type': 'longest_genre_playtime',
            'parameter': None,
            'category': 'genre_insight'
        },
        {
            'question': "Which genre gets the most YouTube views?",
            'query_type': 'most_popular_genre_by_views',
            'parameter': None,
            'category': 'genre_insight'
        },
        {
            'question': "What genre does Jonesy finish games most often?",
            'query_type': 'genre_with_most_completed_games',
            'parameter': None,
            'category': 'genre_insight'
        },
    ],
    'memorable_milestones': [
        {
            'question': "What's the longest game Jonesy has completed (by playtime)?",
            'query_type': 'longest_completed_game',
            'parameter': None,
            'category': 'completion_milestone'
        },
        {
            'question': "What's Jonesy's quickest completed playthrough?",
            'query_type': 'shortest_completed_game',
            'parameter': None,
            'category': 'completion_milestone'
        },
        {
            'question': "What was the very first game played on the channel?",
            'query_type': 'first_game_ever_played',
            'parameter': None,
            'category': 'channel_history'
        },
        {
            'question': "What's the most recent game Jonesy has completed?",
            'query_type': 'most_recent_completed_game',
            'parameter': None,
            'category': 'completion_milestone'
        },
        {
            'question': "What's the oldest game (by release year) that Jonesy has completed?",
            'query_type': 'oldest_completed_game_by_release',
            'parameter': None,
            'category': 'retro_gaming'
        },
        {
            'question': "What's the newest game (by release year) that Jonesy has completed?",
            'query_type': 'newest_completed_game_by_release',
            'parameter': None,
            'category': 'modern_gaming'
        },
    ],
    'series_knowledge': [
        {
            'question': "Which series has Jonesy played the most games from?",
            'query_type': 'series_with_most_games',
            'parameter': None,
            'category': 'series_stats'
        },
        {
            'question': "Which series has Jonesy completed the most games from?",
            'query_type': 'series_with_most_completed_games',
            'parameter': None,
            'category': 'series_completion'
        },
        {
            'question': "Which series has the most incomplete/abandoned games?",
            'query_type': 'most_incomplete_series',
            'parameter': None,
            'category': 'series_completion'
        },
        {
            'question': "Which series has the longest average game length?",
            'query_type': 'longest_average_series_length',
            'parameter': None,
            'category': 'series_stats'
        },
    ],
    'advanced_patterns': [
        {
            'question': "Which game has the best engagement rate (views per episode)?",
            'query_type': 'best_views_per_episode',
            'parameter': None,
            'category': 'engagement_metrics'
        },
        {
            'question': "How many games are YouTube-exclusive on the channel?",
            'query_type': 'youtube_only_count',
            'parameter': None,
            'category': 'platform_analytics'
        },
        {
            'question': "How many games are Twitch-exclusive on the channel?",
            'query_type': 'twitch_only_count',
            'parameter': None,
            'category': 'platform_analytics'
        },
        {
            'question': "Which series appears on both YouTube and Twitch?",
            'query_type': 'most_cross_platform_series',
            'parameter': None,
            'category': 'platform_analytics'
        },
        {
            'question': "How many games has Jonesy completed in total?",
            'query_type': 'total_completed_count',
            'parameter': None,
            'category': 'completion_stats'
        },
        {
            'question': "What percentage of games does Jonesy complete?",
            'query_type': 'completion_rate_percentage',
            'parameter': None,
            'category': 'completion_stats'
        },
    ]
}
