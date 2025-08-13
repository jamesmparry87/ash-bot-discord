# Ash Discord Bot - User Guide

A sophisticated Discord moderation and AI assistant bot featuring strike tracking, game recommendations, played games database, and personality-driven interactions with intelligent game series disambiguation.

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

#### Played Games Database Management

- `!addplayedgame <Game Name> | series:Series | year:2023 | platform:PC | status:completed | episodes:12 | notes:Additional info` - Add played game with metadata
- `!listplayedgames [series_name]` - List all played games, optionally filtered by series
- `!searchplayedgames <query>` - Search played games by name, series, or notes
- `!gameinfo <game_name>` - Get detailed information about a specific played game
- `!updateplayedgame <game_name> status:completed | episodes:15 | notes:New info` - Update game details
- `!removeplayedgame <game_name>` - Remove a played game (with confirmation)
- `!fixcanonicalname <current_name> <new_canonical_name>` - Fix game name formatting
- `!addaltname <game_name> <alternative_name>` - Add alternative name for better search
- `!removealtname <game_name> <alternative_name>` - Remove alternative name

#### Bot Status & Analytics

- `!ashstatus` - View bot status and statistics
- `!dbstats` - Show database statistics and top contributors

#### AI Configuration

- `!setpersona <text>` - Change bot personality
- `!getpersona` - View current personality
- `!toggleai` - Enable/disable AI conversations

### Intelligent Game Queries with Series Disambiguation

Users can ask Ash about games using natural language. The bot now intelligently handles game series disambiguation:

#### Examples

- `@Ashbot Has Jonesy played God of War?` → Bot asks for clarification between God of War 1, 2, 3, (2018), Ragnarök
- `@Ashbot Has Jonesy played God of War 2018?` → Specific answer with episode count, completion status
- `@Ashbot What Final Fantasy games has Jonesy played?` → Lists all FF games with progress details
- `@Ashbot What horror games has Jonesy played?` → Genre-based query with completion status

#### AI Response Features

- Series Detection: Recognizes 25+ major game series (God of War, Final Fantasy, Call of Duty, etc.)
- Disambiguation: Asks clarifying questions for ambiguous queries
- Rich Context: Provides episode counts, completion status, platform info
- Database Integration: Real-time statistics and sample games in responses
- Channel References: Directs users to YouTube/Twitch history channels for video links

---

## Initial Database Setup Commands

After deploying the bot, run these commands in order to build your played games database:

### Step 1: Import Sample Played Games Data

```text
!bulkimportplayedgames
```

This imports sample games (God of War series, The Last of Us, etc.) to get started.

### Step 2: Add Your Actual Played Games

Use the comprehensive add command for each game:

```text
!addplayedgame The Last of Us Part II | series:The Last of Us | year:2020 | platform:PlayStation 4 | status:completed | episodes:18 | notes:Full story completion

!addplayedgame God of War (2018) | series:God of War | year:2018 | platform:PlayStation 4 | status:completed | episodes:15 | alt:God of War 4,GoW 2018

!addplayedgame Resident Evil 2 (2019) | series:Resident Evil | year:2019 | platform:PC | status:completed | episodes:8 | alt:RE2 Remake,Resident Evil 2 Remake
```

### Step 3: Verify Database

```text
!listplayedgames
!dbstats
```

### Step 4: Test AI Responses

Try these queries to test the disambiguation system:

- `@Ashbot Has Jonesy played God of War?`
- `@Ashbot What games has Jonesy played?`
- `@Ashbot What horror games has Jonesy played?`

---

## Advanced Administration

### Data Management Commands (Admin Only)

#### Bulk Operations

- `!bulkimportgames` - Import game recommendations from migration script
- `!bulkimportplayedgames` - Import sample played games data
- `!cleanplayedgames` - Remove already-played games using YouTube/Twitch APIs
- `!clearallgames` - Clear all game recommendations (with confirmation)
- `!importstrikes` - Import strikes from strikes.json file
- `!clearallstrikes` - Clear all strike records (with confirmation)

#### Debugging Commands

- `!debugstrikes` - Debug strikes database issues
- `!teststrikes` - Test individual strike queries
- `!addteststrikes` - Add test strike data
- `!fixgamereasons` - Fix game recommendation reason formatting
- `!listmodels` - List available Gemini AI models

### Automated Game Cleanup

The `!cleanplayedgames` command automatically:

- Fetches Play History from Captain Jonesy's YouTube (UCPoUxLHeTnE9SUDAkqfJzDQ) and Twitch (jonesyspacecat)
- Analyzes Video Titles to extract game names using pattern matching
- Matches Games using fuzzy matching (75% similarity threshold)
- Shows Preview of games to be removed with match confidence
- Requires Confirmation before removing any games
- Updates Lists automatically after cleanup

