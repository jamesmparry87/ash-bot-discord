# Ash Discord Bot - Enhanced Gaming Database System

A sophisticated Discord moderation and AI assistant bot featuring strike tracking, game recommendations, comprehensive played games database with automatic updates, and personality-driven interactions with intelligent game series disambiguation.

## Quick Reference for Daily Use

### User Commands (Everyone)

- `!addgame <name> - <reason>` - Add game recommendation
- `!recommend <name> - <reason>` - Add game recommendation (alias)
- `!listgames` - List all game recommendations
- Ask Ash: `@Ashbot Has Jonesy played [game name]?` - Query played games database with series disambiguation
- Ask Ash: `@Ashbot What games has Jonesy played?` - Get diverse examples from played games database
- Ask Ash: `@Ashbot What horror games has Jonesy played?` - Query by genre
- Ask Ash: `@Ashbot What Final Fantasy games has Jonesy played?` - Query by franchise/series

### Moderator Commands (Requires "Manage Messages" permission)

#### Strike Management

- `!strikes @user` - Check user's strikes
- `!resetstrikes @user` - Reset user's strikes
- `!allstrikes` - List all users with strikes

#### Game Recommendations Management

- `!removegame <name/index>` - Remove game recommendation
- `!listgames` - View all recommendations with index numbers

#### Enhanced Played Games Database Management

- `!addplayedgame <Game Name> | series:Series | year:2023 | platform:PC | status:completed | episodes:12 | notes:Additional info` - Add played game with metadata
- `!listplayedgames [series_name]` - List all played games, optionally filtered by series
- `!searchplayedgames <query>` - Search played games by name, series, or notes
- `!gameinfo <game_name>` - Get detailed information about a specific played game
- `!updateplayedgame <game_name> status:completed | episodes:15 | notes:New info` - Update game details
- `!removeplayedgame <game_name>` - Remove a played game (with confirmation)
- `!fixcanonicalname <current_name> <new_canonical_name>` - Fix game name formatting
- `!addaltname <game_name> <alternative_name>` - Add alternative name for better search
- `!removealtname <game_name> <alternative_name>` - Remove alternative name

#### Comprehensive Game Import System

- `!bulkimportplayedgames` - Import games from YouTube playlists and Twitch VODs with accurate playtime data
- `!cleanplayedgames` - Remove already-played games from recommendations using API analysis

#### Bot Status & Analytics

- `!ashstatus` - View bot status and statistics
- `!dbstats` - Show database statistics and top contributors

#### AI Configuration

- `!setpersona <text>` - Change bot personality
- `!getpersona` - View current personality
- `!toggleai` - Enable/disable AI conversations

---

## 🚀 New Features & Enhancements

### Automatic Scheduled Updates

The bot now automatically updates ongoing games every **Sunday at 12:00 PM (midday)**:

- **Smart Detection**: Only updates games where episode count has changed
- **Accurate Playtime**: Fetches real video durations from YouTube API
- **Mod Notifications**: Sends update status to mod channel
- **Preserves Static Data**: Genre, title, and series names remain unchanged
- **Updates Dynamic Data**: Episode counts, playtime, and completion status

### Enhanced Game Import System

#### Playlist-First Approach

- **YouTube Playlists**: Each playlist is treated as one game series (solves duplicate episode issue)
- **Accurate Episode Counts**: Real playlist video counts instead of estimates
- **Real Playtime Data**: Calculates actual playtime from video durations using YouTube API
- **Completion Status Detection**: Automatically detects completed vs ongoing series

#### AI-Enhanced Metadata

- **Genre Detection**: Automatically categorizes games by genre
- **Series Recognition**: Identifies game series and franchises
- **Release Year**: Adds release year information
- **Platform Detection**: Identifies gaming platforms

#### Smart Deduplication

- **Intelligent Merging**: Combines YouTube and Twitch data without duplicates
- **Series Grouping**: Groups episodes into proper game series
- **Alternative Names**: Supports multiple names per game for better search

### Database Improvements

#### Removed Redundant Fields

- **Removed `franchise_name`**: Simplified to use `series_name` only
- **Optimized Schema**: Cleaner database structure for better performance
- **Fixed All References**: Updated all functions to use new schema

#### Enhanced Search Capabilities

- **Fuzzy Matching**: Intelligent game lookup with typo tolerance
- **Alternative Names**: Support for multiple names per game (RE2, GoW 2018, etc.)
- **Full-Text Search**: Search across names, series, and notes
- **Series Disambiguation**: Smart handling of game series queries

---

## Intelligent Game Queries with Series Disambiguation

Users can ask Ash about games using natural language. The bot now intelligently handles game series disambiguation:

### Examples

- `@Ashbot Has Jonesy played God of War?` → Bot asks for clarification between God of War 1, 2, 3, (2018), Ragnarök
- `@Ashbot Has Jonesy played God of War 2018?` → Specific answer with episode count, completion status
- `@Ashbot What Final Fantasy games has Jonesy played?` → Lists all FF games with progress details
- `@Ashbot What horror games has Jonesy played?` → Genre-based query with completion status

