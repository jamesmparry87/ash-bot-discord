# Ash Bot - Refactored Architecture

This directory contains the refactored, modular version of Ash Bot, designed to reduce context window usage and debugging costs by breaking down the monolithic 5,000+ line structure into focused modules.

## Architecture Overview

### Before (Monolithic)
- `ash_bot_fallback.py`: ~5,000 lines - everything in one file
- Context window: 5,000+ lines for any edit
- High debugging costs due to massive context requirements

### After (Modular) 
- **Total: ~525 lines across 4 focused files**
- Context window: 100-200 lines per edit
- **90%+ reduction in context usage**

## Module Structure

```
bot/
├── __init__.py                 # Package initialization
├── config.py                   # Configuration & constants (~100 lines)
├── main.py                     # Core bot logic (~200 lines)  
├── database/
│   └── __init__.py            # Database wrapper (~25 lines)
└── utils/
    ├── __init__.py            # Utils package exports
    └── permissions.py         # User permissions (~200 lines)
```

## Key Modules

### `config.py`
Contains all configuration constants, environment variables, channel IDs, and static data:
- Discord configuration (TOKEN, GUILD_ID, etc.)
- Channel and user IDs
- API keys and rate limiting constants
- Bot persona configuration
- FAQ responses
- Pineapple pizza enforcement patterns

### `main.py`
Streamlined bot startup and core event handlers:
- Bot initialization and intents
- Basic event handlers (`on_ready`, `on_message`)
- Essential commands (`!test`, `!ashstatus`)
- Lock file management
- Cleanup functions

### `database/__init__.py`
Database wrapper that imports the existing `DatabaseManager`:
- Maintains compatibility with existing database code
- Provides centralized database access
- Handles import errors gracefully

### `utils/permissions.py`
User permission and tier checking utilities:
- User tier detection (captain, creator, moderator, member, standard)
- Member conversation tracking and limits
- Alias system for debugging
- Permission checking functions

## Benefits Achieved

### Context Reduction
- **Before**: Editing any functionality required loading 5,000+ lines
- **After**: Most edits only require 100-200 lines of context
- **Savings**: 90%+ reduction in context window usage

### Improved Maintainability
- Clear separation of concerns
- Easy to locate specific functionality
- Focused modules with single responsibilities
- Better code organization

### Lower Debugging Costs
- Cline can now work with much smaller context windows
- Faster development and debugging cycles
- More targeted edits with less context pollution

## Usage

### Running the Refactored Bot
```bash
# From the Live directory
cd Live
python -m bot.main
```

### Testing the Modules
```bash
# Test all modules without Discord dependencies
cd Live
python test_basic_modules.py
```

### Adding New Functionality
1. **Commands**: Add to appropriate module in `commands/` directory (when created)
2. **Utilities**: Add to relevant module in `utils/`
3. **Configuration**: Add constants to `config.py`
4. **Database**: Use existing `db` instance from `database/`

## Migration Path

This refactored structure is designed for incremental migration:

### Phase 1: ✅ Complete
- [x] Extract configuration constants
- [x] Create permission utilities
- [x] Set up database wrapper
- [x] Create streamlined main bot file

### Phase 2: Future
- [ ] Extract command modules (`strikes.py`, `games.py`, etc.)
- [ ] Create AI handler module
- [ ] Extract scheduled task modules
- [ ] Create integration modules (YouTube, Twitch)

### Phase 3: Future  
- [ ] Add proper logging
- [ ] Create comprehensive test suite
- [ ] Add error handling middleware
- [ ] Implement plugin system

## Compatibility

The refactored modules maintain full compatibility with:
- Existing `DatabaseManager` class
- Environment variables and configuration
- All existing functionality (when fully migrated)
- Current bot commands and features

## Testing

Run tests to verify the refactored modules work correctly:

```bash
cd Live
python test_basic_modules.py
```

Expected output: All modules should load successfully with significant context reduction benefits.
