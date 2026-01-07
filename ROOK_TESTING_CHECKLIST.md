# 🤖 Rook Bot Testing Checklist - Database Refactor Validation

> **Purpose:** Validate the database refactor on the Rook staging bot before deploying to production (Ash)
> **Duration:** 48 hours minimum
> **Branch:** `develop` (already pushed)

---

## ✅ Local Tests Completed

- ✅ **Structure Tests:** All 7 modules import correctly
- ✅ **Property Tests:** All 6 domain modules accessible
- ✅ **Lazy Loading:** All modules initialize on-demand
- ✅ **Method Tests:** All key methods present
- ✅ **Backward Compatibility:** Global `db` alias works
- ✅ **Pytest Suite:** 29/29 tests passed (102 seconds)

**Conclusion:** Code structure is valid. Ready for real-world testing on Rook.

## 🔄 Import Migration Completed (Jan 5, 2026)

- ✅ **bot_modular.py:** Updated to use `bot.database` with fallback to `bot.database_module`
- ✅ **11 Scripts/Tests:** All imports migrated from `database_module` to `bot.database`
- ✅ **Committed:** f442eae - "Migrate all imports to new modular database structure"
- ✅ **Pushed to develop:** Railway will auto-deploy Rook

**What's Different:** Bot will now use the NEW modular structure. Watch for "MODULAR" in startup logs!

---

## 📋 Rook Remote Testing Checklist

### Phase 1: Bot Startup & Health (15 minutes)

**Test:** Verify Rook starts successfully with new database structure

- [ ] **1.1 Deploy to Railway:** Push develop branch, trigger Rook deployment
- [ ] **1.2 Monitor Logs:** Check Railway logs for startup errors
- [ ] **1.3 Bot Online:** Verify Rook shows as "Online" in Discord
- [ ] **1.4 Connection Test:** Check for database connection errors in logs

**Expected Output:**
```
INFO:Live.bot.database.core:DatabaseManager initialized with connection pooling
INFO:discord.client:Logged in as: Rook#1234
✅ Bot database integration loaded successfully
```

**🚨 Red Flags:**
- Import errors mentioning `database.config`, `database.trivia`, etc.
- AttributeError about missing properties
- Database connection failures (existing issue, not related to refactor)

---

### Phase 2: Core Command Testing (30 minutes)

**Test:** Verify all major commands work with new database modules

#### 2.1 User Management Commands

- [ ] **Strikes System:**
  - Command: `!strikes @user`
  - Expected: Shows user strike count
  - Module: `db.users.get_user_strikes()`
  
- [ ] **Add Strike:**
  - Command: `!addstrike @user reason`
  - Expected: Adds strike, updates database
  - Module: `db.users.add_user_strike()`

- [ ] **Reminder System:**
  - Command: `!testreminder 1m Test reminder`
  - Expected: Creates reminder, fires after 1 minute
  - Module: `db.users.add_reminder()` + scheduled task

#### 2.2 Trivia System Commands

- [ ] **Add Trivia Question:**
  - Command: `!addtrivia`
  - Expected: Starts approval workflow
  - Module: `db.trivia.add_trivia_question()`

- [ ] **Start Trivia:**
  - Command: `!starttrivia`
  - Expected: Loads question, creates session
  - Module: `db.trivia.create_trivia_session()`

- [ ] **Submit Answer:**
  - Method: Reply to trivia question
  - Expected: Evaluates answer, updates session
  - Module: `db.trivia.submit_trivia_answer()`

- [ ] **Trivia Stats:**
  - Command: `!triviastats`
  - Expected: Shows leaderboard
  - Module: `db.trivia.get_trivia_leaderboard()`

#### 2.3 Games Database Commands

- [ ] **Add Played Game:**
  - Command: `!addgame "Game Name" 2024-01-01`
  - Expected: Adds to played_games table
  - Module: `db.games.add_played_game()`

- [ ] **List Games:**
  - Command: `!games` or `!listgames`
  - Expected: Shows all played games
  - Module: `db.games.get_all_played_games()`

- [ ] **Game Search:**
  - Command: `!game "God of War"`
  - Expected: Finds and displays game details
  - Module: `db.games.get_played_game()`

- [ ] **Update Game:**
  - Command: `!updategame <id> views=50000`
  - Expected: Updates game statistics
  - Module: `db.games.update_played_game()`

#### 2.4 Statistics Commands

- [ ] **Platform Stats:**
  - Command: `!platformstats`
  - Expected: Shows YouTube vs Twitch comparison
  - Module: `db.stats.get_platform_comparison_stats()`

- [ ] **Engagement Stats:**
  - Command: `!engagementstats`
  - Expected: Shows weekly engagement metrics
  - Module: `db.stats.get_engagement_timeline()`

- [ ] **AI Usage Tracking:**
  - Method: Trigger AI response (ask Ash a question)
  - Expected: AI usage gets logged
  - Module: `db.stats.increment_ai_request()`

#### 2.5 Config & Session Commands

- [ ] **Get Config:**
  - Command: `!getconfig <key>`
  - Expected: Retrieves config value
  - Module: `db.config.get_config_value()`

- [ ] **Set Config:**
  - Command: `!setconfig <key> <value>` (mod only)
  - Expected: Updates config
  - Module: `db.config.set_config_value()`

- [ ] **Weekly Announcement:**
  - Command: `!generateannouncement monday`
  - Expected: Creates announcement for approval
  - Module: `db.config.create_weekly_announcement()`

---

### Phase 3: Advanced Feature Testing (1 hour)

#### 3.1 Session Management

- [ ] **Trivia Approval Flow:**
  - Start: Submit trivia question
  - Expected: Creates approval session, tracks conversation
  - Module: `db.sessions.create_approval_session()`

