# Ash Discord Bot - Railway Deployment Guide

A sophisticated Discord moderation and AI assistant bot featuring strike tracking, game recommendations, and personality-driven interactions.

## Features

- **Strike Management**: Automatic strike tracking with database persistence
- **AI Conversations**: Powered by Google's Gemini AI with character personality
- **Game Recommendations**: Community-driven game suggestion system
- **Persistent Data**: PostgreSQL database for reliable data storage
- **Railway Optimized**: Configured for seamless Railway.app deployment

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
├── database.py            # Database operations
├── requirements.txt       # Python dependencies
├── Procfile              # Railway deployment config
├── railway.toml          # Railway build settings
└── README.md             # This file
```

### Database Schema

The bot automatically creates these tables on first run:

- **strikes**: User strike tracking
- **game_recommendations**: Community game suggestions
- **bot_config**: Bot configuration storage

### Bot Commands

#### User Commands

- `!addgame <name> - <reason>` - Add game recommendation
- `!recommend <name> - <reason>` - Add game recommendation (alias)
- `!listgames` - List all game recommendations

#### Moderator Commands (Requires "Manage Messages" permission)

- `!strikes @user` - Check user's strikes
- `!resetstrikes @user` - Reset user's strikes
- `!allstrikes` - List all users with strikes
- `!removegame <name/index>` - Remove game recommendation
- `!setpersona <text>` - Change bot personality
- `!getpersona` - View current personality
- `!toggleai` - Enable/disable AI conversations
- `!ashstatus` - View bot status

### Configuration

#### Discord Server Setup

Update these IDs in `ash_bot_fallback.py`:

- `GUILD_ID`: Your Discord server ID
- `VIOLATION_CHANNEL_ID`: Channel for automatic strike detection
- `MOD_ALERT_CHANNEL_ID`: Channel for moderation alerts

#### Bot Permissions

Required Discord permissions:

- Read Messages
- Send Messages
- Read Message History
- Use Slash Commands
- Manage Messages (for moderator features)

### Monitoring

#### Railway Logs

Monitor your bot through Railway's built-in logging:

- View real-time logs in the Railway dashboard
- Check for database connection issues
- Monitor AI API usage

#### Health Checks

The bot includes automatic health monitoring:

- Database connection validation
- AI service availability checks
- Error handling with graceful fallbacks

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

#### Support

For deployment issues:

- Check Railway documentation
- Review bot logs in Railway dashboard
- Verify all environment variables are configured

### Security Notes

- Never commit API keys or tokens to version control
- Use Railway's environment variables for all secrets
- Regularly rotate your Discord bot token and API keys
- Monitor usage to prevent unexpected charges

### Performance

- Database queries are optimized for Railway's PostgreSQL
- AI responses are cached when possible
- Error handling prevents cascading failures
- Automatic reconnection for database issues

---

**Ready to deploy?** Push your code to GitHub, connect to Railway, add your environment variables, and your bot will be live in minutes!
