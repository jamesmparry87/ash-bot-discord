# Ash Discord Bot - Railway Deployment Guide

A sophisticated Discord moderation and AI assistant bot featuring strike tracking, game recommendations, bulk data migration, and personality-driven interactions with dynamic game lookup capabilities.

## Features

- **Strike Management**: Automatic strike tracking with PostgreSQL database persistence
- **AI Conversations**: Powered by Google's Gemini AI with Ash character personality
- **Game Recommendations**: Community-driven game suggestion system with bulk import
- **Dynamic Game Lookup**: Ask Ash about games in the recommendation database
- **Data Migration**: Bulk import tools for existing strike and game data
- **Persistent Data**: PostgreSQL database for reliable data storage
- **Railway Optimized**: Configured for seamless Railway.app deployment
- **Enhanced Fallback**: Intelligent responses even when AI is offline

## Railway.app Deployment

### Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **Discord Bot Token**: Create a bot at [Discord Developer Portal](https://discord.com/developers/applications)
3. **Google AI API Key**: Get your key from [Google AI Studio](https://makersuite.google.com/app/apikey)

### Deployment Steps

#### 1. Connect Repository

- Fork or clone this repository to your GitHub account
- Connect your GitHub repository to Railway

#### 2. Add PostgreSQL Database

- In your Railway project, click "New Service"
- Select "Database" → "PostgreSQL"
- Railway will automatically provide a `DATABASE_URL` environment variable

#### 3. Configure Environment Variables

Set these environment variables in Railway:

```text
DISCORD_TOKEN=your_discord_bot_token_here
GOOGLE_API_KEY=your_google_ai_api_key_here
```

**Note**: `DATABASE_URL` is automatically provided by Railway's PostgreSQL service.

#### 4. Deploy

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

- **strikes**: User strike tracking with bulk import support
- **game_recommendations**: Community game suggestions with contributor tracking
- **bot_config**: Bot configuration storage

### Bot Commands

#### User Commands

- `!addgame <name> - <reason>` - Add game recommendation
- `!recommend <name> - <reason>` - Add game recommendation (alias)
- `!listgames` - List all game recommendations
- **Dynamic Queries**: `@Ashbot Has Jonesy played [game name]?` - Query game database

#### Moderator Commands (Requires "Manage Messages" permission)

**Strike Management:**

- `!strikes @user` - Check user's strikes
- `!resetstrikes @user` - Reset user's strikes
- `!allstrikes` - List all users with strikes

**Game Management:**

- `!removegame <name/index>` - Remove game recommendation
- `!clearallgames` - Clear all game recommendations (with confirmation)

**Data Migration:**

- `!importstrikes` - Import strikes from strikes.json file
- `!bulkimportgames` - Import games from migration script (recommended)
- `!dbstats` - Show database statistics and top contributors
- `!clearallstrikes` - Clear all strike records (with confirmation)

**Bot Configuration:**

- `!setpersona <text>` - Change bot personality
- `!getpersona` - View current personality
- `!toggleai` - Enable/disable AI conversations
- `!ashstatus` - View bot status and statistics

### Dynamic Game Lookup

Users can ask Ash about games using natural language:

- `@Ashbot Has Jonesy played Resident Evil 2?`
- `@Ashbot Did Captain Jonesy play Dark Souls?`
- `@Ashbot Has JonesySpaceCat played Sekiro?`

Ash will search the recommendation database and respond in character, indicating whether the game is catalogued and who suggested it.

### Data Migration

#### Game Recommendation Migration (Primary Use Case)

The bot is designed to efficiently import large lists of game recommendations with contributor attribution. This is the main migration feature for most users.

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

#### Step-by-Step Game Migration Process

#### Method 1: Bot Command Import (Easiest - Recommended)

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

3. **Verify Import**
   - Use `!dbstats` to check total games imported
   - Use `!listgames` to spot-check entries

#### Method 2: Manual Script Execution (Advanced)

1. **Prepare Your Games List** (same as Method 1)
2. **Run Migration Script**

   ```bash
   cd Live
   python data_migration.py
   ```

#### Method 3: Individual Bot Commands (For smaller lists)

1. **Clear Existing Data** (if needed)

   ```text
   !clearallgames
   ```

   Type `CONFIRM DELETE` when prompted

2. **Import Games Individually**

   ```text
   !addgame Dark Souls - mysticaldragonborn
   !addgame Resident Evil 2
   ```

3. **Verify Results**

   ```text
   !dbstats
   !listgames
   ```

#### Method 3: Direct Database Import (Advanced)

For very large datasets or custom formatting needs, modify the migration script directly and run it on Railway.

#### Strike Migration (Reference)

For strike data (if needed in future):

- Use `!importstrikes` to import from `strikes.json`
- Manual strike management via `!strikes @user` commands

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

### AI Features

#### Personality System

Ash maintains character consistency with:

- **Clinical Analysis**: Responds with scientific precision
- **Character Loyalty**: Special deference to "Captain Jonesy"
- **Fallback Intelligence**: Maintains character even when AI is offline
- **Dynamic Responses**: Context-aware conversation handling

#### Enhanced Fallback System

When AI is unavailable, Ash provides:

- **Pattern-based responses** for common question types
- **In-character explanations** of limited functionality
- **Command guidance** for available features
- **Personality consistency** regardless of AI status

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

4. **Migration Issues**
   - Ensure data files are in correct format
   - Check file permissions and accessibility
   - Use `!dbstats` to verify successful imports

#### Support

For deployment issues:

- Check Railway documentation
- Review bot logs in Railway dashboard
- Verify all environment variables are configured
- Test migration commands with small datasets first

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

---

**Ready to deploy?** Push your code to GitHub, connect to Railway, add your environment variables, and your bot will be live in minutes with full data migration capabilities!