- [ ] **Game Review Flow:**
  - Start: Trigger game title extraction
  - Expected: Creates review session for manual approval
  - Module: `db.sessions.create_game_review_session()`

- [ ] **Session Expiration:**
  - Wait: Let session expire (default 1 hour)
  - Expected: Old sessions marked inactive
  - Module: `db.sessions.cleanup_expired_sessions()`

#### 3.2 Concurrent Operations

- [ ] **Multiple Trivia Answers:**
  - Test: Have 3+ users answer simultaneously
  - Expected: First correct answer wins, no race conditions
  - Stress Test: Database connection handling

- [ ] **Bulk Game Updates:**
  - Test: Run bulk Twitch/YouTube sync script
  - Expected: Updates complete without errors
  - Module: `db.games.bulk_update_*()` methods

#### 3.3 Natural Language AI Integration

- [ ] **Game Stats Query:**
  - Message: "Hey Ash, how many views does God of War have?"
  - Expected: Triggers stats lookup, responds in Ash voice
  - Module: AI handler → `db.games.get_played_game()`

- [ ] **Trivia Question Query:**
  - Message: "Ash, how many trivia questions do we have?"
  - Expected: Queries trivia database, responds
  - Module: AI handler → `db.trivia.get_trivia_stats()`

---

### Phase 4: Error Handling & Edge Cases (30 minutes)

#### 4.1 Database Connection Issues

- [ ] **Connection Loss Simulation:**
  - Method: Restart Railway database (if safe)
  - Expected: Bot reconnects gracefully, no crashes
  - Module: `db.get_connection()` retry logic

- [ ] **Query Failures:**
  - Method: Intentionally malformed command
  - Expected: Graceful error, no bot crash
  - Module: Error handling in all modules

#### 4.2 Data Validation

- [ ] **Invalid Inputs:**
  - Test: `!addgame "" invalid-date`
  - Expected: Validation error, helpful message
  - Module: Input validation in `db.games`

- [ ] **SQL Injection Attempts:**
  - Test: `!game "'; DROP TABLE --"`
  - Expected: Sanitized, safe query
  - Module: `db._validate_column_name()`

---

### Phase 5: Performance Monitoring (48 hours)

#### 5.1 Response Times

Monitor command execution times over 48 hours:

- [ ] **Baseline Commands:** < 1 second response
  - `!strikes`, `!games`, `!triviastats`

- [ ] **Database-Heavy Commands:** < 3 seconds
  - `!listgames` (100+ games)
  - `!platformstats` (aggregation queries)

- [ ] **AI + Database:** < 5 seconds
  - Natural language queries requiring DB lookups

**🚨 Red Flags:**
- Commands taking >10 seconds consistently
- Timeout errors
- Memory leaks (check Railway metrics)

#### 5.2 Error Monitoring

Track errors in Railway logs:

- [ ] **No Import Errors:** After 24 hours
- [ ] **No AttributeErrors:** Related to db modules
- [ ] **No Connection Pool Issues:** Database connections managed properly

---

### Phase 6: Backward Compatibility Validation (24 hours)

**Test:** Ensure old code paths still work during migration period

- [ ] **Legacy database_module.py:** Still importable (if kept as facade)
- [ ] **Old Import Style:** `from database_module import db` works
- [ ] **Mixed Usage:** Old and new code can coexist

---

## 📊 Success Criteria

After 48 hours on Rook, the refactor is **ready for production** if:

✅ **Zero** module import errors
✅ **Zero** attribute errors related to new structure
✅ **All** commands work identically to before
✅ **Performance** matches or exceeds previous version
✅ **No regressions** in existing features
✅ **Logs clean** of database module errors

---

## 🔴 Rollback Plan

If critical issues found:

1. **Immediate:** Revert develop branch to pre-refactor commit
2. **Notify:** Document issue in GitHub issue tracker
3. **Fix:** Address root cause locally
4. **Re-test:** Run through checklist again
5. **Re-deploy:** Only after local validation passes

**Rollback Command:**
```bash
git revert 8f17fd7  # Revert merge commit
git revert 2a92741  # Revert Phase 3
git revert 60582f7  # Revert Phase 2
git revert f75cde3  # Revert Phase 1
git push origin develop
```

---

## 📝 Testing Log Template

Use this to track your testing:

```
## Rook Testing Session - [DATE]

### Environment
- Branch: develop
- Commit: 8f17fd7
- Deployment: Railway
- Tester: James

### Phase 1: Startup ✅ / ❌
- [TIME] Deployed to Railway
- [TIME] Bot came online
- [TIME] Checked logs - [NOTES]

### Phase 2: Commands
- [TIME] !strikes - ✅ / ❌ - [NOTES]
- [TIME] !starttrivia - ✅ / ❌ - [NOTES]
- [TIME] !games - ✅ / ❌ - [NOTES]
...

### Issues Found
1. [Description] - [Severity: Critical/High/Medium/Low]
2. ...

### Conclusion
Ready for Production: YES / NO / NEEDS MORE TIME
Reason: ...
```

---

## 🎯 Next Steps After Successful Testing

1. **Merge to stable:** `git checkout stable && git merge develop`
2. **Deploy to Ash:** Merge stable → main
3. **Monitor Ash:** Watch production for 24 hours
4. **Document:** Update project documentation
5. **Celebrate:** Database refactor complete! 🎉
6. **Start Priority 2:** Now unblocked for Data Integrity work

---

**Estimated Total Testing Time:** 4-6 hours active + 48 hours monitoring
**Recommended Tester:** James (maintainer) or designated mod with database knowledge
