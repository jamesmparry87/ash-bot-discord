# Ash Bot - Testing Strategy

## Philosophy

**Goal**: Catch deployment-breaking issues before go-live, not validate every fix ever made.

**Test Focus**: Complete user workflows and critical functionality paths.

**Non-Goals**: 
- Testing one-off fixes (those are verified once and removed)
- Testing features requiring external credentials unavailable in CI
- Testing internal implementation details that don't affect users

---

## Test Suite Organization

### 1. **test_functional_core.py** - PRIMARY TEST FILE ⭐

**Purpose**: High-level functional validation of all critical bot features  
**Run Frequency**: Every CI build  
**Coverage**: Complete user-facing workflows

**Test Categories**:
- ✅ **Trivia System** - Question generation, answer options, validation
- ✅ **Reminder System** - NLP parsing, storage, retrieval
- ✅ **Gaming Database** - Query completeness, statistical accuracy
- ✅ **AI Responses** - Filtering, context detection
- ✅ **Command System** - Critical commands registered and working
- ✅ **Announcements** - Workflow doesn't crash
- ✅ **Data Quality** - Normalization, validation
- ✅ **Deployment Readiness** - Module imports, database connection

### 2. **test_database.py** - DATABASE VALIDATION

**Purpose**: Core database operations work correctly  
**Run Frequency**: Every CI build  
**Coverage**: CRUD operations, data integrity

**Keep**: Core database tests  
**Remove**: Migration tests, one-off restructuring tests

### 3. **test_commands.py** - COMMAND INTEGRATION

**Purpose**: Commands parse and execute correctly  
**Run Frequency**: Every CI build  
**Coverage**: Command dispatch, argument parsing

**Keep**: Core command tests  
**Remove**: Fix validation tests

### 4. **test_twitch_data_quality.py** - DATA EXTRACTION

**Purpose**: Game name extraction works correctly  
**Run Frequency**: Every CI build  
**Coverage**: Title parsing, data normalization

**Keep**: Extraction logic tests  
**Remove**: IGDB-dependent tests (already done)

### 5. **test_ai_integration.py** - AI FUNCTIONALITY

**Purpose**: AI response generation works  
**Run Frequency**: Every CI build  
**Coverage**: Response filtering, mock validation

**Keep**: AI filtering tests  
**Remove**: Deprecated backup AI tests

---

## Tests to REMOVE (Redundant/One-Off)

### High Priority Removals:

1. **test_all_fixes.py** - Generic catch-all, no specific purpose
2. **test_database_restructuring.py** - One-off migration test
3. **test_sequence_repair.py** - One-off fix validation
4. **testai.py** - Debug file
5. **test_game_extraction_fixes.py** - One-off fix (covered in data_quality)

### Reminder Fix Tests (Consolidate to 1 file):
- ❌ test_reminder_bugs_fixed.py
- ❌ test_reminder_command_execution.py  
- ❌ test_reminder_fix_validation.py
- ❌ test_reminder_fixes.py
- ❌ test_reminder_integration_fix.py
- ❌ test_reminder_parsing_fixes.py
- ✅ **KEEP**: Core reminder tests in test_functional_core.py

### Trivia Fix Tests (Consolidate to 1 file):
- ❌ test_complete_trivia_fix_validation.py
- ❌ test_trivia_approval_fix.py
- ❌ test_trivia_complete_fix.py
- ❌ test_trivia_fixes_verification.py
- ❌ test_trivia_fixes.py
- ❌ test_trivia_interference_analysis.py
- ❌ test_trivia_session_fix.py
- ❌ test_trivia_sql_fix_validation.py
- ❌ test_trivia_debug.py
- ✅ **KEEP**: Core trivia tests in test_functional_core.py
- ✅ **KEEP**: test_trivia_validation.py (if it has ongoing validation)

### Command/FAQ Fix Tests:
- ❌ test_comprehensive_command_faq_conflicts.py - One-off
- ❌ test_comprehensive_command_priority_fix.py - One-off
- ❌ test_natural_language_command_priority.py - One-off
- ❌ test_faq_fix.py - One-off

### AI Fix Tests:
- ❌ test_ai_fixes.py - Generic fixes
- ❌ test_ai_disambiguation.py - Covered in functional_core
- ❌ test_ai_permissions_fix.py - One-off
- ❌ test_jonesy_disambiguation.py - Covered in functional_core

