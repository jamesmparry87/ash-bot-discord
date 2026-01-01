# ASH BOT - DATABASE SCHEMA DOCUMENTATION

> **Version:** 1.0  
> **Last Updated:** 1 January 2026  
> **Database:** PostgreSQL (Railway.app)

## Table of Contents
1. [Core Game Database](#core-game-database)
2. [Trivia System](#trivia-system)
3. [User Management](#user-management)
4. [Scheduling & Reminders](#scheduling--reminders)
5. [AI Usage Tracking](#ai-usage-tracking)
6. [Session Management](#session-management)
7. [Bot Configuration](#bot-configuration)
8. [Data Format Standards](#data-format-standards)
9. [Schema Normalization Goals](#schema-normalization-goals)

---

## Core Game Database

### `played_games` (Primary Game Database)

**Purpose:** Central repository for all games played on YouTube and/or Twitch, with cached engagement metrics.

**Current State:** Production-ready, but requires normalization (see [Schema Normalization Goals](#schema-normalization-goals))

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique game identifier |
| `canonical_name` | VARCHAR(255) | NOT NULL | Official game name (e.g., "God of War (2018)") |
| `alternative_names` | TEXT | NULL | JSON array or comma-separated list of alternate spellings |
| `series_name` | VARCHAR(255) | NULL | Franchise/series grouping (e.g., "God of War") |
| `genre` | VARCHAR(100) | NULL | Primary genre (e.g., "action-adventure", "survival-horror") |
| `release_year` | INTEGER | NULL | Year game was released |
| `platform` | VARCHAR(100) | NULL | Gaming platform (e.g., "PlayStation 5", "PC") |
| `first_played_date` | DATE | NULL | Date when first episode/VOD was published |
| `completion_status` | VARCHAR(50) | DEFAULT 'unknown' | Values: `unknown`, `ongoing`, `dropped`, `completed` |
| `total_episodes` | INTEGER | DEFAULT 0 | Combined count of YouTube episodes + Twitch VODs |
| `total_playtime_minutes` | INTEGER | DEFAULT 0 | Total recorded playtime across all platforms |

**Platform-Specific Fields:**

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `youtube_playlist_url` | TEXT | Full YouTube playlist URL | `https://www.youtube.com/playlist?list=PLxxx...` |
| `youtube_views` | INTEGER | Cached view count from YouTube API | `150243` |
| `twitch_vod_urls` | TEXT | JSON array of Twitch VOD URLs | `["https://www.twitch.tv/videos/123", ...]` |
| `twitch_views` | INTEGER | Cached view count (engagement metric) | `5420` |

**Metadata Fields:**

| Column | Type | Description |
|--------|------|-------------|
| `notes` | TEXT | Free-form notes (auto-discovery info, manual annotations) |
| `created_at` | TIMESTAMP | Record creation timestamp |
| `updated_at` | TIMESTAMP | Last modification timestamp |

**Indexes:**
- `idx_played_games_canonical_name` - Fast lookups by game name
- `idx_played_games_series_name` - Fast series filtering

**Storage Format for Platform IDs:**

**YouTube:**
- **Field:** `youtube_playlist_url`
- **Format:** Full URL stored as TEXT
- **Example:** `https://www.youtube.com/playlist?list=PLG8LBpstyh9Q...`
- **Extraction:** Playlist ID can be parsed from `list=` parameter

**Twitch:**
- **Field:** `twitch_vod_urls`
- **Format:** JSON array of full URLs stored as TEXT
- **Example:** `["https://www.twitch.tv/videos/2345678901", "https://www.twitch.tv/videos/2345678902"]`
- **Extraction:** VOD IDs can be parsed from `/videos/` segment

**Current Data Format (Legacy):**
- `alternative_names`: Mixed formats (JSON arrays, PostgreSQL arrays, comma-separated)
- `twitch_vod_urls`: Mixed formats (JSON arrays, PostgreSQL arrays, comma-separated)

**Target Format (Priority 2.2 - Schema Normalization):**
- `alternative_names`: Pure JSON (`["Name 1", "Name 2"]`)
- `twitch_vod_urls`: Pure JSON (`["url1", "url2"]`)

---

## Trivia System

### `trivia_questions`

**Purpose:** Pool of trivia questions (mod-submitted and AI-generated)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique question identifier |
| `question_text` | TEXT | NOT NULL | The trivia question |
| `question_type` | VARCHAR(20) | NOT NULL | `single` or `multiple_choice` |
| `correct_answer` | TEXT | NULL | Answer for single-type questions |
| `multiple_choice_options` | TEXT[] | NULL | Array of options for multiple-choice |
| `is_dynamic` | BOOLEAN | DEFAULT FALSE | Requires real-time calculation (e.g., "longest playtime") |
| `dynamic_query_type` | VARCHAR(50) | NULL | Query type for dynamic questions |
| `submitted_by_user_id` | BIGINT | NULL | Discord user ID if mod-submitted, NULL if AI-generated |
| `category` | VARCHAR(50) | NULL | Question category (e.g., `completion`, `playtime`, `genre`) |
| `difficulty_level` | INTEGER | DEFAULT 1 | 1-5 scale |
| `is_active` | BOOLEAN | DEFAULT TRUE | Whether question can be used |
| `status` | VARCHAR(20) | DEFAULT 'available' | `available`, `answered`, `retired` |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Question creation time |
| `last_used_at` | TIMESTAMP | NULL | Last time question was used in session |
| `usage_count` | INTEGER | DEFAULT 0 | Number of times question has been used |

**Status Flow:**
```
available → answered (after being used in a session)
answered → available (manual reset or cooldown expiry)
any → retired (permanently disabled)
```

### `trivia_sessions`

**Purpose:** Active and historical trivia sessions

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique session identifier |
| `question_id` | INTEGER | FOREIGN KEY → trivia_questions(id) | Question used in this session |
| `session_date` | DATE | NOT NULL | Date of session |
| `session_type` | VARCHAR(20) | DEFAULT 'weekly' | `weekly`, `bonus` |
| `question_submitter_id` | BIGINT | NULL | For conflict detection (mod can't answer own question) |
| `calculated_answer` | TEXT | NULL | For dynamic questions, the computed answer |
| `status` | VARCHAR(20) | DEFAULT 'active' | `active`, `completed`, `expired` |
| `started_at` | TIMESTAMP | DEFAULT NOW() | Session start time |
| `ended_at` | TIMESTAMP | NULL | Session end time |
| `first_correct_user_id` | BIGINT | NULL | User who answered correctly first |
| `total_participants` | INTEGER | DEFAULT 0 | Count of unique participants |
| `correct_answers_count` | INTEGER | DEFAULT 0 | Count of correct answers |
| `question_message_id` | BIGINT | NULL | Discord message ID of question embed |
| `confirmation_message_id` | BIGINT | NULL | Discord message ID of confirmation |
| `channel_id` | BIGINT | NULL | Discord channel where session is active |

### `trivia_answers`

**Purpose:** All answer submissions for trivia sessions

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique answer identifier |
| `session_id` | INTEGER | FOREIGN KEY → trivia_sessions(id) | Parent session |
| `user_id` | BIGINT | NOT NULL | Discord user ID |
| `answer_text` | TEXT | NOT NULL | User's submitted answer |
| `normalized_answer` | TEXT | NULL | Normalized version for matching |
| `submitted_at` | TIMESTAMP | DEFAULT NOW() | Submission timestamp |
| `is_correct` | BOOLEAN | NULL | Whether answer is correct |
| `is_first_correct` | BOOLEAN | DEFAULT FALSE | Whether this was the first correct answer |
| `conflict_detected` | BOOLEAN | DEFAULT FALSE | Mod answering own question |
| `is_close` | BOOLEAN | DEFAULT FALSE | Answer was close but not exact |

---

## User Management

### `strikes`

**Purpose:** User strike tracking for moderation

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `user_id` | BIGINT | PRIMARY KEY | Discord user ID |
| `strike_count` | INTEGER | DEFAULT 0 | Current strike count |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last strike update |

### `game_recommendations`

**Purpose:** Community game suggestions

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique recommendation ID |
| `name` | VARCHAR(255) | NOT NULL | Game name |
| `reason` | TEXT | NULL | Why user recommends it |
| `added_by` | VARCHAR(100) | NULL | Discord username |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Submission timestamp |

---

## Scheduling & Reminders

### `reminders`

**Purpose:** User-scheduled reminders with optional auto-actions

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique reminder ID |
| `user_id` | BIGINT | NOT NULL | Discord user ID |
| `reminder_text` | TEXT | NOT NULL | Reminder message |
| `scheduled_time` | TIMESTAMP | NOT NULL | When to deliver reminder |
| `delivery_channel_id` | BIGINT | NULL | Discord channel for delivery |
| `delivery_type` | VARCHAR(20) | NOT NULL | `dm` or `channel` |
| `auto_action_enabled` | BOOLEAN | DEFAULT FALSE | Enable auto-action after reminder |
| `auto_action_type` | VARCHAR(50) | NULL | Type of auto-action (e.g., `start_trivia`) |
| `auto_action_data` | JSONB | NULL | Additional data for auto-action |
| `status` | VARCHAR(20) | DEFAULT 'pending' | `pending`, `delivered`, `cancelled`, `auto_completed`, `expired` |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Creation timestamp |
| `delivered_at` | TIMESTAMP | NULL | Actual delivery timestamp |
| `auto_executed_at` | TIMESTAMP | NULL | Auto-action execution timestamp |

---

## AI Usage Tracking

### `ai_usage_tracking`

**Purpose:** Track Gemini API quota usage and prevent exhaustion

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `tracking_date` | DATE | PRIMARY KEY | Date being tracked |
| `daily_requests` | INTEGER | DEFAULT 0 | Total requests today |
| `hourly_requests` | INTEGER | DEFAULT 0 | Requests this hour |
| `daily_errors` | INTEGER | DEFAULT 0 | Error count today |
| `last_reset_time` | TIMESTAMP WITH TIME ZONE | NULL | Last hourly reset |
| `last_hour_reset` | INTEGER | DEFAULT 0 | Hour of last reset |
| `quota_exhausted` | BOOLEAN | DEFAULT FALSE | Whether quota is exhausted |
| `current_model` | TEXT | NULL | Active Gemini model |
| `last_model_switch` | TIMESTAMP WITH TIME ZONE | NULL | Last model switch timestamp |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | Record creation |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | Last update |

### `ai_alert_log`

**Purpose:** Log critical AI system alerts for mod notification

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique alert ID |
| `alert_type` | TEXT | NOT NULL | Alert category |
| `severity` | TEXT | NOT NULL | `low`, `medium`, `high`, `critical` |
| `message` | TEXT | NOT NULL | Alert message |
| `error_details` | JSONB | NULL | Structured error data |
| `dm_sent` | BOOLEAN | DEFAULT FALSE | Whether mod was notified |
| `dm_sent_at` | TIMESTAMP WITH TIME ZONE | NULL | Notification timestamp |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | Alert creation |

**Indexes:**
- `idx_ai_alert_log_created` - Fast time-based queries
- `idx_ai_alert_log_type_severity` - Fast filtering by type/severity

---

## Session Management

### `trivia_approval_sessions`

**Purpose:** Persistent approval workflows for trivia question submission (survives bot restarts)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique session ID |
| `user_id` | BIGINT | NOT NULL | Discord user ID |
| `session_type` | VARCHAR(50) | NOT NULL, DEFAULT 'question_approval' | Session type |
| `conversation_step` | VARCHAR(50) | NOT NULL | Current step in approval flow |
| `question_data` | JSONB | NOT NULL | Question data being approved |
| `conversation_data` | JSONB | DEFAULT '{}' | Additional conversation state |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Session creation |
| `last_activity` | TIMESTAMP | DEFAULT NOW() | Last user interaction |
| `expires_at` | TIMESTAMP | NULL | Expiration time (default: 3 hours) |
| `status` | VARCHAR(20) | DEFAULT 'active' | `active`, `completed`, `cancelled`, `expired` |
| `bot_restart_count` | INTEGER | DEFAULT 0 | Number of bot restarts during session |

**Indexes:**
- `idx_trivia_approval_user_status` - Fast user session lookups
- `idx_trivia_approval_expires` - Fast expiration cleanup

### `game_review_sessions`

**Purpose:** Review workflows for low-confidence game matches from title parsing

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique session ID |
| `user_id` | BIGINT | NOT NULL | Moderator reviewing the match |
| `session_type` | VARCHAR(50) | NOT NULL, DEFAULT 'game_review' | Session type |
| `original_title` | TEXT | NOT NULL | Original video/VOD title |
| `extracted_name` | TEXT | NOT NULL | Extracted game name |
| `confidence_score` | FLOAT | NOT NULL | Match confidence (0.0-1.0) |
| `alternative_names` | TEXT | NULL | Potential alternative names |
| `source` | VARCHAR(20) | NOT NULL | `youtube` or `twitch` |
| `igdb_data` | JSONB | NULL | IGDB API response data |
| `video_url` | TEXT | NULL | Link to video/VOD |
| `conversation_step` | VARCHAR(50) | NOT NULL | Current step in review flow |
| `conversation_data` | JSONB | DEFAULT '{}' | Additional state |
| `created_at` | TIMESTAMP | DEFAULT NOW() | Session creation |
| `last_activity` | TIMESTAMP | DEFAULT NOW() | Last interaction |
| `expires_at` | TIMESTAMP | NULL | Expiration (default: 24 hours) |
| `status` | VARCHAR(20) | DEFAULT 'pending' | `pending`, `approved`, `rejected`, `cancelled`, `expired` |
| `approved_name` | TEXT | NULL | Final approved name |
| `approved_data` | JSONB | NULL | Final approved game data |
| `bot_restart_count` | INTEGER | DEFAULT 0 | Restart counter |

**Indexes:**
- `idx_game_review_user_status` - Fast user lookups
- `idx_game_review_expires` - Fast cleanup

---

## Bot Configuration

### `bot_config`

**Purpose:** Dynamic bot configuration storage (key-value pairs)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `key` | VARCHAR(50) | PRIMARY KEY | Configuration key |
| `value` | TEXT | NULL | Configuration value (stored as string) |
| `updated_at` | TIMESTAMP | DEFAULT NOW() | Last update timestamp |

**Common Keys:**
- `last_youtube_check` - Last YouTube channel check timestamp
- `last_twitch_check` - Last Twitch channel check timestamp
- `last_content_sync_timestamp` - Last full content sync

### `weekly_announcements`

**Purpose:** Approval workflow for Monday/Friday announcements

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | SERIAL | PRIMARY KEY | Unique announcement ID |
| `day` | VARCHAR(10) | NOT NULL | `monday` or `friday` |
| `generated_content` | TEXT | NOT NULL | AI-generated announcement text |
| `analysis_cache` | JSONB | NULL | Cached stats/analysis data |
| `status` | VARCHAR(20) | DEFAULT 'pending_approval' | `pending_approval`, `approved`, `rejected`, `cancelled`, `posted` |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | Generation timestamp |
| `approved_at` | TIMESTAMP WITH TIME ZONE | NULL | Approval timestamp |

---

## Data Format Standards

### JSON Array Format (Target Standard)
All list-based fields should use consistent JSON format:

```json
["Item 1", "Item 2", "Item 3"]
```

**Fields Using This Format:**
- `played_games.alternative_names`
- `played_games.twitch_vod_urls`
- `trivia_questions.multiple_choice_options`

**Helper Functions:**
- `_parse_comma_separated_list()` - Handles legacy formats during migration
- `_convert_text_to_arrays()` - Converts TEXT to Python lists for compatibility

### Timestamp Standards
- **Storage:** Always use PostgreSQL `TIMESTAMP WITH TIME ZONE`
- **Application Timezone:** Europe/London (UTC+0 with BST)
- **Date Formatting:** DD-MM-YYYY (UK format) for display

### ID Fields
- **Discord IDs:** BIGINT (Discord snowflake IDs exceed 32-bit integers)
- **Database IDs:** SERIAL (auto-incrementing 32-bit integers)

---

## Schema Normalization Goals

### Priority 2.2: Schema Normalization (Q1 2026)

**Current Problems:**
1. **Mixed Data Formats:** Alternative names stored as JSON, PostgreSQL arrays, or comma-separated strings
2. **No Data Validation:** Invalid JSON can cause parsing errors
3. **Manual Editing Difficulty:** Raw TEXT fields are error-prone

**Normalization Strategy:**

#### Option A: Pure JSON (Recommended)
```sql
ALTER TABLE played_games
ALTER COLUMN alternative_names TYPE JSONB 
USING alternative_names::jsonb;

-- Benefits: PostgreSQL can validate and index JSON
-- Enables: WHERE alternative_names @> '["God of War"]'
```

#### Option B: Separate Table (Future Consideration)
```sql
CREATE TABLE game_aliases (
    id SERIAL PRIMARY KEY,
    game_id INTEGER REFERENCES played_games(id),
    alias VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Benefits: Easier to query/manage individual aliases
-- Enables: Full-text search on aliases
```

**Recommended Approach:** Start with Option A (Pure JSON), evaluate Option B if alias management becomes complex.

### Priority 6: Title Pattern Learning System

**New Tables Needed:**

```sql
CREATE TABLE title_game_mappings (
    id SERIAL PRIMARY KEY,
    title_pattern TEXT NOT NULL,
    game_id INTEGER REFERENCES played_games(id),
    confidence FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_title_patterns ON title_game_mappings(title_pattern);
```

**Purpose:** Learn from successful title→game mappings to improve future parsing accuracy.

### Priority 7: Real-Time Engagement Stats

**New Columns Needed:**

```sql
ALTER TABLE played_games
ADD COLUMN last_stats_query TIMESTAMP NULL,
ADD COLUMN query_count INTEGER DEFAULT 0;
```

**Purpose:** Track when users query game stats to prioritize API refresh operations.

### Priority 8: Platform Awareness

**New Column Needed:**

```sql
ALTER TABLE played_games
ADD COLUMN platform_type VARCHAR(20) NULL;

-- Values: 'youtube', 'twitch', 'both'
```

**Purpose:** Quick platform identification without checking URL columns.

---

## Migration Scripts Location

All database migration scripts should be stored in:
```
Live/scripts/sql/
├── migration_*.sql          # Schema migrations
├── apply_sql.py             # Migration runner
└── README.md                # Migration documentation
```

---

## Backup & Recovery

**Backup Location:** `Live/scripts/backup_played_games_*.json`

**Backup Commands:**
```python
# Create backup
db.get_all_played_games()  # Export to JSON

# Restore backup
db.bulk_import_played_games(games_data)  # Import from JSON
```

---

## Questions or Issues?

For schema questions, implementation details, or migration assistance:
1. Check `Live/documentation/REFACTORING_GUIDE.md`
2. Review existing migration scripts in `Live/scripts/sql/`
3. Consult with maintainer (James) or AI assistants (Claude/Cline)

---

**Document Version History:**
- v1.0 (1 Jan 2026) - Initial comprehensive schema documentation
