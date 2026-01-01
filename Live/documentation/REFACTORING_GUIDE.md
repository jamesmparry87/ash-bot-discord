# DATABASE MODULE REFACTORING GUIDE

> **Status:** In Progress (Priority 1.5)  
> **Timeline:** Q1 2026 (2 weeks estimated)  
> **Risk Level:** Low (backward compatibility maintained)

## Table of Contents
1. [Overview](#overview)
2. [Why Refactor Now](#why-refactor-now)
3. [Refactoring Strategy](#refactoring-strategy)
4. [Implementation Steps](#implementation-steps)
5. [Testing Protocol](#testing-protocol)
6. [Deployment Process](#deployment-process)
7. [Troubleshooting](#troubleshooting)

---

## Overview

**Current State:**
- `Live/bot/database_module.py`: **3,076 lines** (monolithic)
- All database operations in single file
- Difficult to navigate, test, and extend

**Target State:**
```
Live/bot/
├── database_module.py           # Backward compatibility facade (~200 lines)
└── database/
    ├── __init__.py              # Module exports
    ├── core.py                  # Connection management (~200 lines)
    ├── games.py                 # played_games operations (~800 lines)
    ├── trivia.py                # Trivia system (~600 lines)
    ├── users.py                 # Users, strikes, reminders (~300 lines)
    ├── stats.py                 # Analytics & metrics (~200 lines)
    └── config.py                # Bot configuration (~100 lines)
```

**Benefits:**
- ✅ Each module < 800 lines (vs. 3000+)
- ✅ Easier to find and modify specific functions
- ✅ Better testing isolation
- ✅ Reduced merge conflicts
- ✅ Foundation for Priorities 2, 6, 7, 8

---

## Why Refactor Now

### Strategic Dependencies

**Priority 2 (Data Integrity)** requires:
- Schema changes to `played_games` table
- New normalization logic
- Enhanced data validation

**Priority 6 (Twitch Title Parsing)** requires:
- New `title_game_mappings` table
- Pattern learning system
- Database-first matching logic

**Priority 7 (Real-Time Stats)** requires:
- New columns: `last_stats_query`, `query_count`
- Query-driven update logic
- Caching mechanisms

**Priority 8 (Platform Improvements)** requires:
- New column: `platform_type`
- Cross-platform comparison queries
- Analytics enhancements

**The Problem:** Building these features on the current monolithic structure will:
- Make the file even larger (4000+ lines)
- Increase merge conflicts
- Make future refactoring exponentially harder
- Cement technical debt

**The Solution:** Refactor NOW before adding new features.

---

## Refactoring Strategy

### Phase 1: Modular Structure Creation

**Approach:** Split by domain responsibility, not by database tables.

#### `core.py` - Foundation Layer
**Responsibilities:**
- Database connection management
- Base `DatabaseManager` class
- Connection pooling/retry logic
- SQL injection prevention helpers

**Key Methods:**
```python
- get_connection()
- init_database()
- _validate_column_name()
- _validate_order_direction()
- close()
```

#### `games.py` - Game Database Operations
**Responsibilities:**
- ALL `played_games` table operations
- Game search/lookup (canonical + fuzzy)
- Platform detection (YouTube/Twitch)
- Engagement metrics
- Series/genre queries

**Key Methods:**
```python
- add_played_game()
- get_played_game()
- update_played_game()
- get_all_played_games()
- search_played_games()
- get_games_by_genre()
- get_games_by_playtime()
- bulk_import_played_games()
- deduplicate_played_games()
```

#### `trivia.py` - Trivia System
**Responsibilities:**
- Trivia questions management
- Session lifecycle
- Answer submission & evaluation
- Leaderboards

**Key Methods:**
```python
- add_trivia_question()
- get_next_trivia_question()
- create_trivia_session()
- get_active_trivia_session()
- submit_trivia_answer()
- complete_trivia_session()
- get_trivia_leaderboard()
```

#### `users.py` - User Management
**Responsibilities:**
- Strike system
- User reminders
- Game recommendations

**Key Methods:**
```python
- get_user_strikes()
- add_user_strike()
- add_reminder()
- get_due_reminders()
- add_game_recommendation()
```

#### `stats.py` - Analytics & Metrics
**Responsibilities:**
- Platform comparison stats
- Engagement metrics
- AI usage tracking
- Analytics queries

**Key Methods:**
```python
- get_platform_comparison_stats()
- get_engagement_metrics()
- get_ranking_context()
- load_ai_usage_stats()
- save_ai_usage_stats()
```

#### `config.py` - Bot Configuration
**Responsibilities:**
- Key-value configuration storage
- Weekly announcements
- Bot state management

**Key Methods:**
```python
- get_config_value()
- set_config_value()
- create_weekly_announcement()
- get_announcement_by_day()
```

### Phase 2: Backward Compatibility Facade

**Critical:** Existing code must continue to work without changes.

**Implementation:**
```python
# Live/bot/database_module.py (new facade)

from .database.core import DatabaseManager as _CoreDatabaseManager
from .database.games import GameDatabase
from .database.trivia import TriviaDatabase
from .database.users import UserDatabase
from .database.stats import StatsDatabase
from .database.config import ConfigDatabase

class DatabaseManager(_CoreDatabaseManager):
    """
    Backward-compatible facade for the modular database system.
    
    All existing code continues to work. New code should use
    the modular system directly for better organization.
    """
    
    def __init__(self):
        super().__init__()
        
        # Initialize domain-specific databases
        self._games = GameDatabase(self)
        self._trivia = TriviaDatabase(self)
        self._users = UserDatabase(self)
        self._stats = StatsDatabase(self)
        self._config = ConfigDatabase(self)
    
    # ===== GAME METHODS (proxy to games.py) =====
    
    def add_played_game(self, *args, **kwargs):
        """Add a played game (backward compatible)"""
        return self._games.add_played_game(*args, **kwargs)
    
    def get_played_game(self, name):
        """Get a played game by name (backward compatible)"""
        return self._games.get_played_game(name)
    
    def update_played_game(self, game_id, **kwargs):
        """Update a played game (backward compatible)"""
        return self._games.update_played_game(game_id, **kwargs)
    
    # ... continue for all methods ...
    
    # ===== TRIVIA METHODS (proxy to trivia.py) =====
    
    def add_trivia_question(self, *args, **kwargs):
        """Add a trivia question (backward compatible)"""
        return self._trivia.add_trivia_question(*args, **kwargs)
    
    # ... etc ...
```

**Key Principles:**
1. **Zero Breaking Changes:** All existing function signatures remain identical
2. **Lazy Loading:** Domain modules only load when needed
3. **Transparent Proxying:** Methods delegate to appropriate domain module
4. **Future Flexibility:** Easy to migrate to direct imports later

### Phase 3: Testing & Validation

**Testing Strategy:**
1. **Unit Tests:** Ensure each module works independently
2. **Integration Tests:** Verify facade proxying works correctly
3. **Regression Tests:** Run full pytest suite
4. **Staging Deployment:** Deploy to Rook bot for real-world testing

---

## Implementation Steps

### Week 1: Module Creation & Facade

#### Step 1: Create Directory Structure
```bash
cd Live/bot
mkdir database
touch database/__init__.py
touch database/core.py
touch database/games.py
touch database/trivia.py
touch database/users.py
touch database/stats.py
touch database/config.py
```

#### Step 2: Implement `core.py`
**Extract from `database_module.py`:**
- `__init__()` method
- `get_connection()` method
- `init_database()` method
- All SQL validation helpers
- `close()` method

**Add to `core.py`:**
```python
class DatabaseManager:
    """Base database manager with connection handling"""
    
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        self.connection = None
        if self.database_url:
            self.init_database()
    
    def get_connection(self):
        # ... existing implementation ...
    
    def init_database(self):
        # ... existing implementation ...
```

#### Step 3: Implement `games.py`
**Extract from `database_module.py`:**
- All methods dealing with `played_games` table
- Fuzzy search helpers
- Platform detection methods
- Series/genre queries

**Structure:**
```python
class GameDatabase:
    """Handles all played_games table operations"""
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    def add_played_game(self, ...):
        conn = self.db.get_connection()
        # ... implementation ...
```

#### Step 4: Implement `trivia.py`
**Extract from `database_module.py`:**
- All methods dealing with trivia tables
- Session management
- Answer evaluation

#### Step 5: Implement `users.py`, `stats.py`, `config.py`
**Follow same pattern for remaining domains**

#### Step 6: Create Backward Compatibility Facade
**Modify `database_module.py`:**
- Keep all method signatures
- Add imports from new modules
- Implement proxy methods

#### Step 7: Update `database/__init__.py`
```python
"""
Modular database system for Ash Bot.

Usage:
    # Backward compatible (legacy)
    from bot.database_module import DatabaseManager
    db = DatabaseManager()
    
    # Direct module access (new)
    from bot.database.games import GameDatabase
    from bot.database_module import get_database
    
    db = get_database()
    games = GameDatabase(db)
"""

from .core import DatabaseManager
from .games import GameDatabase
from .trivia import TriviaDatabase
from .users import UserDatabase
from .stats import StatsDatabase
from .config import ConfigDatabase

__all__ = [
    'DatabaseManager',
    'GameDatabase',
    'TriviaDatabase',
    'UserDatabase',
    'StatsDatabase',
    'ConfigDatabase'
]
```

### Week 2: Testing & Deployment

#### Step 8: Run Unit Tests
```bash
cd Live
python -m pytest tests/test_database.py -v
```

**Expected Result:** All tests pass with no changes to test code.

#### Step 9: Run Integration Tests
```bash
python -m pytest tests/test_commands.py -v
python -m pytest tests/test_functional_core.py -v
```

**Expected Result:** All existing functionality works unchanged.

#### Step 10: Deploy to Rook (Staging)
```bash
git checkout develop
git add Live/bot/database/
git add Live/bot/database_module.py
git commit -m "Refactor: Split database_module into modular structure"
git push origin develop
```

**Monitor Rook for 48 hours:**
- ✅ No errors in logs
- ✅ All commands work normally
- ✅ Trivia system functions correctly
- ✅ Database operations complete successfully

#### Step 11: Merge to Stable
```bash
git checkout stable
git merge develop
git push origin stable
```

#### Step 12: Deploy to Production (Ash)
```bash
git checkout main
git merge stable
git push origin main
```

---

## Testing Protocol

### Pre-Deployment Testing Checklist

**Unit Tests:**
- [ ] `test_database.py` passes (100% compatibility)
- [ ] `test_commands.py` passes (command functionality)
- [ ] `test_trivia_response_simple.py` passes (trivia system)
- [ ] `test_functional_core.py` passes (core features)

**Manual Testing on Rook:**
- [ ] `!game add` - Add new game successfully
- [ ] `!game search` - Search games by name
- [ ] `!trivia start` - Start trivia session
- [ ] `!trivia submit` - Submit answer
- [ ] `!remind` - Create reminder
- [ ] `!strikes @user` - Check strikes
- [ ] AI conversation - Natural language responses

**Performance Testing:**
- [ ] Database query times unchanged
- [ ] Memory usage within normal range
- [ ] No connection pool exhaustion

**Error Handling:**
- [ ] Connection failures handled gracefully
- [ ] Invalid data doesn't crash bot
- [ ] Logging remains consistent

---

## Deployment Process

### Staging Deployment (Rook Bot)

**1. Pre-Deployment:**
```bash
# Ensure develop branch is up-to-date
git checkout develop
git pull origin develop

# Create feature branch
git checkout -b refactor/database-modular
```

**2. Implementation:**
```bash
# Make changes following implementation steps
# Test locally with pytest
python -m pytest tests/ -v
```

**3. Commit & Push:**
```bash
git add Live/bot/database/
git add Live/bot/database_module.py
git add Live/documentation/
git commit -m "Refactor: Modular database structure with backward compatibility"
git push origin refactor/database-modular
```

**4. Merge to Develop:**
```bash
git checkout develop
git merge refactor/database-modular
git push origin develop
```

**5. Railway Auto-Deploys to Rook:**
- Railway detects push to `develop` branch
- Automatically deploys to Rook bot instance
- Monitor Railway logs for deployment success

**6. Monitoring Period (48 hours):**
- Check Railway logs for errors
- Test all commands in Discord
- Monitor database performance metrics
- Verify no user-reported issues

### Production Deployment (Ash Bot)

**Only proceed if Rook testing is successful.**

**1. Merge to Stable:**
```bash
git checkout stable
git merge develop
git push origin stable
```

**2. Final Testing:**
- Quick smoke test on Rook
- Verify all critical paths

**3. Merge to Main:**
```bash
git checkout main
git merge stable
git push origin main
```

**4. Railway Auto-Deploys to Ash:**
- Railway detects push to `main` branch
- Automatically deploys to Ash bot instance
- Monitor deployment logs

**5. Post-Deployment Verification:**
- [ ] Ash bot comes online successfully
- [ ] Test key commands (!game, !trivia, !help)
- [ ] Check error logs for issues
- [ ] Monitor for 24 hours

---

## Troubleshooting

### Common Issues & Solutions

#### Issue: Import Errors After Refactoring
**Symptom:** `ModuleNotFoundError: No module named 'bot.database'`

**Solution:**
```bash
# Ensure __init__.py exists
touch Live/bot/database/__init__.py

# Verify Python path includes parent directory
export PYTHONPATH="${PYTHONPATH}:/path/to/discord/Live"
```

#### Issue: Circular Import Dependencies
**Symptom:** `ImportError: cannot import name 'DatabaseManager' from partially initialized module`

**Solution:**
- Ensure `core.py` has no dependencies on other database modules
- Use lazy imports within methods if needed
- Verify import order in `__init__.py`

#### Issue: Method Signature Mismatch
**Symptom:** `TypeError: missing required positional argument`

**Solution:**
- Check facade proxying in `database_module.py`
- Ensure all `*args, **kwargs` are forwarded correctly
- Verify method signatures match exactly

#### Issue: Connection Sharing Between Modules
**Symptom:** `DatabaseManager has no attribute 'connection'`

**Solution:**
```python
# In domain modules, always use db.get_connection()
conn = self.db.get_connection()

# Never access self.db.connection directly
```

#### Issue: Test Failures After Refactoring
**Symptom:** Tests that worked before now fail

**Solution:**
1. Check if tests import from correct location
2. Verify backward compatibility facade is complete
3. Run tests individually to isolate issue:
   ```bash
   python -m pytest tests/test_database.py::TestClass::test_method -v
   ```

---

## Rollback Procedure

**If critical issues arise in production:**

### Immediate Rollback (< 5 minutes)

**1. Revert to Previous Commit:**
```bash
git checkout main
git revert HEAD
git push origin main
```

**2. Railway Auto-Redeploys:**
- Previous version automatically deployed
- Bot restores to working state

### Manual Rollback (if git revert fails)

**1. Identify Last Working Commit:**
```bash
git log --oneline -n 10
```

**2. Hard Reset:**
```bash
git checkout main
git reset --hard <last-working-commit-hash>
git push --force origin main
```

**3. Notify Team:**
- Post in Discord mod channel
- Document issue in GitHub
- Schedule post-mortem

---

## Post-Refactoring Cleanup

**After 2-4 weeks of stable operation:**

### Phase 4: Remove Facade Layer

**Goal:** Migrate all code to use modular imports directly.

**1. Update Import Statements:**
```python
# Old (facade)
from bot.database_module import DatabaseManager
db = DatabaseManager()
game = db.get_played_game("God of War")

# New (direct)
from bot.database_module import get_database
from bot.database.games import GameDatabase

db = get_database()
games = GameDatabase(db)
game = games.get_played_game("God of War")
```

**2. Remove Proxy Methods:**
- Once all imports updated, remove facade from `database_module.py`
- Keep only `get_database()` singleton function

**3. Final Testing:**
- Run full test suite
- Deploy to Rook
- Monitor for 48 hours
- Deploy to production

---

## Success Metrics

### Quantitative Metrics

- **Code Organization:** No module > 800 lines ✅
- **Test Coverage:** Maintain 100% test pass rate ✅
- **Performance:** No regression in query times ✅
- **Stability:** Zero production incidents related to refactoring ✅

### Qualitative Metrics

- **Developer Velocity:** Easier to find and modify code ✅
- **Merge Conflicts:** Reduced frequency ✅
- **Onboarding:** New contributors can navigate codebase easier ✅
- **Foundation:** Ready for Priorities 2, 6, 7, 8 implementation ✅

---

## Next Steps After Refactoring

**With modular database in place, proceed with:**

1. **Priority 2:** Data Integrity & Game Knowledge
   - Schema normalization (easier with `games.py` isolated)
   - Enhanced validation logic
   - IGDB resync implementation

2. **Priority 6:** Twitch Title Parsing
   - New `title_game_mappings` table (add to `games.py`)
   - Pattern learning system
   - Fuzzy matching improvements

3. **Priority 7:** Real-Time Engagement Stats
   - New columns in `played_games` (modify `games.py`)
   - Query-driven cache (add to `stats.py`)
   - Response formatting

4. **Priority 8:** Platform Improvements
   - Platform type detection (enhance `games.py`)
   - Cross-platform analytics (expand `stats.py`)
   - Engagement metrics

---

## Questions?

For refactoring questions or implementation assistance:
1. Review this guide thoroughly
2. Check `Live/documentation/SCHEMA.md` for database structure
3. Consult with James (maintainer) or AI assistants
4. Test changes on `develop` branch first
5. Deploy to Rook before production

**Remember:** Backward compatibility is critical. No existing code should break.

---

**Document Version History:**
- v1.0 (1 Jan 2026) - Initial refactoring guide
