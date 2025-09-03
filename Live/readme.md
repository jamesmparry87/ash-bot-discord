# Ash Discord Bot - Gaming Database & Moderation System

A Discord moderation and AI assistant bot featuring strike tracking, game recommendations, comprehensive played games database, and personality-driven interactions with intelligent game series disambiguation.

## Quick Reference

### User Commands (Everyone)

- `!addgame <name> - <reason>` - Add game recommendation
- `!recommend <name> - <reason>` - Add game recommendation (alias)
- `!listgames` - List all game recommendations

#### Natural Language Queries (Ask Ash)

**Game Lookup Queries:**

- `@Ashbot Has Jonesy played [game name]?` - Query played games database with smart follow-up suggestions
- `@Ashbot What games has Jonesy played?` - Get examples from played games database

**Genre & Series Queries:**

- `@Ashbot What horror games has Jonesy played?` - Query by genre with completion status
- `@Ashbot What Final Fantasy games has Jonesy played?` - Query by franchise/series with progress details

**Statistical Analysis Queries (NEW):**

- `@Ashbot What game series has Jonesy played for the most minutes?` - Series playtime rankings
- `@Ashbot What game has the highest average playtime per episode?` - Episode efficiency analysis
- `@Ashbot Which game has the most episodes?` - Episode count rankings
- `@Ashbot What game took the longest to complete?` - Completion time analysis
- `@Ashbot What game series has the most playtime?` - Series time investment analysis

**Enhanced Conversational Features:**

- Smart follow-up suggestions based on game properties
- Series-based recommendations for franchise games
- Episode count insights for marathon gaming sessions
- Progress tracking suggestions for ongoing games
- Completion efficiency analysis for finished games

### Moderator Commands (Requires "Manage Messages" permission)

#### Strike Management

- `!strikes @user` - Check user's strikes
- `!resetstrikes @user` - Reset user's strikes
- `!allstrikes` - List all users with strikes

#### Game Recommendations Management

- `!removegame <name/index>` - Remove game recommendation
- `!listgames` - View all recommendations with index numbers

#### Played Games Database Management

- `!addplayedgame <Game Name> | series:Series | year:2023 | platform:PC | status:completed | episodes:12 | notes:Additional info` - Add played game with metadata
- `!listplayedgames [series_name]` - List all played games, optionally filtered by series
- `!searchplayedgames <query>` - Search played games by name, series, or notes
- `!gameinfo <game_name_or_id>` - Get detailed information about a specific played game (accepts game name or database ID)
- `!updateplayedgame <game_name_or_id> status:completed | episodes:15 | notes:New info` - Update individual game details (accepts game name or database ID)
- `!removeplayedgame <game_name>` - Remove a played game (with confirmation)
- `!fixcanonicalname <current_name> <new_canonical_name>` - Fix game name formatting
- `!addaltname <game_name> <alternative_name>` - Add alternative name for better search
- `!removealtname <game_name> <alternative_name>` - Remove alternative name
- `!setaltnames <game_name> <name1, name2, name3>` - Set all alternative names for a game (comma-separated)

#### Game Import System

- `!bulkimportplayedgames` - Import games from YouTube playlists and Twitch VODs with accurate playtime data
- `!updateplayedgames` - Update existing played games with AI-enhanced metadata (genre, alternative names, series info, release years)
- `!cleanplayedgames` - Remove already-played games from recommendations using API analysis

#### Bot Status & Analytics

- `!ashstatus` - View bot status and statistics
- `!dbstats` - Show database statistics and top contributors

#### AI Configuration

- `!setpersona <text>` - Change bot personality
- `!getpersona` - View current personality
- `!toggleai` - Enable/disable AI conversations

---

## Features

### Automatic Scheduled Updates

The bot automatically updates ongoing games every **Sunday at 12:00 PM (midday)**:

- Updates episode counts and playtime from YouTube playlists
- Only updates games where data has changed
- Sends status notifications to mod channel
- Preserves manually edited information

### Intelligent Game Queries & Statistical Analysis

Users can ask Ash about games using natural language with smart series disambiguation and advanced analytics:

**Game Lookup Examples:**

- `@Ashbot Has Jonesy played God of War?` → Bot asks for clarification between different entries
- `@Ashbot Has Jonesy played God of War 2018?` → Specific answer with episode count, completion status, and contextual follow-up suggestions
- `@Ashbot What Final Fantasy games has Jonesy played?` → Lists all FF games with progress details and series insights
- `@Ashbot What horror games has Jonesy played?` → Genre-based query with completion status and genre statistics

**Statistical Analysis Examples (NEW):**