### Announcement Tests:
- ❌ test_emergency_approval.py - One-off
- ❌ test_manual_approval.py - One-off
- ✅ **KEEP**: test_announcement_system_e2e.py (if it's comprehensive)

### Other Cleanup:
- ❌ test_mod_channel_fixes.py - One-off
- ❌ test_rate_limiting_fixes.py - One-off
- ❌ test_privacy_fixes.py - One-off
- ❌ test_staging_validation.py - Should run in staging, not CI

---

## Tests to KEEP

### Core Functionality (Critical):
✅ **test_functional_core.py** - NEW primary test file  
✅ **test_database.py** - Database operations  
✅ **test_commands.py** - Command dispatch  
✅ **test_ai_integration.py** - AI responses  
✅ **test_twitch_data_quality.py** - Data extraction  
✅ **test_config.py** - Configuration validation  

### Specialized Systems (If comprehensive):
✅ **test_context_system.py** - Context management  
✅ **test_dm_conversations.py** - DM workflow  
✅ **test_reply_based_trivia_system.py** - Trivia mechanics  
✅ **test_complete_trivia_workflow.py** - End-to-end trivia  
✅ **test_announcement_system_e2e.py** - Announcement workflow  

### Integration (Modular):
✅ **test_modular_commands.py** - Module loading  
✅ **test_modular_integration.py** - Module integration  
✅ **test_basic_modules.py** - Module imports  

---

## CI Workflow Configuration

### Primary Test Run:
```yaml
- name: Run Core Functional Tests (CRITICAL)
  run: |
    python3 -m pytest Live/tests/test_functional_core.py -v --tb=short
```

### Full Test Suite:
```yaml
- name: Run All Tests
  run: |
    python3 -m pytest Live/tests/ -v \
      --ignore=Live/tests/test_igdb_live_integration.py \
      --ignore=Live/tests/test_staging_validation.py \
      -k "not test_youtube and not test_twitch"
```

---

## Test Failure Response

### When a test fails:

1. **Functional Core Test Fails** → 🚨 CRITICAL - Blocks deployment
   - Indicates user-facing feature broken
   - Must fix before merge

2. **Database Test Fails** → 🚨 CRITICAL - Blocks deployment
   - Indicates data integrity issue
   - Must fix before merge

3. **Command Test Fails** → ⚠️ HIGH - Review required
   - Indicates command broken
   - Fix or disable feature

4. **Integration Test Fails** → ℹ️ MEDIUM - Investigate
   - May be credential issue
   - Verify in staging

---

## Success Criteria

**Deployment Ready When**:
- ✅ All test_functional_core.py tests pass
- ✅ All test_database.py tests pass
- ✅ All test_commands.py tests pass
- ✅ Module loading tests pass
- ✅ No import errors

**Optional (Staging-Only)**:
- Integration tests with real credentials
- Performance tests
- Load tests

---

## Maintenance

### Adding New Tests:
1. **New Feature** → Add to test_functional_core.py
2. **New Database Table** → Add to test_database.py
3. **New Command** → Add to test_commands.py
4. **One-off Fix** → Test locally, don't commit

### Removing Tests:
1. Feature deprecated? → Remove tests
2. Fix validated once? → Remove fix tests
3. Credential-dependent? → Remove or skip gracefully

---

## Example: Good vs Bad Tests

### ✅ GOOD TEST (Keep):
```python
def test_trivia_question_includes_answer_options(self):
    """Verify multiple-choice questions include ALL answer options"""
    question = generate_trivia_question(type="multiple_choice")
    assert "multiple_choice_options" in question
    assert len(question["multiple_choice_options"]) >= 2
```
**Why**: Catches real user-facing issue (missing answer options)

### ❌ BAD TEST (Remove):
```python
def test_trivia_sql_injection_fix_validation(self):
    """Verify SQL injection fix from PR #123 still works"""
    # ... test for specific historical fix
```
**Why**: One-off fix validation, not ongoing functional test

---

## Summary

**Before**: 56 test files, many one-off fix validations  
**After**: ~15-20 core test files, focused on ongoing functionality  

**Result**: Every test failure indicates a real deployment blocker, not a missing credential or deprecated fix.