#### Required API Keys

- `YOUTUBE_API_KEY` - YouTube Data API v3 key
- `TWITCH_CLIENT_ID` - Twitch application client ID
- `TWITCH_CLIENT_SECRET` - Twitch application client secret

---

## Technical Documentation

### Railway.app Deployment

#### Prerequisites

1. Railway Account: Sign up at [railway.app](https://railway.app)
2. Discord Bot Token: Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
3. Google AI API Key: Get your key from [Google AI Studio](https://makersuite.google.com/app/apikey)

#### Deployment Steps

1. Connect Repository

   - Fork or clone this repository to your GitHub account
   - Connect your GitHub repository to Railway

2. Add PostgreSQL Database

   - In your Railway project, click "New Service"
   - Select "Database" → "PostgreSQL"
   - Railway will automatically provide a `DATABASE_URL` environment variable

3. Configure Environment Variables

   Set these environment variables in Railway:

   ```bash
   DISCORD_TOKEN=your_discord_bot_token_here
   GOOGLE_API_KEY=your_google_ai_api_key_here
   YOUTUBE_API_KEY=your_youtube_api_key_here (optional)
   TWITCH_CLIENT_ID=your_twitch_client_id_here (optional)
   TWITCH_CLIENT_SECRET=your_twitch_client_secret_here (optional)
   ```

4. Deploy

   - Railway will automatically detect the Python project
   - It will install dependencies from `requirements.txt`
   - The bot will start using the `Procfile` configuration

### Project Structure

```text
Live/
├── ash_bot_fallback.py    # Main bot file with AI and played games integration
├── database.py            # Database operations & played games management
├── data_migration.py      # Data migration utilities
├── requirements.txt       # Python dependencies
├── Procfile              # Railway deployment config
├── railway.toml          # Railway build settings
└── README.md             # This file
```

### Database Schema

The bot automatically creates these tables on first run:

- **strikes**: User strike tracking with bulk import support
- **game_recommendations**: Community game suggestions with contributor tracking
- **played_games**: Comprehensive played games database with series, episodes, completion status
- **bot_config**: Bot configuration storage

#### Played Games Table Fields

- `canonical_name`: Official game name for database searches
- `alternative_names`: Array of alternative names (RE2, GoW 2018, etc.)
- `series_name`: Game series (God of War, Final Fantasy, etc.)
- `franchise_name`: Broader franchise grouping
- `genre`: Game genre for filtering
- `release_year`: Release year for chronological sorting
- `platform`: Gaming platform (PC, PlayStation 4, etc.)
- `completion_status`: completed, ongoing, dropped, unknown
- `total_episodes`: Number of episodes/videos recorded
- `total_playtime_minutes`: Total playtime in minutes
- `youtube_playlist_url`: Link to YouTube playlist
- `twitch_vod_urls`: Array of Twitch VOD URLs
- `notes`: Additional notes and context

### Configuration

#### Discord Server Setup

Update these IDs in `ash_bot_fallback.py`:

- `GUILD_ID`: Your Discord server ID
- `VIOLATION_CHANNEL_ID`: Channel for automatic strike detection
- `MOD_ALERT_CHANNEL_ID`: Channel for moderation alerts
- `TWITCH_HISTORY_CHANNEL_ID`: Channel for Twitch history data
- `YOUTUBE_HISTORY_CHANNEL_ID`: Channel for YouTube history data
- `RECOMMEND_CHANNEL_ID`: Channel for game recommendation updates

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

#### AI Response Protocols

1. **General Queries** (`"what games has Jonesy played?"`):
   - Shows 5-8 diverse examples from different genres/franchises
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

### Data Migration

#### Game Recommendation Migration

The bot is designed to efficiently import large lists of game recommendations with contributor attribution.

**Supported Formats:**

- **With Contributors**: `game name - username` (e.g., "Dark Souls - mysticaldragonborn")
- **Without Contributors**: `game name` (e.g., "Resident Evil 2")
- **Mixed Lists**: Combination of both formats in the same import
- **Large Datasets**: Optimized for 80+ game entries in single operation

**Key Features:**

- **Fuzzy Duplicate Detection**: Prevents near-duplicates with 85% similarity matching
- **Typo Tolerance**: Handles variations like "RE2" vs "Resident Evil 2"
- **Batch Processing**: Uses PostgreSQL's efficient bulk operations
- **Contributor Tracking**: Maintains attribution for community recommendations

#### Played Games Migration

**Manual Entry Method** (Recommended for accuracy):

```text
!addplayedgame Game Name | series:Series Name | year:2023 | platform:PC | status:completed | episodes:12 | alt:Alternative Name 1,Alt Name 2 | notes:Additional context
```

**Bulk Import Method** (For large datasets):

1. Update `data_migration.py` with your played games data
2. Run `!bulkimportplayedgames`
3. Use individual commands to add missing metadata

#### Migration Process

#### Method 1: Initial Setup (New Database)

1. **Import Sample Data**

   ```text
   !bulkimportplayedgames
   ```

2. **Add Your Games**

   ```text
   !addplayedgame Your Game | series:Series | year:2023 | platform:PC | status:completed | episodes:10
   ```

3. **Verify Setup**

   ```text
   !listplayedgames
   !dbstats
   ```

#### Method 2: Bot Command Import (Game Recommendations)

1. **Update Migration Script**
   - Edit `data_migration.py`
   - Replace `SAMPLE_GAMES_TEXT` with your games list
   - Format: one game per line, use "game name - username" for attribution

2. **Run Import Command**

   ```text
   !bulkimportgames
   ```

3. **Clean Already-Played Games**

   ```text
   !cleanplayedgames
   ```

#### Method 3: Individual Commands (Small Lists)

1. **Clear Existing Data** (if needed)

   ```text
   !clearallgames
   ```

2. **Import Games Individually**

   ```text
   !addgame Dark Souls
   !addgame Resident Evil 2
   ```

### Monitoring

#### Railway Logs

Monitor your bot through Railway's built-in logging:

- View real-time logs in the Railway dashboard
- Check for database connection issues
- Monitor AI API usage and migration progress

#### Database Statistics

Use `!dbstats` to monitor:

- Total game recommendations
- Total played games
- Unique contributors
- Strike distribution
- Top contributors ranking
- Played games completion statistics

### Troubleshooting

#### Common Issues

1. **Bot Not Responding**
   - Check environment variables are set correctly
   - Verify Discord token is valid
   - Ensure bot has proper permissions in your server

2. **Database Errors**
   - Confirm PostgreSQL service is running
   - Check `DATABASE_URL` environment variable
   - Review Railway logs for connection issues
   - Use `!debugstrikes` for strike-specific issues

3. **AI Features Not Working**
   - Verify `GOOGLE_API_KEY` is set
   - Check Google AI API quota/billing
   - Monitor for rate limiting
   - Bot will use fallback responses automatically

4. **Game Series Disambiguation Not Working**
   - Ensure played games database has data (`!listplayedgames`)
   - Check AI is enabled (`!toggleai`)
   - Verify game series are properly categorized in database

5. **API Integration Issues**
   - Verify YouTube/Twitch API keys are configured
   - Check API quotas and rate limits
   - Review error messages in bot responses

### Security Notes

- Never commit API keys or tokens to version control
- Use Railway's environment variables for all secrets
- Regularly rotate your Discord bot token and API keys
- Monitor usage to prevent unexpected charges
- Moderator commands are permission-gated for security
- Played games management restricted to moderators only

### Performance

- Database queries are optimized for Railway's PostgreSQL
- Bulk operations use batch processing for efficiency
- AI responses include real-time database statistics
- Error handling prevents cascading failures
- Automatic reconnection for database issues
- Fuzzy matching optimized for large game databases
- Series disambiguation uses indexed searches

### Advanced Features

#### Played Games Database Features

- **Comprehensive Metadata**: Series, genre, platform, completion status, episode counts
- **Alternative Names**: Support for multiple names per game (RE2, Resident Evil 2, etc.)
- **Series Grouping**: Intelligent organization by game series and franchises
- **Progress Tracking**: Episode counts, playtime, completion status
- **Media Links**: YouTube playlists and Twitch VOD integration
- **Search Capabilities**: Full-text search across names, series, and notes

#### AI Integration Features

- **Dynamic Context**: Real-time database statistics in AI responses
- **Series Intelligence**: Recognizes 25+ major game series for disambiguation
- **Response Protocols**: Different handling for general, specific, genre, and franchise queries
- **Fallback Handling**: Graceful degradation when AI is unavailable
- **Natural Language**: Supports various query formats and phrasings

#### Game Database Features

- **Fuzzy Matching**: Intelligent duplicate detection and game lookup
- **Contributor Tracking**: Attribution system for community recommendations
- **Dynamic Queries**: Natural language game lookup with pattern matching
- **Statistics Tracking**: Comprehensive analytics on recommendations and contributors
- **Series Disambiguation**: Intelligent handling of game series queries

#### YouTube/Twitch Integration

- **Smart Title Parsing**: Extracts game names from various video title formats
- **Rate Limiting**: Respects API limits with automatic delays
- **Error Handling**: Graceful handling of API errors or missing credentials
- **Batch Processing**: Efficiently processes large video histories

---

**Ready to deploy?** Push your code to GitHub, connect to Railway, add your environment variables, and your bot will be live in minutes with full played games database, series disambiguation, and intelligent AI responses!