### AI Response Features

- **Series Detection**: Recognizes 25+ major game series (God of War, Final Fantasy, Call of Duty, etc.)
- **Disambiguation**: Asks clarifying questions for ambiguous queries
- **Rich Context**: Provides episode counts, completion status, platform info
- **Database Integration**: Real-time statistics and sample games in responses
- **Channel References**: Directs users to YouTube/Twitch history channels for video links
- **Optimized Token Usage**: Reduced AI context for efficiency while maintaining quality

---

## Database Setup & Import Commands

### Step 1: Comprehensive Game Import

```text
!bulkimportplayedgames
```

This command now:

- **Fetches from YouTube playlists** (primary source) - each playlist = one game series
- **Calculates accurate playtime** from real video durations
- **Enhances with AI metadata** (genre, series, release year, platform)
- **Merges Twitch data** intelligently to avoid duplicates
- **Provides detailed preview** before import

### Step 2: Clean Recommendations

```text
!cleanplayedgames
```

Automatically removes games from recommendations that have already been played:

- **Smart Title Analysis**: Extracts game names from video titles
- **Fuzzy Matching**: 75% similarity threshold for accurate matching
- **Preview Before Removal**: Shows what will be removed with confidence scores
- **Confirmation Required**: Prevents accidental deletions

### Step 3: Verify and Test

```text
!listplayedgames
!dbstats
@Ashbot What games has Jonesy played?
```

---

## Advanced Administration

### Automatic Maintenance

#### Scheduled Updates

- **Every Sunday at 12:00 PM**: Automatic refresh of ongoing games
- **Smart Updates**: Only updates games with changed episode counts
- **Preserves Manual Data**: Genre, title, series names remain unchanged
- **Mod Notifications**: Status updates sent to mod alert channel

#### Data Integrity

- **Smart Upsert Logic**: Running imports again updates existing games without duplicates
- **Alternative Names Merging**: Combines unique alternative names
- **Playtime Accumulation**: Adds new playtime to existing totals
- **Notes Appending**: Preserves existing notes while adding new information

### Enhanced API Integration

#### YouTube Data API v3

- **Playlist Analysis**: Primary source for game series detection
- **Video Duration Fetching**: Accurate playtime calculation
- **Rate Limiting**: Respects API quotas with automatic delays
- **Fallback Mechanisms**: Video parsing if playlists unavailable

#### Twitch Helix API

- **VOD Analysis**: Comprehensive Twitch gaming history
- **Duration Parsing**: Accurate playtime from Twitch format (1h23m45s)
- **Smart Merging**: Combines with YouTube data without duplicates
- **Error Handling**: Graceful handling of API limitations

#### AI Enhancement

- **Batch Processing**: Efficient metadata enhancement for multiple games
- **Genre Classification**: Automatic genre detection
- **Series Recognition**: Identifies game franchises and series
- **Token Optimization**: Reduced context for cost efficiency

### Data Management Commands (Admin Only)

#### Bulk Operations

- `!bulkimportgames` - Import game recommendations from migration script
- `!bulkimportplayedgames` - Comprehensive game import with AI enhancement
- `!cleanplayedgames` - Remove already-played games using API analysis
- `!clearallgames` - Clear all game recommendations (with confirmation)
- `!importstrikes` - Import strikes from strikes.json file
- `!clearallstrikes` - Clear all strike records (with confirmation)

#### Debugging Commands

- `!debugstrikes` - Debug strikes database issues
- `!teststrikes` - Test individual strike queries
- `!addteststrikes` - Add test strike data
- `!fixgamereasons` - Fix game recommendation reason formatting
- `!listmodels` - List available Gemini AI models

---

