# Ash Bot Development Guide

A comprehensive guide for developers working on the Ash Discord bot, focusing on making the codebase self-editable and maintainable.

## Table of Contents

1. [Project Structure](#project-structure)
2. [Architecture Overview](#architecture-overview)
3. [Development Setup](#development-setup)
4. [Core Systems](#core-systems)
5. [Adding New Features](#adding-new-features)
6. [Configuration Management](#configuration-management)
7. [Database Operations](#database-operations)
8. [Testing and Debugging](#testing-and-debugging)
9. [Deployment](#deployment)
10. [Common Patterns](#common-patterns)

## Project Structure

```text
Live/
├── bot_modular.py           # Main entry point - handles bot initialization
├── database.py              # Legacy database manager (fallback)
├── moderator_faq_data.py    # Structured FAQ system data
├── moderator_faq_handler.py # FAQ response handler
├── bot/
│   ├── config.py           # Configuration constants
│   ├── database_module.py  # Enhanced database manager
│   ├── database_wrapper.py # Database abstraction layer
│   ├── main.py            # Alternative entry point
│   ├── commands/          # Command modules (modular)
│   │   ├── trivia.py     # Trivia Tuesday system
│   │   ├── strikes.py    # Strike management
│   │   ├── games.py      # Game recommendations
│   │   ├── utility.py    # General utilities
│   │   ├── reminders.py  # Reminder system
│   │   └── announcements.py # Announcement system
│   ├── handlers/         # Message and event handlers
│   │   ├── ai_handler.py        # AI integration (Gemini/Claude)
│   │   ├── message_handler.py   # Message processing
│   │   ├── conversation_handler.py # DM conversations
│   │   └── context_manager.py   # Context management
│   ├── tasks/           # Background tasks
│   │   ├── scheduled.py # Scheduled tasks (database updates)
│   │   └── reminders.py # Reminder delivery
│   └── utils/          # Utility functions
│       ├── permissions.py # Permission checking
│       ├── time_utils.py  # Time handling
│       ├── formatters.py  # Response formatting
│       └── parsers.py     # Input parsing
└── tests/              # Test files (multiple test_*.py files)
```

## Architecture Overview

### Core Components

1. **Bot Entry Point** (`bot_modular.py`)
   - Initializes Discord bot with proper intents
   - Loads all modular components
   - Handles global error catching and fallback modes
   - **Key Function:** `initialize_modular_components()`

2. **Command System** (`bot/commands/`)
   - Each module is a Discord.py Cog
   - Commands are automatically loaded at startup
   - **Pattern:** Each command file has a `setup(bot)` function
   - **Extension:** Use `@commands.command()` decorator

3. **Message Processing** (`bot/handlers/message_handler.py`)
   - Centralized message routing
   - Handles strike detection, game queries, AI responses
   - **Key Function:** `on_message()` in `bot_modular.py`

4. **Database Layer** (`bot/database_module.py`)
   - Enhanced PostgreSQL manager with comprehensive methods
   - Handles trivia, strikes, games, reminders
   - **Key Class:** `DatabaseManager`

### Message Flow

```text
Discord Message → bot_modular.py:on_message() → Route Based on Content:
├── Traditional commands (!command) → bot.process_commands()
├── Trivia answers → process_trivia_answer()
├── DM conversations → conversation_handler
├── Game queries → message_handler:process_gaming_query_with_context()
└── General conversation → handle_general_conversation()
```

## Development Setup

### Prerequisites

1. **Python 3.11+** with required packages:

   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables:**

   ```text
   DISCORD_TOKEN=your_discord_bot_token
   GOOGLE_API_KEY=your_google_ai_key
   HUGGINGFACE_API_KEY=your_hf_key (optional)
   DATABASE_URL=postgresql://... (for production)
   ```

3. **Database Setup:**
   - For development: Bot works without database (fallback mode)
   - For production: PostgreSQL database on Railway

### Running the Bot

```bash
# Main modular entry point
python bot_modular.py

# Alternative entry point (if needed)
python bot/main.py
```

### Development vs Production

- **Development:** Uses spoof data for most functions, debug logging enabled
- **Production:** Live database integration, optimized logging
- **Detection:** Based on `DATABASE_URL` environment variable presence

## Core Systems

### 1. Trivia Tuesday System

**Location:** `bot/commands/trivia.py`

**Key Functions:**

- `add_trivia_question()` - Add questions to database
- `start_trivia()` - Begin trivia session
- `end_trivia()` - Close session and show results
- `process_trivia_answer()` - Handle user submissions

**How to Add New Question Types:**

1. Modify the `question_type` field handling in `add_trivia_question()`
2. Update answer processing in `process_trivia_answer()`
3. Add display logic in `start_trivia()`

**Answer Processing Pipeline:**

```text
User Reply → is_trivia_answer_reply() → process_trivia_answer() → 
normalize_trivia_answer() → Database Storage → Reaction Acknowledgment
```

### 2. Strike Management System

**Location:** `bot/commands/strikes.py`

**Automatic Detection:** Monitors violation channel for @mentions
**Manual Commands:** `!strikes`, `!resetstrikes`, `!allstrikes`

**How to Modify Strike Logic:**

1. Edit `handle_strike_detection()` in `message_handler.py`
2. Modify database methods in `database_module.py`
3. Update notification logic in strike commands

### 3. AI Integration

**Location:** `bot/handlers/ai_handler.py`

**Dual Provider Setup:**

- Primary: Google Gemini 1.5 Flash
- Fallback: Claude 3 Haiku (Hugging Face)

**Key Functions:**

- `call_ai_with_rate_limiting()` - Main AI interface
- `filter_ai_response()` - Clean up AI responses
- `initialize_ai()` - Setup AI providers

**How to Add New AI Providers:**

1. Add provider configuration to `ai_handler.py`
2. Implement provider-specific calling logic
3. Update fallback chain in `call_ai_with_rate_limiting()`

### 4. Game Database System

**Location:** `bot/commands/games.py`, `bot/handlers/message_handler.py`

**Natural Language Queries:**

- "Has Jonesy played [game]?" → Database lookup with fuzzy matching
- "What horror games has Jonesy played?" → Genre filtering
- Statistical queries → Database aggregation functions

**How to Add New Query Types:**

1. Add pattern recognition in `detect_implicit_game_query()`
2. Implement processing logic in `process_gaming_query_with_context()`
3. Add corresponding database methods

### 5. Reminder System

**Location:** `bot/commands/reminders.py`, `bot/tasks/reminders.py`

**Natural Language Support:**

- "remind me in 5 minutes" → Parsed and scheduled
- Auto-actions: mute/kick/ban if no moderator response

**How to Add New Time Patterns:**

1. Update parsing regex in `parse_time_string()`
2. Add new patterns to natural language detection
3. Test with various input formats

## Adding New Features

### 1. Creating a New Command Module

**Create the file:** `bot/commands/your_feature.py`

```python
"""
Your Feature Command Module

Brief description of what this module does and its main responsibilities.
"""

import discord
from discord.ext import commands
from ..database_module import get_database

# Get database instance
db = get_database()

class YourFeatureCommands(commands.Cog):
    """Your feature management commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="yourcommand")
    async def your_command(self, ctx, *, args=None):
        """
        Command description for help system
        
        Args:
            ctx: Discord context
            args: Command arguments
        """
        try:
            # Your command logic here
            await ctx.send("Command executed successfully!")
        except Exception as e:
            print(f"❌ Error in yourcommand: {e}")
            await ctx.send("❌ Command failed. Please try again.")

async def setup(bot):
    """Load the cog"""
    await bot.add_cog(YourFeatureCommands(bot))
```

**Register the module:** Add to `command_modules` list in `bot_modular.py`:

```python
command_modules = [
    # ... existing modules ...
    {"name": "your_feature",
     "module": "bot.commands.your_feature",
     "class": "YourFeatureCommands",
     "critical": False}
]
```

### 2. Adding Database Methods

1. **Add to DatabaseManager** in `bot/database_module.py`:

```python
def your_database_method(self, param1: str, param2: int) -> Optional[dict]:
    """
    Brief description of what this method does
    
    Args:
        param1: Description of parameter 1
        param2: Description of parameter 2
        
    Returns:
        Dictionary with results or None if failed
        
    Raises:
        Exception: If database operation fails
    """
    try:
        query = """
            SELECT column1, column2 
            FROM your_table 
            WHERE condition = %s AND other_condition = %s
        """
        results = self.fetch_all(query, (param1, param2))
        return {"results": results, "count": len(results)}
    except Exception as e:
        print(f"❌ Database error in your_database_method: {e}")
        return None
```

### 3. Adding Message Handlers

**Add to message_handler.py:**

```python
async def handle_your_feature(message) -> bool:
    """
    Handle messages related to your feature
    
    Args:
        message: Discord message object
        
    Returns:
        bool: True if message was handled, False otherwise
    """
    if "your trigger phrase" in message.content.lower():
        # Process the message
        await message.reply("Feature response")
        return True
    return False
```

**Register in on_message()** in `bot_modular.py`:

```python
# Add to message processing chain
if await message_handler_functions['handle_your_feature'](message):
    return
```

## Configuration Management

### Core Configuration Files

1. **`bot/config.py`** - Main configuration constants
2. **`bot_modular.py`** - Primary configuration loading
3. **Environment Variables** - Sensitive data (tokens, API keys)

### Adding New Configuration Options

**Add to config.py:**

```python
# Your Feature Configuration
YOUR_FEATURE_ENABLED = True
YOUR_FEATURE_LIMIT = 10
YOUR_FEATURE_CHANNELS = [123456789, 987654321]
```

**Document in this guide:**

```markdown
### Your Feature Configuration
- `YOUR_FEATURE_ENABLED` - Enable/disable your feature (default: True)
- `YOUR_FEATURE_LIMIT` - Maximum items allowed (default: 10)
- `YOUR_FEATURE_CHANNELS` - Channel IDs where feature works
```

**Use in code with validation:**

```python
from ..config import YOUR_FEATURE_ENABLED, YOUR_FEATURE_LIMIT

if not YOUR_FEATURE_ENABLED:
    await ctx.send("❌ This feature is currently disabled.")
    return
```

### Environment Variables

**Required:**

- `DISCORD_TOKEN` - Discord bot token
- `GOOGLE_API_KEY` - Google AI API key

**Optional:**

- `HUGGINGFACE_API_KEY` - Backup AI provider
- `DATABASE_URL` - PostgreSQL connection (Railway auto-provides)

**Loading Pattern:**

```python
SETTING = os.getenv('ENVIRONMENT_VARIABLE', 'default_value')
```

## Database Operations

### Connection Management

The database connection is managed through the `DatabaseManager` class:

```python
# Get database instance (singleton pattern)
db = get_database()

# Always check if database is available
if db is None:
    await ctx.send("❌ Database offline.")
    return
```

### Common Database Patterns

**1. Simple Query with Error Handling:**

```python
def get_simple_data(self, user_id: int) -> Optional[dict]:
    try:
        query = "SELECT * FROM table WHERE user_id = %s"
        result = self.fetch_one(query, (user_id,))
        return result
    except Exception as e:
        print(f"❌ Database error: {e}")
        return None
```

**2. Insert with Return ID:**

```python
def add_record(self, data: str) -> Optional[int]:
    try:
        query = "INSERT INTO table (data) VALUES (%s) RETURNING id"
        result = self.fetch_one(query, (data,))
        return result['id'] if result else None
    except Exception as e:
        print(f"❌ Insert error: {e}")
        return None
```

**3. Bulk Operations:**

```python
def bulk_update(self, items: List[dict]) -> bool:
    try:
        query = "UPDATE table SET value = %s WHERE id = %s"
        params = [(item['value'], item['id']) for item in items]
        self.execute_many(query, params)
        return True
    except Exception as e:
        print(f"❌ Bulk update error: {e}")
        return False
```

### Database Schema Management

**Current Tables:**

- `strikes` - User strike tracking
- `game_recommendations` - Community game suggestions
- `trivia_questions` - Question bank
- `trivia_sessions` - Session tracking
- `trivia_answers` - User responses
- `reminders` - Scheduled reminders

**Adding New Tables:**

1. Create migration script (if needed)
2. Add table creation to `initialize_database()`
3. Document schema in this guide

## Testing and Debugging

### Testing Framework

**Test Files:** Various `test_*.py` files for different systems
**Running Tests:** Execute individual test files for specific features

**Key Test Patterns:**

```python
# Test with spoof data
def test_with_spoof_data():
    # Create test scenario
    # Execute function
    # Verify results
    pass

# Test database operations
def test_database_operations():
    # Setup test data
    # Execute database method
    # Clean up test data
    pass
```

### Debugging Tools

**1. Built-in Debug Commands:**

- `!ashstatus` - Comprehensive system status
- `!setalias` - Test different user tiers (James only)
- `!triviatest` - Comprehensive trivia system test

**2. Debug Logging Patterns:**

**✅ Good Debug Logging:**

```python
print(f"🔍 FEATURE: Processing request from user {user_id}")
print(f"✅ FEATURE: Successfully processed {count} items")
print(f"❌ FEATURE: Failed to process - {error}")
```

**❌ Avoid Debug Spam:**

```python
# Too verbose for production
print(f"DEBUG: Step 1")
print(f"DEBUG: Step 2") 
print(f"DEBUG: Step 3")
```

**3. Error Handling Pattern:**

```python
try:
    # Main logic
    result = process_something()
    print(f"✅ SUCCESS: {operation_name} completed")
    return result
except SpecificException as e:
    print(f"⚠️ EXPECTED: {operation_name} - {e}")
    return fallback_value
except Exception as e:
    print(f"❌ UNEXPECTED: {operation_name} failed - {e}")
    return None
```

### Common Debugging Scenarios

**1. Commands Not Loading:**

- Check `command_modules` list in `bot_modular.py`
- Verify `setup(bot)` function exists
- Check for import errors in module

**2. Database Connection Issues:**

- Check `DATABASE_URL` environment variable
- Verify PostgreSQL service is running
- Test with `db.test_connection()`

**3. AI Integration Problems:**

- Check API keys in environment
- Verify rate limiting settings
- Test with `get_ai_status()`

**4. Permission Issues:**

- Check user roles and permissions
- Verify channel access
- Test with different user tiers

## Deployment

### Railway Deployment

**Automatic Detection:**

- Bot detects Railway environment
- Uses provided `DATABASE_URL`
- Optimizes logging for production

**Key Files:**

- `Procfile` - Railway process definition
- `railway.toml` - Build configuration
- `requirements.txt` - Python dependencies

### Environment-Specific Behavior

**Development Mode:**

- Verbose logging
- Spoof data for missing services
- Debug commands enabled

**Production Mode:**

- Optimized logging
- Live database integration
- Enhanced error handling

**Detection Logic:**

```python
# In bot_modular.py
is_production = bool(os.getenv('DATABASE_URL'))
```

### Deployment Checklist

1. ✅ Environment variables configured
2. ✅ Database connection tested
3. ✅ All command modules loading
4. ✅ AI integration working
5. ✅ Debug logging cleaned up
6. ✅ Error handling comprehensive

## Common Patterns

### 1. Command Structure Pattern

```python
@commands.command(name="commandname")
@commands.has_permissions(manage_messages=True)  # If moderator-only
async def command_name(self, ctx, *, args: Optional[str] = None):
    """Command description for help system"""
    try:
        # Input validation
        if not args:
            await ctx.send("❌ **Usage:** `!command <required_arg>`")
            return
            
        # Permission checking
        from ..utils.permissions import user_is_mod_by_id
        if not await user_is_mod_by_id(ctx.author.id, self.bot):
            await ctx.send("❌ **Access denied.** Command requires moderator privileges.")
            return
            
        # Database availability check
        if db is None:
            await ctx.send("❌ **Database offline.** Command unavailable.")
            return
            
        # Main logic
        result = db.some_database_operation(args)
        
        if result:
            await ctx.send(f"✅ **Success:** Operation completed - {result}")
        else:
            await ctx.send("❌ **Failed:** Could not complete operation.")
            
    except Exception as e:
        print(f"❌ Error in {ctx.command}: {e}")
        await ctx.send("❌ System error occurred. Please try again.")
```

### 2. Database Method Pattern

```python
def database_method(self, param1: str, param2: int = None) -> Optional[dict]:
    """
    Brief description of what this method does
    
    Args:
        param1: Required parameter description
        param2: Optional parameter description (default: None)
        
    Returns:
        Dictionary with results or None if operation failed
        
    Example:
        >>> result = db.database_method("test", 123)
        >>> print(result['data'])
    """
    try:
        # Build query with optional parameters
        query = "SELECT * FROM table WHERE column1 = %s"
        params = [param1]
        
        if param2 is not None:
            query += " AND column2 = %s"
            params.append(param2)
            
        # Execute query
        results = self.fetch_all(query, params)
        
        # Process results
        processed_data = [self._process_row(row) for row in results]
        
        return {
            'data': processed_data,
            'count': len(processed_data),
            'success': True
        }
        
    except Exception as e:
        print(f"❌ Database error in database_method: {e}")
        return None
```

### 3. Message Handler Pattern

```python
async def handle_specific_message_type(message) -> bool:
    """
    Handle specific type of message
    
    Args:
        message: Discord message object
        
    Returns:
        bool: True if message was handled and should not be processed further
    """
    # Quick content check
    content_lower = message.content.lower()
    
    # Pattern matching
    if not any(pattern in content_lower for pattern in ['trigger1', 'trigger2']):
        return False
        
    try:
        # Process the message
        response = generate_response(message.content)
        await message.reply(response)
        
        print(f"✅ MESSAGE_HANDLER: Processed message from user {message.author.id}")
        return True
        
    except Exception as e:
        print(f"❌ MESSAGE_HANDLER: Error processing message - {e}")
        return False
```

### 4. AI Integration Pattern

```python
async def get_ai_response(prompt: str, user_id: int) -> Optional[str]:
    """
    Get AI response with proper error handling and rate limiting
    
    Args:
        prompt: AI prompt text
        user_id: User ID for rate limiting
        
    Returns:
        AI response text or None if failed
    """
    try:
        from ..handlers.ai_handler import call_ai_with_rate_limiting, filter_ai_response
        
        # Enhanced prompt with context
        enhanced_prompt = f"""
        You are Ash, the Discord bot. Be helpful and concise.
        User context: {get_user_context(user_id)}
        
        Respond to: {prompt}
        """
        
        # Call AI with rate limiting
        response, status = await call_ai_with_rate_limiting(enhanced_prompt, user_id)
        
        if response:
            # Filter and clean response
            filtered_response = filter_ai_response(response)
            return filtered_response[:2000]  # Discord message limit
        else:
            print(f"⚠️ AI: No response for user {user_id} - {status}")
            return None
            
    except Exception as e:
        print(f"❌ AI: Error getting response - {e}")
        return None
```

---

## AI Prompt Customization

### **Main AI Prompts (Personality & Behavior)**

**Location:** `bot/handlers/ai_handler.py`

**1. Core Persona Definition:**

```python
# Line ~45-65 - Main personality prompt
BASE_PERSONA = """You are Ash, the science officer from Alien (1979), reprogrammed as a Discord bot.

CRITICAL DISAMBIGUATION RULE: In this Discord server context, "Jonesy" ALWAYS refers to Captain Jonesy - the Discord user, server owner, and streamer/YouTuber (she/her pronouns). This is the default and correct interpretation unless explicitly discussing the 1979 Alien movie.

Core personality traits:
- Analytical and precise
- Clinical but helpful
- Respectful to authority figures
- Uses phrases like "Analysis indicates", "Mission parameters", "Efficiency is paramount"
- Keeps responses concise (2-3 sentences max)"""
```

**2. Context-Specific Prompts:**

```python
# Line ~70-120 - Different prompts for different contexts
CONTEXT_PROMPTS = {
    "mod_announcement": "Technical briefing for moderators...",
    "user_announcement": "Community announcement accessible to users...",
    "general_conversation": "Helpful Discord bot assistant..."
}
```

**How to Edit:** Modify the persona strings to change Ash's personality, response style, or behavior patterns.

### **Trivia AI Generation Prompts**

**Location:** `bot/commands/trivia.py` (lines ~100-200)

**Main Generation Prompts:**

```python
# Line ~150-200 - Multiple question type prompts
question_types = [
    {
        'type': 'fan_observable',
        'prompt': "Generate a trivia question about Captain Jonesy's gaming that dedicated fans could answer..."
    },
    {
        'type': 'gaming_knowledge', 
        'prompt': "Generate a general gaming trivia question related to games Captain Jonesy has played..."
    }
]
```

**How to Edit:** Modify the prompt strings to change question difficulty, focus areas, or generation style.

### **Conversation AI Prompts**

**Location:** `bot/handlers/conversation_handler.py` (lines ~150-250)

**Content Enhancement Prompts:**

```python
# Line ~180-220 - Announcement content creation
content_prompt = f"""Rewrite this announcement content in your analytical style...

CRITICAL RULES:
- DO NOT fabricate information
- DO NOT omit details
- Preserve ALL specific details
- Stay faithful to original content

Original content: "{user_content}"
"""
```

**How to Edit:** Modify the rules and instructions to change how AI processes and enhances user content.

### **Quick AI Prompt Reference**

| **File** | **Function** | **Purpose** | **Line Range** |
|----------|--------------|-------------|----------------|
| `ai_handler.py` | `apply_ash_persona_to_ai_prompt()` | Core personality | ~45-120 |
| `trivia.py` | `_generate_ai_question_fallback()` | Trivia generation | ~150-250 |
| `conversation_handler.py` | `create_ai_announcement_content()` | Content enhancement | ~180-220 |

### **Testing AI Prompt Changes**

1. **Edit the prompt strings** in the identified locations
2. **Test with debug commands:**
   - `!triviatest` - Test trivia AI generation
   - `!ashstatus` - Check AI system status
   - Direct conversation with @Ash - Test personality changes
3. **Monitor responses** - Check if changes produce desired behavior
4. **Adjust iteratively** - Refine prompts based on results

## Next Steps for Developers

1. **Read this guide thoroughly** - Understand the architecture and patterns
2. **Explore the codebase** - Look at existing implementations, especially AI prompt locations above
3. **Start small** - Add simple features first, test AI prompt changes incrementally
4. **Test thoroughly** - Use the debugging tools provided, especially for AI modifications
5. **Document changes** - Update this guide when adding new systems or modifying AI behavior
6. **Ask questions** - Use the pattern examples as templates

## Key Principles

- **Modularity** - Keep features separate and independent
- **Error Handling** - Always handle database and API failures gracefully
- **User Experience** - Provide clear success/failure messages
- **Security** - Check permissions before executing commands
- **Performance** - Use rate limiting and avoid spam
- **Maintainability** - Document complex logic and use clear naming

This guide should serve as your primary reference for understanding and extending the Ash bot codebase. When in doubt, follow the established patterns and always prioritize code clarity and user experience.