- `@Ashbot What game series has Jonesy played for the most minutes?` → "Database analysis complete. The series with maximum temporal investment: 'Batman: Arkham' with 45.2 hours across 3 games. Fascinating - this significantly exceeds the second-ranked 'Mass Effect' series at 32.1 hours. I could analyze her complete franchise chronology or compare series completion patterns if you require additional data."
- `@Ashbot What game has the highest average playtime per episode?` → "Statistical analysis indicates 'Persona 5' demonstrates highest temporal density per episode: 67.3 minutes average across 45 episodes. Intriguing patterns emerge when comparing this to her other extended gaming sessions."
- `@Ashbot Which game has the most episodes?` → "Database confirms 'Dark Souls III' holds maximum episode count: 52 episodes, status: completed. Remarkable commitment detected - this represents her most extensive completed gaming engagement."

**Enhanced Conversational Follow-ups:**

- **Series Analysis**: "I could analyze her complete [Series] chronology or compare series completion patterns..."
- **Episode Insights**: "This ranks #2 in her episode count metrics. I could analyze her other marathon gaming sessions..."
- **Completion Tracking**: "Mission status: ongoing. I can track her progress against typical completion metrics..."
- **Efficiency Analysis**: "Efficient completion detected - this falls within optimal episode range for focused gaming sessions..."

### Gameplay History Import System

- **YouTube Playlists**: Each playlist treated as one game series for accurate data
- **Accurate Playtime**: Calculates real playtime from video durations using YouTube API
- **AI-Enhanced Metadata**: Automatically categorizes games by genre, series, release year, and platform
- **Smart Deduplication**: Combines YouTube and Twitch data without creating duplicates
- **Completion Status Detection**: Automatically detects completed vs ongoing series

### Database Management

- **Comprehensive Game Data**: Stores episode counts, playtime, completion status, platform info
- **Alternative Names**: Support for multiple names per game (RE2, GoW 2018, etc.)
- **Series Grouping**: Intelligent handling of game franchises and series
- **Search Capabilities**: Full-text search across names, series, and notes

---

## Technical File Overview

### Project Structure

```text
Live/
├── ash_bot_fallback.py    # Main bot file
├── database.py            # Database operations
├── data_migration.py      # Data migration utilities
├── main.py               # Alternative entry point
├── testai.py             # AI testing utilities
├── requirements.txt       # Python dependencies
├── Procfile              # Railway deployment config
├── railway.toml          # Railway build settings
├── runtime.txt           # Python version specification
├── start.sh              # Startup script
├── bot.lock              # Single instance lock file
├── .env.example          # Environment variables template
└── README.md             # This file

# Root directory files
../
├── ash_bot_final.py       # Legacy bot version
├── ash_bot.py            # Original bot version
├── readme.md             # Root readme
├── .gitignore            # Git ignore rules
└── .gitattributes        # Git attributes
```

### Core Bot Files

#### `ash_bot_fallback.py` (Main Bot)

**Primary bot implementation with comprehensive features:**

- **Discord Event Handling**: Message processing, command routing, automatic strike detection
- **AI Integration**: Dual AI system (Google Gemini + Claude Anthropic) with fallback mechanisms
- **Statistical Query Engine**: Advanced pattern matching for gaming analytics queries
- **Conversational Follow-ups**: Context-aware suggestions based on game properties
- **Game Database Integration**: Natural language queries with series disambiguation
- **Scheduled Tasks**: Automatic Sunday updates for ongoing games metadata
- **Command System**: 40+ commands for moderation, game management, and analytics
- **Error Handling**: Comprehensive error recovery and user feedback
- **Personality System**: Ash character implementation with configurable responses
- **Captain Jonesy Integration**: Recognizes server owner (ID: 51329927895056384) for special permissions

**Key Features:**

- Cross-platform locking system for single instance deployment
- Rate limiting and quota management for external APIs
- Intelligent game series recognition and disambiguation
- Real-time strike tracking with automatic channel monitoring
- AI response filtering to prevent repetitive character phrases

#### `database.py` (Database Layer)

**Comprehensive PostgreSQL database management:**

- **Connection Management**: Robust connection handling with retry logic and error recovery
- **Schema Management**: Automatic table creation and migration handling
- **Strike System**: User strike tracking with bulk operations and individual queries
- **Game Recommendations**: Community suggestion system with fuzzy matching and duplicate detection
- **Played Games Database**: Advanced gaming history with metadata, alternative names, and series grouping
- **Statistical Analytics**: 15+ analytical functions for gaming insights and rankings
- **Data Import/Export**: Bulk operations for migration and API data integration
- **Search Capabilities**: Full-text search across multiple fields with ranking algorithms

