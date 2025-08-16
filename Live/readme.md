# Ash Discord Bot - Gaming Database & Moderation System

A Discord moderation and AI assistant bot featuring strike tracking, game recommendations, comprehensive played games database, and personality-driven interactions with intelligent game series disambiguation.

## Quick Reference

### User Commands (Everyone)

- `!addgame <name> - <reason>` - Add game recommendation
- `!recommend <name> - <reason>` - Add game recommendation (alias)
- `!listgames` - List all game recommendations
- Ask Ash: `@Ashbot Has Jonesy played [game name]?` - Query played games database
- Ask Ash: `@Ashbot What games has Jonesy played?` - Get examples from played games database
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

### Intelligent Game Queries

Users can ask Ash about games using natural language with smart series disambiguation:

**Examples:**

- `@Ashbot Has Jonesy played God of War?` → Bot asks for clarification between different entries
- `@Ashbot Has Jonesy played God of War 2018?` → Specific answer with episode count and completion status
- `@Ashbot What Final Fantasy games has Jonesy played?` → Lists all FF games with progress details
- `@Ashbot What horror games has Jonesy played?` → Genre-based query with completion status

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

### Project Structure

```text
Live/
├── ash_bot_fallback.py    # Main bot file
├── database.py            # Database operations
├── data_migration.py      # Data migration utilities
├── requirements.txt       # Python dependencies
├── Procfile              # Railway deployment config
├── railway.toml          # Railway build settings
└── README.md             # This file
```

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

#### Bot Permissions

Required Discord permissions:

- Read Messages
- Send Messages
- Read Message History
- Use Slash Commands
- Manage Messages (for moderator features)

---

## Usage Guide

### Setting Up Game Database

#### Step 1: Comprehensive Game Import

```text
!bulkimportplayedgames
```

This command:

- Fetches from YouTube playlists (primary source) - each playlist = one game series
- Calculates accurate playtime from real video durations
- Enhances with AI metadata (genre, series, release year, platform)
- Merges Twitch data intelligently to avoid duplicates
- Provides detailed preview before import

#### Step 2: Clean Recommendations

```text
!cleanplayedgames
```

Automatically removes games from recommendations that have already been played:

- Smart title analysis extracts game names from video titles
- Fuzzy matching with 75% similarity threshold for accurate matching
- Preview before removal shows what will be removed with confidence scores
- Confirmation required to prevent accidental deletions

#### Step 3: Verify and Test

```text
!listplayedgames
!dbstats
@Ashbot What games has Jonesy played?
```

### Game Series Disambiguation

The bot recognizes major game series for disambiguation:

- **Action**: God of War, Devil May Cry, Bayonetta
- **RPG**: Final Fantasy, The Elder Scrolls, Fallout, Mass Effect, Dragon Age, The Witcher, Dark Souls, Persona
- **FPS**: Call of Duty, Battlefield, Halo, Rainbow Six, Ghost Recon
- **Adventure**: Assassin's Creed, Tomb Raider, Uncharted
- **Horror**: Resident Evil, Silent Hill, Dead Space
- **Racing**: Need for Speed, Gran Turismo, Forza
- **Sports**: FIFA, Madden, NBA 2K
- **Fighting**: Mortal Kombat, Street Fighter, Tekken
- **Nintendo**: Super Mario, The Legend of Zelda, Pokémon, Metroid

### Individual Game Updates

The `!updateplayedgame` command allows precise updates to individual game records using either the game name or database ID:

#### Command Format

```text
!updateplayedgame <game_name_or_id> field1:value1 | field2:value2 | field3:value3
```

#### Available Update Fields

- `status:completed` - Update completion status (completed, ongoing, dropped, unknown)
- `episodes:15` - Update total episode count (numeric)
- `notes:New information` - Update or append notes
- `platform:PC` - Update gaming platform
- `year:2023` - Update release year (numeric)
- `series:Series Name` - Update series/franchise name
- `youtube:https://youtube.com/playlist?list=...` - Update YouTube playlist URL

#### Examples

**Update by Game Name:**

```text
!updateplayedgame "God of War (2018)" status:completed | episodes:25 | notes:Excellent Norse mythology adaptation
```

**Update by Database ID:**

```text
!updateplayedgame 42 status:ongoing | episodes:12 | platform:PlayStation 5
```

**Single Field Update:**

```text
!updateplayedgame "Dark Souls" status:completed
```

**Multiple Field Update:**

```text
!updateplayedgame "Final Fantasy VII" status:completed | episodes:30 | year:1997 | platform:PC | notes:Classic JRPG masterpiece
```

#### Automatic Metadata Refresh

