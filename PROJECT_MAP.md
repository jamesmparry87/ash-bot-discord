# Discord Bot Project File Logic Map

## Quick Reference for AI Assistants

This document provides an at-a-glance reference for understanding which files to edit for specific tasks, eliminating the need to read through all files to understand the project structure.

## Core Architecture Files

### `Live/bot/main.py`
**Purpose**: Bot initialization, basic commands, event handlers
**Edit for**: 
- Adding new basic commands (!test, !ashstatus)
- Bot startup configuration
- Global event handlers (on_ready, on_message)
- Lock file management
- Bot token and intents setup

### `Live/bot/config.py`
**Purpose**: All configuration constants and static data
**Edit for**:
- Environment variables and channel IDs
- FAQ responses and bot persona
- Pineapple pizza enforcement patterns
- Static response templates
- Bot configuration constants

### `Live/bot/database/__init__.py`
**Purpose**: Database connection wrapper
**Edit for**:
- Database connection issues
- Adding new database methods (while maintaining compatibility)
- Database initialization
- Connection error handling

### `Live/bot/utils/permissions.py`
**Purpose**: User permission and tier detection
**Edit for**:
- User permission levels
- Communication tier logic
- Member conversation tracking
- User alias system for debugging
- Permission-based feature access

## Command Modules (Phase 2)

### `Live/bot/commands/strikes.py`
**Purpose**: Strike system management
**Edit for**:
- Adding/removing strikes
- Strike expiration logic
- Strike display and formatting
- Strike-related commands

### `Live/bot/commands/games.py`
**Purpose**: Game-related functionality
**Edit for**:
- Game commands and interactions
- Game state management
- Game statistics and tracking

### `Live/bot/commands/played_games.py`
**Purpose**: Played games tracking system
**Edit for**:
- Adding games to played list
- Game completion tracking
- Played games statistics
- User game history

### `Live/bot/commands/reminders.py`
**Purpose**: Reminder system commands
**Edit for**:
- Creating/editing reminders
- Reminder notification logic
- Reminder scheduling
- User reminder management

### `Live/bot/commands/trivia.py`
**Purpose**: Trivia game functionality
**Edit for**:
- Trivia questions and answers
- Trivia game logic
- Scoring and leaderboards
- Trivia categories

### `Live/bot/commands/moderation.py`
**Purpose**: Server moderation tools
**Edit for**:
- Moderation commands
- Auto-moderation rules
- User warnings and actions
- Content filtering

### `Live/bot/commands/utility.py`
**Purpose**: General utility commands
**Edit for**:
- Utility commands and helpers
- Server information commands
- User lookup functionality
- General bot utilities

## Handler Modules (Phase 3)

### `Live/bot/handlers/ai_handler.py`
**Purpose**: AI response processing and integration
**Edit for**:
- AI response generation
- OpenAI/Claude integration
- Response formatting and filtering
- AI conversation context

### `Live/bot/handlers/message_handler.py`
**Purpose**: Message event processing
**Edit for**:
- Message content analysis
- Automated responses
- Message filtering and processing
- Content-based triggers

### `Live/bot/handlers/conversation_handler.py`
**Purpose**: Conversation tracking and management
**Edit for**:
- Conversation state tracking
- Multi-message conversations
- Conversation history
- Context management

## Integration Modules (Phase 3)

### `Live/bot/integrations/youtube.py`
**Purpose**: YouTube API integration
**Edit for**:
- YouTube video information
- Channel monitoring
- Video notifications
- YouTube-related commands

### `Live/bot/integrations/twitch.py`
**Purpose**: Twitch integration
**Edit for**:
- Twitch stream monitoring
- Stream notifications
- Twitch user information
- Stream-related commands

## Task and Utility Modules (Phase 4)

### `Live/bot/tasks/scheduled.py`
**Purpose**: Background scheduled tasks
**Edit for**:
- Cron-like scheduled operations
- Recurring task management
- Task scheduling logic
- Background maintenance

### `Live/bot/tasks/reminders.py`
**Purpose**: Reminder task processing
**Edit for**:
- Reminder delivery logic
- Reminder timing and scheduling
- Reminder persistence
- Notification handling

### `Live/bot/utils/formatters.py`
**Purpose**: Text and data formatting utilities
**Edit for**:
- Message formatting functions
- Embed creation helpers
- Data presentation utilities
- Text processing functions

### `Live/bot/utils/parsers.py`
**Purpose**: Data parsing utilities
**Edit for**:
- Command argument parsing
- Data extraction functions
- Input validation
- Format conversion

### `Live/bot/utils/time_utils.py`
**Purpose**: Time handling and utilities
**Edit for**:
- Time zone handling
- Date/time formatting
- Duration calculations
- Time-based logic

## Legacy Files (Maintain but Don't Edit)

### `Live/ash_bot_fallback.py`
**Purpose**: Original monolithic bot (backup/reference)
**Status**: Keep for reference, use modular version for development

### `Live/database.py`
**Purpose**: Original database manager
**Status**: Wrapped by `bot/database/__init__.py`, maintain compatibility

## Testing Files

### `Live/test_basic_modules.py`
**Purpose**: Test modular architecture
**Edit for**: Testing individual module functionality

### `Live/test_refactored.py`
**Purpose**: Integration testing
**Edit for**: Testing complete bot functionality

## Task-to-File Quick Reference

| Task Type | Primary File | Secondary Files |
|-----------|-------------|----------------|
| Add FAQ response | `bot/config.py` | - |
| Fix permissions | `bot/utils/permissions.py` | - |
| Add slash command | Relevant `bot/commands/*.py` | `bot/main.py` (register) |
| Database issue | `bot/database/__init__.py` | `database.py` |
| AI responses | `bot/handlers/ai_handler.py` | `bot/config.py` |
| Message processing | `bot/handlers/message_handler.py` | - |
| YouTube features | `bot/integrations/youtube.py` | - |
| Twitch features | `bot/integrations/twitch.py` | - |
| Scheduled tasks | `bot/tasks/scheduled.py` | - |
| Reminders | `bot/commands/reminders.py` | `bot/tasks/reminders.py` |
| Text formatting | `bot/utils/formatters.py` | - |
| Bot startup | `bot/main.py` | `bot/__init__.py` |
| Configuration | `bot/config.py` | - |

## Development Workflow

1. **Small changes**: Edit specific module file
2. **New features**: Create in appropriate module, register in main.py
3. **Configuration**: Always use `bot/config.py`
4. **Testing**: Use `test_basic_modules.py` for individual modules
5. **Integration**: Use `test_refactored.py` for full bot testing

This map enables AI assistants to quickly identify the correct file to edit without reading through the entire codebase.