**Database Tables:**

- `strikes`: User moderation tracking
- `game_recommendations`: Community game suggestions
- `played_games`: Comprehensive gaming history with 15+ metadata fields
- `bot_config`: Persistent bot configuration storage

**Advanced Features:**

- Array field handling for alternative names and VOD URLs
- Fuzzy matching algorithms for game name recognition
- Deduplication logic for merging duplicate game records
- Temporal data analysis for gaming patterns and trends

### Utility and Configuration Files

#### `data_migration.py` (Migration Tools)

**Data migration and parsing utilities:**

- **Game List Parser**: Converts text-based game lists to structured database format
- **Sample Data**: Predefined game collections for testing and initial population
- **Format Conversion**: Handles various input formats (comma-separated, bulleted lists, etc.)
- **Validation Logic**: Ensures data integrity during migration processes

#### `main.py` (Alternative Entry Point)

**Secondary bot entry point:**

- Alternative startup configuration
- Development testing environment
- Backup execution path
- Simplified deployment option

#### `testai.py` (AI Testing)

**AI system testing and validation:**

- **Model Testing**: Validates AI API connections and response quality
- **Token Usage Monitoring**: Tracks API usage and costs
- **Response Analysis**: Tests AI response filtering and character consistency
- **Fallback Testing**: Validates backup AI system functionality

#### `requirements.txt` (Dependencies)

**Python package specifications:**

```text
discord.py>=2.3.0          # Discord API integration
psycopg2-binary>=2.9.0     # PostgreSQL database driver
google-generativeai>=0.3.0 # Google Gemini AI integration
anthropic>=0.7.0           # Claude AI integration
aiohttp>=3.8.0             # Async HTTP client for API calls
```

#### `Procfile` (Railway Deployment)

**Process definition for Railway.app:**

```text
web: python ash_bot_fallback.py
```

Defines the main process for cloud deployment with automatic restart capabilities.

#### `railway.toml` (Build Configuration)

**Railway-specific build settings:**

- Python version specification
- Build command configuration
- Environment variable handling
- Deployment optimization settings

#### `runtime.txt` (Python Version)

**Python version specification for deployment:**

```text
python-3.11.0
```

Ensures consistent Python version across development and production environments.

#### `start.sh` (Startup Script)

**Shell script for bot initialization:**

- Environment validation
- Database connection testing
- Graceful startup with error handling
- Process monitoring setup

### Configuration and Environment Files

#### `.env.example` (Environment Template)

**Template for required environment variables:**

```text
# Required
DISCORD_TOKEN=your_discord_bot_token_here
GOOGLE_API_KEY=your_google_ai_api_key_here
DATABASE_URL=postgresql://user:pass@host:port/db

# Optional
ANTHROPIC_API_KEY=your_claude_api_key_here
YOUTUBE_API_KEY=your_youtube_api_key_here
TWITCH_CLIENT_ID=your_twitch_client_id_here
TWITCH_CLIENT_SECRET=your_twitch_client_secret_here
```

#### `bot.lock` (Instance Lock)

**Single instance enforcement:**

- Prevents multiple bot instances
- Cross-platform compatibility
- Automatic cleanup on shutdown
- Process ID tracking

### Legacy and Archive Files

#### `ash_bot_final.py` (Legacy Version)

**Previous stable bot version:**

- Maintained for rollback capabilities
- Contains earlier implementation patterns
- Reference for feature migration
- Backup for critical deployments

#### `ash_bot.py` (Original Version)

**Initial bot implementation:**

- Basic command structure
- Simple database operations
- Original personality implementation
- Historical reference for development progression

### Root Directory Files

#### `readme.md` (Root Documentation)

**Project overview and quick start guide:**

- High-level project description
- Basic setup instructions
- Link to detailed documentation
- Contribution guidelines

#### `.gitignore` (Git Exclusions)

**Version control exclusions:**

- Environment files (.env)
- Python cache files (_pycache_)
- Database files (*.db)
- Log files (*.log)
- IDE configuration files

#### `.gitattributes` (Git Attributes)

**Git handling specifications:**

- Line ending normalization
- Binary file identification
- Merge strategy definitions
- Language detection overrides

## Architecture Overview

### System Architecture

```text
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Discord API   │◄──►│  ash_bot_fallback │◄──►│   PostgreSQL    │
└─────────────────┘    │      .py         │    │   Database      │
                       └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │   database.py    │
                       └──────────────────┘
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
            ┌──────────┐ ┌──────────┐ ┌──────────┐
            │Google AI │ │YouTube   │ │Twitch    │
            │(Gemini)  │ │Data API  │ │Helix API │
            └──────────┘ └──────────┘ └──────────┘
```