## Technical Documentation

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

   ```bash
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

### Project Structure

```text
Live/
├── ash_bot_fallback.py    # Main bot file with enhanced game import system
├── database.py            # Database operations with optimized schema
├── data_migration.py      # Data migration utilities
├── requirements.txt       # Python dependencies
├── Procfile              # Railway deployment config
├── railway.toml          # Railway build settings
└── README.md             # This file
```

### Database Schema (Updated)

The bot automatically creates these tables on first run:

- **strikes**: User strike tracking with bulk import support
- **game_recommendations**: Community game suggestions with contributor tracking
- **played_games**: Comprehensive played games database (enhanced schema)
- **bot_config**: Bot configuration storage including scheduled task settings

#### Enhanced Played Games Table Fields

- `canonical_name`: Official game name for database searches
- `alternative_names`: Array of alternative names (RE2, GoW 2018, etc.)
- `series_name`: Game series (God of War, Final Fantasy, etc.) - **replaces franchise_name**
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

#### Bot Permissions

Required Discord permissions:

- Read Messages
- Send Messages
- Read Message History
- Use Slash Commands
- Manage Messages (for moderator features)

### AI Features & Game Series Disambiguation

#### Supported Game Series

The bot recognizes these major game series for disambiguation:

- **Action**: God of War, Devil May Cry, Bayonetta
- **RPG**: Final Fantasy, The Elder Scrolls, Fallout, Mass Effect, Dragon Age, The Witcher, Dark Souls, Persona
- **FPS**: Call of Duty, Battlefield, Halo, Rainbow Six, Ghost Recon
- **Adventure**: Assassin's Creed, Tomb Raider, Uncharted
- **Horror**: Resident Evil, Silent Hill, Dead Space
- **Racing**: Need for Speed, Gran Turismo, Forza
- **Sports**: FIFA, Madden, NBA 2K
- **Fighting**: Mortal Kombat, Street Fighter, Tekken
- **Nintendo**: Super Mario, The Legend of Zelda, Pokémon, Metroid
- **Indie**: Borderlands, Bioshock, Dishonored

#### Optimized AI Response Protocols

1. **General Queries** (`"what games has Jonesy played?"`):
   - Shows 3-4 diverse examples (reduced from 8 for efficiency)
   - Asks user to specify genre, franchise, or time period for detailed lists

2. **Specific Game Queries** (`"has Jonesy played Dark Souls?"`):
   - Searches database first for exact matches
   - Provides details including episodes, completion status, playtime
   - References YouTube playlist if available

3. **Genre Queries** (`"what horror games has Jonesy played?"`):
   - Lists games from specific genre with episode counts and completion status
   - Groups by series when applicable

4. **Franchise Queries** (`"what Final Fantasy games has Jonesy played?"`):
   - Shows all games in franchise with progress details
   - Chronological ordering when possible

5. **Series Disambiguation** (`"has Jonesy played God of War?"`):
   - Acknowledges multiple entries exist
   - Lists specific games from database if available
   - Asks for clarification with analytical persona

### Performance Optimizations

#### AI Token Efficiency

- **Reduced Context**: Minimal prompts for better cost efficiency
- **Conditional Context**: Only adds game database context for game-related queries
- **Batch Processing**: Processes multiple games in single AI calls
- **Smart Caching**: Avoids redundant AI calls for similar queries

#### Database Performance

- **Indexed Searches**: Optimized queries for faster game lookups
- **Bulk Operations**: Efficient batch processing for imports
- **Smart Upserts**: Intelligent merging without duplicates
- **Connection Pooling**: Optimized database connections

#### API Rate Limiting

- **YouTube API**: 0.1 second delays between requests
- **Twitch API**: Proper OAuth token management
- **Error Handling**: Graceful degradation when APIs are unavailable
- **Quota Management**: Respects API limits and quotas

### Monitoring & Maintenance

#### Automatic Monitoring

- **Scheduled Health Checks**: Sunday midday system status
- **Database Integrity**: Automatic validation of game data
- **API Status Monitoring**: Tracks API availability and quotas
- **Error Reporting**: Comprehensive error logging and notifications

#### Manual Monitoring Tools

- `!ashstatus` - Bot operational status
- `!dbstats` - Database statistics and health
- `!debugstrikes` - Strike system diagnostics
- `!listmodels` - AI model availability

### Troubleshooting

#### Common Issues

1. **Scheduled Updates Not Running**
   - Check bot uptime and Railway logs
   - Verify `YOUTUBE_API_KEY` is configured
   - Ensure mod alert channel is accessible

2. **Game Import Issues**
   - Verify API credentials are correct
   - Check API quotas and rate limits
   - Review error messages in bot responses

3. **AI Features Not Working**
   - Verify `GOOGLE_API_KEY` is set
   - Check Google AI API quota/billing
   - Monitor for rate limiting
   - Bot will use fallback responses automatically

4. **Database Performance Issues**
   - Monitor Railway database metrics
   - Check for connection pool exhaustion
   - Review query performance in logs

### Security & Best Practices

- **Environment Variables**: All secrets stored securely in Railway
- **API Key Rotation**: Regular rotation of API keys recommended
- **Permission Gating**: Moderator commands properly restricted
- **Input Validation**: All user inputs sanitized and validated
- **Error Handling**: Comprehensive error handling prevents crashes
- **Rate Limiting**: Respects all external API limits

---

## Migration Guide

### From Previous Versions

If upgrading from an older version:

1. **Database Schema Update**: The bot will automatically remove the `franchise_name` column
2. **Re-import Games**: Run `!bulkimportplayedgames` to get enhanced metadata
3. **Verify Scheduled Tasks**: Check that Sunday updates are working with `!ashstatus`
4. **Update API Keys**: Ensure YouTube and Twitch API keys are configured for full functionality

### Data Preservation

- **Existing Games**: All existing played games data is preserved during updates
- **Strike Records**: Strike data remains intact during schema updates
- **Game Recommendations**: Recommendation list is preserved with enhanced formatting
- **Configuration**: Bot settings and persona configurations are maintained

---

**Ready to deploy?** Push your code to GitHub, connect to Railway, add your environment variables, and your enhanced bot will be live with automatic scheduled updates, comprehensive game import system, and optimized AI responses!

The bot now provides a complete gaming history management solution with automatic maintenance, accurate data collection, and intelligent user interactions.
