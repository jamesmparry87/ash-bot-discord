# Ash Discord Bot - User Guide

A sophisticated Discord moderation and AI assistant bot featuring strike tracking, game recommendations, and personality-driven interactions with dynamic game lookup capabilities.

## Quick Reference for Daily Use

### User Commands (Everyone)

- `!addgame <name> - <reason>` - Add game recommendation
- `!recommend <name> - <reason>` - Add game recommendation (alias)
- `!listgames` - List all game recommendations
- Ask Ash: `@Ashbot Has Jonesy played [game name]?` - Query game database

### Moderator Commands (Requires "Manage Messages" permission)

#### Strike Management

- `!strikes @user` - Check user's strikes
- `!resetstrikes @user` - Reset user's strikes
- `!allstrikes` - List all users with strikes

#### Game Management

- `!removegame <name/index>` - Remove game recommendation
- `!listgames` - View all recommendations with index numbers

#### Bot Status

- `!ashstatus` - View bot status and statistics
- `!dbstats` - Show database statistics and top contributors

#### AI Configuration

- `!setpersona <text>` - Change bot personality
- `!getpersona` - View current personality
- `!toggleai` - Enable/disable AI conversations

### Dynamic Game Lookup

Users can ask Ash about games using natural language:

- `@Ashbot Has Jonesy played Resident Evil 2?`
- `@Ashbot Did Captain Jonesy play Dark Souls?`
- `@Ashbot Has JonesySpaceCat played Sekiro?`

Ash will search the recommendation database and respond in character, indicating whether the game is catalogued and who suggested it.

### AI Features

#### Ash's Personality

- Clinical Analysis: Responds with scientific precision
- Character Loyalty: Special deference to "Captain Jonesy"
- Fallback Intelligence: Maintains character even when AI is offline
- Dynamic Responses: Context-aware conversation handling

---

## Advanced Administration

### Data Management Commands (Admin Only)

#### Bulk Operations

- `!bulkimportgames` - Import games from migration script
- `!cleanplayedgames` - Remove already-played games using YouTube/Twitch APIs
- `!clearallgames` - Clear all game recommendations (with confirmation)
- `!importstrikes` - Import strikes from strikes.json file
- `!clearallstrikes` - Clear all strike records (with confirmation)

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
├── ash_bot_fallback.py    # Main bot file
├── database.py            # Database operations & bulk import
├── data_migration.py      # Data migration utilities
├── requirements.txt       # Python dependencies
├── Procfile              # Railway deployment config
├── railway.toml          # Railway build settings
└── README.md             # This file
```

### Database Schema

The bot automatically creates these tables on first run:

- strikes: User strike tracking with bulk import support
- game_recommendations: Community game suggestions with contributor tracking
- bot_config: Bot configuration storage

### Configuration

#### Discord Server Setup

Update these IDs in `ash_bot_fallback.py`:

- `GUILD_ID`: Your Discord server ID
- `VIOLATION_CHANNEL_ID`: Channel for automatic strike detection
- `MOD_ALERT_CHANNEL_ID`: Channel for moderation alerts
- `RECOMMEND_CHANNEL_ID`: Channel for game recommendation updates

#### Bot Permissions

Required Discord permissions:

- Read Messages
- Send Messages
- Read Message History
- Use Slash Commands
- Manage Messages (for moderator features)

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

#### Migration Process

#### Method 1: Bot Command Import (Recommended)

1. **Update Migration Script**

   - Edit `data_migration.py`
   - Replace `SAMPLE_GAMES_TEXT` with your games list
   - Format: one game per line, use "game name - username" for attribution

2. **Run Import Command**

   ```text
   !bulkimportgames
   ```

   - Shows preview of games to be imported
   - Type `CONFIRM IMPORT` to proceed
   - Automatically updates recommendation list

3. **Clean Already-Played Games**

   ```text
   !cleanplayedgames
   ```

   - Analyzes e and Twitch play history
   - Shows preview of games to remove
   - Type `CONFIRM CLEANUP` to proceed

4. **Verify Results**
   - Use `!dbstats` to check final game count
   - Use `!listgames` to spot-check entries

#### Method 2: Manual Script Execution

1. **Prepare Your Games List** (same as Method 1)
2. **Run Migration Script**

   ```bash
   cd Live
   python data_migration.py
   ```

#### Method 3: Individual Commands (Small Lists)

1. **Clear Existing Data** (if needed)

   ```text
   !clearallgames
   ```

2. **Import Games Individually**

   ```text
   !addgame Dark Souls - mysticaldragonborn
   !addgame Resident Evil 2
   ```

#### Strike Migration

For strike data (if needed):

- Use `!importstrikes` to import from `strikes.json`
- Manual strike management via `!strikes @user` commands

### Monitoring

#### Railway Logs

Monitor your bot through Railway's built-in logging:

- View real-time logs in the Railway dashboard
- Check for database connection issues
- Monitor AI API usage and migration progress

#### Database Statistics

Use `!dbstats` to monitor:

- Total game recommendations
- Unique contributors
- Strike distribution
- Top contributors ranking

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

3. **AI Features Not Working**
   - Verify `GOOGLE_API_KEY` is set
   - Check Google AI API quota/billing
   - Monitor for rate limiting
   - Bot will use fallback responses automatically

4. **API Integration Issues**
   - Verify YouTube/Twitch API keys are configured
   - Check API quotas and rate limits
   - Review error messages in bot responses

### Security Notes

- Never commit API keys or tokens to version control
- Use Railway's environment variables for all secrets
- Regularly rotate your Discord bot token and API keys
- Monitor usage to prevent unexpected charges
- Moderator commands are permission-gated for security

### Performance

- Database queries are optimized for Railway's PostgreSQL
- Bulk operations use batch processing for efficiency
- AI responses are cached when possible
- Error handling prevents cascading failures
- Automatic reconnection for database issues
- Fuzzy matching optimized for large game databases

### Advanced Features

#### Bulk Data Processing

- **Efficient Batch Operations**: Uses PostgreSQL's `executemany()` for optimal performance
- **Data Validation**: Automatic type conversion and error handling
- **Progress Reporting**: Detailed feedback during migration operations
- **Rollback Protection**: Transaction-based operations with error recovery

#### Game Database Features

- **Fuzzy Matching**: Intelligent duplicate detection and game lookup
- **Contributor Tracking**: Attribution system for community recommendations
- **Dynamic Queries**: Natural language game lookup with pattern matching
- **Statistics Tracking**: Comprehensive analytics on recommendations and contributors

#### YouTube/Twitch Integration

- **Smart Title Parsing**: Extracts game names from various video title formats
- **Rate Limiting**: Respects API limits with automatic delays
- **Error Handling**: Graceful handling of API errors or missing credentials
- **Batch Processing**: Efficiently processes large video histories

---

**Ready to deploy?** Push your code to GitHub, connect to Railway, add your environment variables, and your bot will be live in minutes with full data migration and cleanup capabilities!