### Data Flow

1. **User Input** → Discord message processing
2. **Command Routing** → Appropriate handler function
3. **Database Query** → PostgreSQL via database.py
4. **AI Enhancement** → Google Gemini or Claude (if needed)
5. **Response Generation** → Formatted Discord message
6. **Logging & Analytics** → Database updates and monitoring

### Key Design Patterns

- **Singleton Pattern**: Single bot instance enforcement
- **Factory Pattern**: AI client creation and management
- **Observer Pattern**: Discord event handling
- **Repository Pattern**: Database abstraction layer
- **Strategy Pattern**: Multiple AI provider support
- **Command Pattern**: Discord command system

---

## Setup & Deployment

### Railway.app Deployment

#### Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **Discord Bot Token**: Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
3. **Google AI API Key**: Get your key from [Google AI Studio](https://makersuite.google.com/app/apikey)
4. **YouTube Data API Key**: Get from [Google Cloud Console](https://console.cloud.google.com/) (optional but recommended)
5. **Twitch API Credentials**: Get from [Twitch Developers](https://dev.twitch.tv/) (optional)

#### Deployment Steps

1. **Connect Repository**

   - Fork or clone this repository to your GitHub account
   - Connect your GitHub repository to Railway

2. **Add PostgreSQL Database**

   - In your Railway project, click "New Service"
   - Select "Database" → "PostgreSQL"
   - Railway will automatically provide a `DATABASE_URL` environment variable

3. **Configure Environment Variables**

   Set these environment variables in Railway:

   ```text
   # Required
   DISCORD_TOKEN=your_discord_bot_token_here
   GOOGLE_API_KEY=your_google_ai_api_key_here
   DATABASE_URL=automatically_provided_by_railway
   
   # Optional (for enhanced features)
   YOUTUBE_API_KEY=your_youtube_api_key_here
   TWITCH_CLIENT_ID=your_twitch_client_id_here
   TWITCH_CLIENT_SECRET=your_twitch_client_secret_here
   ```

4. **Deploy**

   - Railway will automatically detect the Python project
   - It will install dependencies from `requirements.txt`
   - The bot will start using the `Procfile` configuration
   - Scheduled tasks will automatically begin running

### Database Schema

The bot automatically creates these tables on first run:

- **strikes**: User strike tracking
- **game_recommendations**: Community game suggestions
- **played_games**: Comprehensive played games database
- **bot_config**: Bot configuration storage

#### Played Games Table Fields

- `canonical_name`: Official game name for database searches
- `alternative_names`: Array of alternative names (RE2, GoW 2018, etc.)
- `series_name`: Game series (God of War, Final Fantasy, etc.)
- `genre`: Game genre for filtering (auto-detected by AI)
- `release_year`: Release year for chronological sorting (auto-detected by AI)
- `platform`: Gaming platform (PC, PlayStation 4, etc.) (auto-detected by AI)
- `completion_status`: completed, ongoing, dropped, unknown
- `total_episodes`: Number of episodes/videos recorded (auto-updated)
- `total_playtime_minutes`: Total playtime in minutes (calculated from real video durations)
- `youtube_playlist_url`: Link to YouTube playlist
- `twitch_vod_urls`: Array of Twitch VOD URLs
- `notes`: Additional notes and context
- `first_played_date`: Date of first episode (auto-detected)
- `created_at`: Record creation timestamp
- `updated_at`: Last modification timestamp (auto-updated by scheduled tasks)

### Configuration

#### Discord Server Setup

Update these IDs in `ash_bot_fallback.py`:

- `GUILD_ID`: Your Discord server ID
- `VIOLATION_CHANNEL_ID`: Channel for automatic strike detection
- `MOD_ALERT_CHANNEL_ID`: Channel for moderation alerts and scheduled update notifications
- `TWITCH_HISTORY_CHANNEL_ID`: Channel for Twitch history data
- `YOUTUBE_HISTORY_CHANNEL_ID`: Channel for YouTube history data
- `CAPTAIN_JONESY_ID`: Server owner user ID (51329927895056384)

#### Bot Permissions

Required Discord permissions:

- Read Messages
- Send Messages
- Read Message History
- Use Slash Commands
- Manage Messages (for moderator features)

---

**Ready to deploy?** Push your code to GitHub, connect to Railway, add your environment variables, and your bot will be live with automatic scheduled updates and comprehensive game management capabilities.

TEST
