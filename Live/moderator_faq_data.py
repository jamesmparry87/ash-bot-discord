"""
Moderator FAQ System Data Structure

This module contains structured FAQ data for the moderator help system,
extracted from the hardcoded if/elif chain in the main bot file.
"""

# FAQ Data Structure: Each entry contains patterns and response data
FAQ_DATA = {
    "strikes": {
        "patterns": ["explain strikes", "strike", "strike system"],
        "title": "📋 **Strike Management System Analysis**",
        "sections": [
            {
                "title": "Purpose",
                "content": "Automatic strike tracking with manual moderation controls. I monitor the violation channel and add strikes when users are mentioned.",
            },
            {
                "title": "Automatic Detection",
                "content": [
                    "• **Channel:** <#{VIOLATION_CHANNEL_ID}> (VIOLATION_CHANNEL_ID)",
                    "• When users are @mentioned in this channel, I automatically add strikes",
                    "• Captain Jonesy cannot receive strikes (protection protocol)",
                    "• I send notifications to mod alert channel for each strike added",
                ],
            },
            {
                "title": "Manual Commands",
                "content": [
                    "• `!strikes @user` — Query user's current strike count",
                    "• `!resetstrikes @user` — Reset user strikes to zero",
                    "• `!allstrikes` — Display comprehensive strike report",
                ],
            },
            {
                "title": "Database",
                "content": "PostgreSQL with persistence across restarts. Individual queries work as fallback if bulk operations fail.",
            },
            {
                "title": "Security",
                "content": "Only users with 'Manage Messages' permission can use manual strike commands.",
            },
        ],
    },
    "members": {
        "patterns": ["explain members", "member", "member system"],
        "title": "👥 **Member Interaction System Analysis**",
        "sections": [
            {
                "title": "Purpose",
                "content": "Special privileges for YouTube Members with conversation tracking and tier-based responses.",
            },
            {
                "title": "Member Role IDs",
                "content": [
                    "• YouTube Member: Space Cat (1018908116957548666)",
                    "• YouTiube Member (1018908116957548665)",
                    "• YouTube Member: Space Cat duplicate (1127604917146763424)",
                    "• Space Ocelot (879344337576685598)",
                ],
            },
            {
                "title": "Conversation System",
                "content": [
                    "• **Unlimited** conversations in Senior Officers' Area (<#{MEMBERS_CHANNEL_ID}>)",
                    "• **5 daily responses** in other channels, then encouraged to move to members area",
                    "• **Daily reset** at midnight (conversation counts reset automatically)",
                    "• Enhanced AI responses with more engagement than standard users",
                ],
            },
            {
                "title": "User Hierarchy",
                "content": "Captain Jonesy → Sir Decent Jam → Moderators → Members → Standard Users",
            },
            {
                "title": "Edge Cases",
                "content": "Users with both moderator permissions AND member roles are classified as 'moderator' tier (higher privilege takes precedence).",
            },
        ],
    },
    "database": {
        "patterns": ["explain database", "played games", "game database"],
        "title": "🎮 **Played Games Database System Analysis**",
        "sections": [
            {
                "title": "Purpose",
                "content": "Comprehensive gaming history with metadata, statistics, and AI-powered natural language queries.",
            },
            {
                "title": "Key Features",
                "content": [
                    "• **15+ metadata fields** per game (genre, series, platform, completion status, etc.)",
                    "• **Array support** for alternative names and Twitch VOD URLs",
                    "• **AI enhancement** for automatic genre/series detection",
                    "• **Statistical analysis** for gaming insights and rankings",
                ],
            },
            {
                "title": "Management Commands",
                "content": [
                    "• `!addplayedgame <name> | series:Series | year:2023 | status:completed | episodes:12`",
                    "• `!listplayedgames [series]` — List games, optionally filtered by series",
                    "• `!gameinfo <name_or_id>` — Detailed game information",
                    "• `!updateplayedgame <name_or_id> status:completed | episodes:15`",
                ],
            },
            {
                "title": "Import System",
                "content": [
                    "• `!bulkimportplayedgames` — YouTube playlists + Twitch VODs with real playtime",
                    "• `!updateplayedgames` — AI metadata enhancement for existing games",
                    "• `!cleanplayedgames` — Remove already-played games from recommendations",
                ],
            },
            {
                "title": "Natural Language Queries",
                "content": "Users can ask 'Has Jonesy played [game]?' and get intelligent responses with follow-up suggestions.",
            },
        ],
    },
    "commands": {
        "patterns": ["explain commands", "command", "bot commands"],
        "title": "⚙️ **Bot Command System Analysis**",
        "sections": [
            {
                "title": "Architecture",
                "content": "Event-driven command processing with permission-based access control.",
            },
            {
                "title": "User Commands (Everyone)",
                "content": [
                    "• `!addgame <name> - <reason>` / `!recommend <name> - <reason>` — Add game recommendation",
                    "• `!listgames` — View all game recommendations",
                ],
            },
            {
                "title": "Moderator Commands (Manage Messages required)",
                "content": [
                    "• **Strike Management:** `!strikes`, `!resetstrikes`, `!allstrikes`",
                    "• **Game Management:** `!removegame`, `!addplayedgame`, `!updateplayedgame`",
                    "• **Database Operations:** `!bulkimportplayedgames`, `!cleanplayedgames`",
                    "• **AI Configuration:** `!setpersona`, `!toggleai`, `!ashstatus`",
                ],
            },
            {
                "title": "Natural Language Processing",
                "content": [
                    "• Statistical queries: 'What game series has the most playtime?'",
                    "• Game lookups: 'Has Jonesy played God of War?'",
                    "• Genre queries: 'What horror games has Jonesy played?'",
                ],
            },
            {
                "title": "Permission System",
                "content": "Commands check user roles and guild permissions before execution. Captain Jonesy and Sir Decent Jam have elevated access.",
            },
        ],
    },
    "ai": {
        "patterns": ["explain ai", "artificial intelligence", "ai system"],
        "title": "🧠 **AI Integration System Analysis**",
        "sections": [
            {
                "title": "Dual AI Architecture",
                "content": [
                    "• **Primary:** Google Gemini 1.5 Flash (fast, efficient)",
                    "• **Backup:** Claude 3 Haiku (fallback if Gemini fails)",
                    "• **Automatic failover** with quota monitoring",
                ],
            },
            {
                "title": "Personality System",
                "content": [
                    "• **Character:** Science Officer Ash from Alien (1979)",
                    "• **Configurable:** `!setpersona` to modify personality",
                    "• **Response filtering** to prevent repetitive character phrases",
                    "• **Tier-aware** responses based on user authority level",
                ],
            },
            {
                "title": "AI Features",
                "content": [
                    "• **Game metadata enhancement** (genre, series, release year detection)",
                    "• **Natural language query processing** for gaming statistics",
                    "• **Conversation management** with context awareness",
                    "• **Error handling** with graceful fallbacks to static responses",
                ],
            },
            {
                "title": "Configuration",
                "content": [
                    "• Current Status: {ai_status_message}",
                    "• Toggle with `!toggleai` command",
                    "• Rate limiting prevents quota exhaustion",
                ],
            },
        ],
    },
    "tiers": {
        "patterns": ["explain tiers", "user tier", "user system"],
        "title": "👑 **User Tier System Analysis**",
        "sections": [
            {"title": "Hierarchy (Highest to Lowest)", "content": ""},
            {
                "title": "1. Captain Jonesy (ID: {JONESY_USER_ID})",
                "content": [
                    "• Addressed as 'Captain' with military courtesy",
                    "• Cannot receive strikes (protection protocol)",
                    "• Unlimited conversation access everywhere",
                ],
            },
            {
                "title": "2. Sir Decent Jam (ID: {JAM_USER_ID})",
                "content": [
                    "• Acknowledged as bot creator with special respect",
                    "• Full command access, development privileges",
                ],
            },
            {
                "title": "3. Moderators (Manage Messages Permission)",
                "content": [
                    "• Professional courtesy and authority recognition",
                    "• Full moderator command suite, unlimited conversations",
                    "• Access to detailed FAQ system (this system)",
                ],
            },
            {
                "title": "4. Members (YouTube Member Roles)",
                "content": [
                    "• Enhanced conversations, more engaging responses",
                    "• Unlimited in Senior Officers' Area (<#{MEMBERS_CHANNEL_ID}>)",
                    "• 5 daily responses in other channels",
                ],
            },
            {
                "title": "5. Standard Users",
                "content": [
                    "• Basic bot interactions, public commands",
                    "• Can ask natural language questions about games",
                ],
            },
            {
                "title": "Detection Logic",
                "content": "`get_user_communication_tier()` checks in hierarchy order. Higher tiers take precedence over lower ones.",
            },
        ],
    },
    "import": {
        "patterns": ["explain import", "import system", "bulk import"],
        "title": "📥 **Game Import System Analysis**",
        "sections": [
            {
                "title": "Purpose",
                "content": "Automated import of gaming history from YouTube and Twitch with comprehensive metadata.",
            },
            {
                "title": "Import Sources",
                "content": [
                    "• **YouTube:** Playlist-based detection with accurate video duration calculation",
                    "• **Twitch:** VOD analysis with duration tracking and series grouping",
                    "• **AI Enhancement:** Automatic genre, series, and release year detection",
                ],
            },
            {
                "title": "Commands",
                "content": [
                    "• `!bulkimportplayedgames` — Full import from APIs with AI metadata",
                    "• `!updateplayedgames` — AI enhancement for existing games",
                    "• `!cleanplayedgames` — Remove already-played games from recommendations",
                ],
            },
            {
                "title": "Data Processing",
                "content": [
                    "• **Smart Deduplication:** Merges YouTube + Twitch data for same games",
                    "• **Completion Detection:** Automatically identifies completed vs ongoing series",
                    "• **Alternative Names:** Generates searchable aliases (RE2, GoW 2018, etc.)",
                    "• **Real Playtime:** Calculates actual time from video durations, not estimates",
                ],
            },
            {
                "title": "API Requirements",
                "content": "YouTube Data API key, Twitch Client ID/Secret (optional but recommended).",
            },
        ],
    },
    "statistics": {
        "patterns": ["explain statistics", "stats", "analytics"],
        "title": "📊 **Statistical Analysis System**",
        "sections": [
            {
                "title": "Purpose",
                "content": "Advanced gaming analytics with natural language query processing and intelligent follow-up suggestions.",
            },
            {
                "title": "Query Types",
                "content": [
                    "• **Playtime Analysis:** 'What game series has the most playtime?'",
                    "• **Episode Rankings:** 'Which game has the most episodes?'",
                    "• **Completion Metrics:** 'What game took longest to complete?'",
                    "• **Efficiency Analysis:** 'What game has highest average playtime per episode?'",
                ],
            },
            {
                "title": "Database Functions",
                "content": [
                    "• `get_series_by_total_playtime()` — Series playtime rankings",
                    "• `get_longest_completion_games()` — Completion time analysis",
                    "• `get_games_by_episode_count()` — Episode count statistics",
                    "• `get_games_by_average_episode_length()` — Efficiency metrics",
                ],
            },
            {
                "title": "Enhanced Responses",
                "content": [
                    "• **Contextual Follow-ups:** Suggests related queries based on results",
                    "• **Comparative Analysis:** Shows rankings and differences between games",
                    "• **Series Insights:** Analyzes franchise-level gaming patterns",
                ],
            },
            {
                "title": "Processing",
                "content": "Pattern matching identifies query type, routes to appropriate database function, generates response with Ash personality.",
            },
        ],
    },
    "scheduled": {
        "patterns": ["explain scheduled", "automatic update", "schedule"],
        "title": "⏰ **Scheduled Update System Analysis**",
        "sections": [
            {"title": "Schedule", "content": "Every Sunday at 12:00 PM (midday) UTC"},
            {"title": "Purpose", "content": "Automatically update ongoing games with fresh metadata from YouTube API."},
            {
                "title": "Update Process",
                "content": [
                    "• **Target Games:** Only games with 'ongoing' completion status",
                    "• **Data Sources:** YouTube playlists for episode count and playtime",
                    "• **Change Detection:** Only updates games where data has actually changed",
                    "• **Preservation:** Maintains manually edited information",
                ],
            },
            {
                "title": "Update Logic",
                "content": [
                    "1. Query database for ongoing games with YouTube playlist URLs",
                    "2. Fetch current playlist metadata via YouTube API",
                    "3. Compare episode counts - update only if changed",
                    "4. Recalculate playtime from actual video durations",
                    "5. Update database records with new metadata",
                ],
            },
            {"title": "Notifications", "content": "Status reports sent to <#{MOD_ALERT_CHANNEL_ID}>"},
            {
                "title": "Implementation",
                "content": "`@tasks.loop(time=time(12, 0))` decorator with `scheduled_games_update()` function. Includes error handling and rate limiting.",
            },
        ],
    },
    "recommendations": {
        "patterns": ["explain recommendations", "game rec", "rec system"],
        "title": "🎯 **Game Recommendations System Analysis**",
        "sections": [
            {"title": "Purpose", "content": "Community-driven game suggestion system with persistent list management."},
            {
                "title": "User Commands",
                "content": [
                    "• `!addgame <name> - <reason>` / `!recommend <name> - <reason>`",
                    "• `!listgames` — View all recommendations with contributor info",
                ],
            },
            {
                "title": "Moderator Commands",
                "content": [
                    "• `!removegame <name_or_index>` — Remove recommendation by name or index",
                    "• `!cleanplayedgames` — Remove already-played games from recommendations",
                ],
            },
            {
                "title": "Database Features",
                "content": [
                    "• **Duplicate Detection:** Fuzzy matching prevents duplicate entries",
                    "• **Contributor Tracking:** Records who suggested each game",
                    "• **Persistent Storage:** PostgreSQL with automatic indexing",
                ],
            },
            {
                "title": "Smart Features",
                "content": [
                    "• **Auto-Update Channel:** Persistent list in recommendations channel",
                    "• **Typo Tolerance:** Fuzzy matching for game name recognition",
                    "• **Batch Processing:** Can add multiple games in one command",
                    "• **API Integration:** Cross-reference with played games to avoid duplicates",
                ],
            },
            {
                "title": "Special Handling",
                "content": "Sir Decent Jam's contributions don't show contributor names (configured via user ID check).",
            },
        ],
    },
}