When used without any field updates (e.g., `!updateplayedgame 42` or `!updateplayedgame "Dark Souls"`), the command will automatically:

- **Analyze missing metadata** - Checks for missing genre, alternative names, series info, and release year
- **Use AI enhancement** - Applies the same AI analysis as `!updateplayedgames` but for a single game
- **Show detailed results** - Displays exactly what metadata was enhanced
- **Preserve existing data** - Only fills in missing fields, doesn't overwrite existing information

This is perfect for:

- **Testing AI enhancement** on individual games before running the full batch update
- **Debugging database issues** by updating one game at a time
- **Filling gaps** in specific games after manual database edits
- **Verifying** that the enhancement logic works correctly

**Manual vs. Automatic Updates:**

- `!updateplayedgame 42 status:completed | notes:Great game` - Manual field updates only
- `!updateplayedgame 42` - Automatic AI metadata refresh for missing fields
- `!updateplayedgames` - AI metadata refresh for all games with missing metadata

#### Benefits of ID-Based Updates

- **Precision**: No ambiguity with similar game names
- **Database Integration**: Works seamlessly with manual PostgreSQL edits
- **Efficiency**: Faster lookups for frequently updated games
- **Consistency**: Reliable updates even after canonical name changes

To find a game's ID, use `!gameinfo <game_name>` - the ID is shown in the footer.

### AI Response Protocols

1. **General Queries** (`"what games has Jonesy played?"`): Shows diverse examples, asks user to specify genre or franchise for detailed lists
2. **Specific Game Queries** (`"has Jonesy played Dark Souls?"`): Searches database first, provides details including episodes, completion status, playtime
3. **Genre Queries** (`"what horror games has Jonesy played?"`): Lists games from specific genre with episode counts and completion status
4. **Franchise Queries** (`"what Final Fantasy games has Jonesy played?"`): Shows all games in franchise with progress details
5. **Series Disambiguation** (`"has Jonesy played God of War?"`): Acknowledges multiple entries exist, lists specific games from database, asks for clarification

---

## Advanced Administration

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

### API Integration

#### YouTube Data API v3

- Playlist analysis for game series detection
- Video duration fetching for accurate playtime calculation
- Rate limiting with automatic delays
- Fallback mechanisms for video parsing if playlists unavailable

#### Twitch Helix API

- VOD analysis for comprehensive Twitch gaming history
- Duration parsing for accurate playtime from Twitch format (1h23m45s)
- Smart merging with YouTube data without duplicates
- Graceful handling of API limitations

#### AI Enhancement (Google Gemini)

- Batch processing for efficient metadata enhancement
- Genre classification and series recognition
- Automatic detection of release years and platforms
- Optimized token usage for cost efficiency

### Monitoring & Maintenance

#### Automatic Monitoring

- Scheduled health checks every Sunday at midday
- Database integrity validation of game data
- API status monitoring and quota tracking
- Comprehensive error logging and notifications

#### Manual Monitoring Tools

- `!ashstatus` - Bot operational status
- `!dbstats` - Database statistics and health
- `!debugstrikes` - Strike system diagnostics
- `!listmodels` - AI model availability

### Troubleshooting

#### Common Issues

1. **Scheduled Updates Not Running**: Check bot uptime, verify `YOUTUBE_API_KEY` is configured, ensure mod alert channel is accessible
2. **Game Import Issues**: Verify API credentials, check API quotas and rate limits, review error messages in bot responses
3. **AI Features Not Working**: Verify `GOOGLE_API_KEY` is set, check Google AI API quota/billing, monitor for rate limiting (bot will use fallback responses automatically)
4. **Database Performance Issues**: Monitor Railway database metrics, check for connection pool exhaustion, review query performance in logs

### Security & Best Practices

- All secrets stored securely in Railway environment variables
- Regular rotation of API keys recommended
- Moderator commands properly restricted by Discord permissions
- All user inputs sanitized and validated
- Comprehensive error handling prevents crashes
- Respects all external API limits and quotas

---

## Migration Guide

### From Previous Versions

If upgrading from an older version:

1. The bot will automatically update database schema as needed
2. Run `!bulkimportplayedgames` to get enhanced metadata for existing games
3. Verify scheduled tasks are working with `!ashstatus`
4. Ensure YouTube and Twitch API keys are configured for full functionality

### Data Preservation

- Existing games data is preserved during updates
- Strike records remain intact during schema updates
- Game recommendations list is preserved
- Bot settings and persona configurations are maintained

---

**Ready to deploy?** Push your code to GitHub, connect to Railway, add your environment variables, and your bot will be live with automatic scheduled updates and comprehensive game management capabilities.
                                                                                                                                                                                                                                                                                                                                            
