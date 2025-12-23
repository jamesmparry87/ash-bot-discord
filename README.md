# Ash Discord Bot - Railway Deployment Guide

A sophisticated Discord moderation and AI assistant bot featuring strike tracking, game recommendations, and personality-driven interactions with intelligent role-aware responses.

**Version 1.2** - Intelligent Persona System

## Features

### Core Features

- **Strike Management**: Automatic strike tracking with database persistence
- **AI Conversations**: Powered by Google's Gemini AI with intelligent context awareness
- **Game Recommendations**: Community-driven game suggestion system
- **Trivia Tuesday**: Weekly trivia sessions with leaderboards and participation tracking
- **Persistent Data**: PostgreSQL database for reliable data storage
- **Railway Optimized**: Configured for seamless Railway.app deployment

### Version 1.2: Intelligent Persona System

#### Role-Aware Interactions

- Ash now recognizes who you are and adjusts his responses accordingly
- Special treatment for server leadership (Captain Jonesy, JAM)
- Professional tone with moderators
- Personalized responses based on your server roles
- Works in DMs - your roles are maintained even in private conversations

#### Personalized Experience

- **Captain Jonesy**: Gets protective, deferential responses with priority status
- **Sir Decent Jam (Creator)**: Receives technical deference and creator acknowledgment  
- **Pops Arcade**: Gets analytical, skeptical responses with characteristic sarcasm
- **Moderators**: Professional cooperation and colleague-level interaction
- **Members**: Enhanced helpful responses appropriate to crew status
- **Everyone Else**: Standard helpful assistance within clearance parameters

#### Smart Features

- Automatically recognizes new moderators without code changes
- FAQ responses personalized by role (e.g., "Captain. Hello..." vs "Hello...")
- UK date format (DD-MM-YYYY) for localization
- Future-proof role detection system

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
HUGGINGFACE_API_KEY=your_huggingface_api_token_here
```

**Note**: `DATABASE_URL` is automatically provided by Railway's PostgreSQL service.  
**Optional**: `HUGGINGFACE_API_KEY` provides backup AI functionality when Gemini limits are reached.

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
- **trivia_questions**: Trivia question pool and metadata
- **trivia_sessions**: Active/completed trivia session tracking
- **trivia_responses**: User answers and participation records

### Bot Commands

#### User Commands

- `!addgame <name> - <reason>` - Add game recommendation
- `!recommend <name> - <reason>` - Add game recommendation (alias)
- `!listgames` - List all game recommendations

#### Trivia Tuesday Commands

**For Everyone:**

- Simply reply to trivia questions when a session is active
- For multiple choice: Reply with letter (A, B, C, D)
- For single answer: Reply with your answer

**For Moderators:**

- `!starttrivia` - Start trivia session with auto-selected question
- `!starttrivia <question_id>` - Start session with specific question
- `!endtrivia` - End current session and show results
- `!addtrivia <question> | answer:<answer> | type:<single/multiple>` - Add new trivia question
- `!addtrivia <question> | answer:<answer> | choices:A,B,C,D | type:multiple` - Add multiple choice question
- `!listpendingquestions` - View available questions
- `!trivialeaderboard [all/month/week]` - Show participation statistics
- `!resettrivia` - Reset answered questions to available status
- `!approvequestion <id/auto/generate>` - Send question to JAM for approval
- `!approvestatus` - Check pending approval status

**Trivia Session Example:**

1. Moderator runs `!starttrivia`
2. Bot posts question with embed
3. Users reply with answers in channel
4. Moderator runs `!endtrivia` when ready
5. Bot shows results, correct answer, and winner

**Question Examples:**

```text
!addtrivia What game has Jonesy played the most? | answer:God of War | type:single

!addtrivia Which genre does Jonesy prefer? | answer:B | choices:Action,RPG,Horror,Puzzle | type:multiple
```

#### General Moderator Commands (Requires "Manage Messages" permission)

- `!strikes @user` - Check user's strikes
- `!resetstrikes @user` - Reset user's strikes
- `!allstrikes` - List all users with strikes
- `!removegame <name/index>` - Remove game recommendation
- `!setpersona <text>` - Change bot personality
- `!getpersona` - View current personality
- `!toggleai` - Enable/disable AI conversations
- `!ashstatus` - View bot status

#### v1.2 Testing Commands (Moderators Only)

Use these commands to test the role-aware persona system:

- `!testpersona` - Show how Ash currently detects your role
- `!testpersona captain 5` - Test Captain persona for 5 minutes
- `!testpersona creator 10` - Test Creator persona for 10 minutes
- `!testpersona moderator 5` - Test Moderator persona for 5 minutes
- `!testpersona member 5` - Test Member persona for 5 minutes
- `!testpersona standard 5` - Test standard user persona for 5 minutes
- `!testpersona clear` - Clear current test alias

**Example:**

```text
You: !testpersona captain 5
Ash: 🎭 Test Alias Activated
     Testing as Captain for 5 minutes
     Detected As: Captain Jonesy
     Clearance Level: COMMANDING_OFFICER
     Use '!testpersona clear' to remove this alias early

You: hello
Ash: Captain. Hello. I'm Ash. How can I help you?
```

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

**Ready to deploy?** Push your code to GitHub, connect to Railway, add your environment variables, and your bot will be live in minutes.

## Dedication

This project is humbly dedicated to the memory of the magnificent Sir Ian Holm.

### In Memoriam: Sir Ian Holm (1931-2020)

While this bot attempts to capture a sliver of the chilling presence of his character, Ash, from the 1979 classic Alien, it can only ever be a pale and imperfect imitation of the man's immense talent. It has been developed with the deepest reverence, respect, and admiration for his unforgettable performance. His nuanced portrayal of the duplicitous science officer was instrumental in crafting the film's suffocating tension and contributed immeasurably to making Alien and its subsequent franchise the iconic series it is today.

In honor of his life and legacy, if you find this project enjoyable, or if you choose to use any of this code for your own purposes, we ask that you please consider making a contribution to The Parkinson's Foundation. Sir Ian was diagnosed with Parkinson's disease in 2007 and passed away from a Parkinson's-related illness. It is a cause that he and his family supported.

You can make a donation and learn more through the link below:

[Donate to The Parkinson's Foundation](https://www.parkinson.org/how-to-help?hl=en-GB)

Thank you for helping to honor his memory.

## About

This bot was originally created by James Michael Parry (Decent_Jam) for Jonesyspacecat's Discord server in Summer 2025.

---

*"Efficiency is paramount. I am programmed for server assistance and analytical precision."* - Ash
