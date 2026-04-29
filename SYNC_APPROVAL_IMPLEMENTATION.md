# Database Sync Pre-Approval Workflow - Implementation Guide

## ✅ Completed (Phase 1)

### 1. Database Schema & Methods
**File**: `Live/bot/database/games.py`

Added complete staging infrastructure:
- ✅ `create_staging_table_if_not_exists()` - Creates sync_staging table with indexes
- ✅ `stage_game_for_approval()` - Stage games before commit
- ✅ `get_staged_games()` - Retrieve staged games by session
- ✅ `get_staged_game_by_id()` - Get individual staged game
- ✅ `update_staged_game_data()` - Edit game data during review
- ✅ `mark_staged_game_reviewed()` - Mark as approved/rejected
- ✅ `commit_staged_games()` - Bulk commit approved games
- ✅ `clear_staging_session()` - Cleanup after commit
- ✅ `get_staging_session_summary()` - Stats for approval message

### 2. Initialization Script
**File**: `Live/scripts/init_staging_table.py`

Run this once to create the table:
```bash
cd Live
python scripts/init_staging_table.py
```

---

## 🔄 Remaining (Phase 2)

### Step 1: Modify Sync Logic
**File**: `Live/bot/tasks/scheduled.py`
**Function**: `perform_full_content_sync()`

**Current behavior** (lines ~2100-2400):
```python
# Direct database writes
if existing_game:
    db.update_played_game(existing_game['id'], **update_params)
else:
    db.add_played_game(**game_data)
```

**New behavior needed**:
```python
import uuid

# Create session ID at start of sync
sync_session_id = str(uuid.uuid4())

# Initialize staging table
db.games.create_staging_table_if_not_exists()

# Replace ALL db.add_played_game() calls with:
db.games.stage_game_for_approval(
    sync_session_id=sync_session_id,
    game_data=game_data,
    action_type='add',
    confidence_score=confidence,
    source_platform='youtube'  # or 'twitch'
)

# Replace ALL db.update_played_game() calls with:
db.games.stage_game_for_approval(
    sync_session_id=sync_session_id,
    game_data=game_data,
    action_type='update',
    confidence_score=confidence,
    source_platform='youtube'  # or 'twitch'
)

# At end of sync, return session ID instead of committing
return {
    'status': 'staged',
    'sync_session_id': sync_session_id,
    'new_content_count': total_content_count,
    # ... other stats
}
```

### Step 2: Modify Monday Morning Task
**File**: `Live/bot/tasks/scheduled.py`
**Function**: `monday_content_sync()`

**Current behavior** (line ~980):
```python
analysis_results = await perform_full_content_sync(start_sync_time)
# Then creates message and sends for approval
```

**New behavior needed**:
```python
analysis_results = await perform_full_content_sync(start_sync_time)

if analysis_results.get('status') == 'staged':
    sync_session_id = analysis_results['sync_session_id']
    
    # Get summary of staged games
    summary = db.games.get_staging_session_summary(sync_session_id)
    
    # Send for JAM approval (see Step 3)
    await start_sync_approval(sync_session_id, summary)
```

### Step 3: Create Approval Conversation Handler
**File**: `Live/bot/handlers/conversation_handler.py`

Add new functions:

```python
# Global state for sync approval conversations
sync_approval_conversations = {}

async def start_sync_approval(sync_session_id: str, summary: Dict[str, Any]):
    """
    Send sync approval request to JAM via DM.
    
    Message format:
    ┌─────────────────────────────────────────────┐
    │ 🔄 Database Sync Complete                  │
    │                                             │
    │ 📊 10 new games detected                   │
    │                                             │
    │ 🆕 New Games:                               │
    │ 97. Saros (Twitch, 3h 20m, 85% confidence)│
    │ 98. Star Wars Jedi: Survivor (YouTube,    │
    │     12 episodes, 6h 40m, 95% confidence)   │
    │ 99. END GAME (YouTube, 8 episodes,        │
    │     4h 10m, 65% confidence) ⚠️             │
    │                                             │
    │ 🔄 Updated Games: (+5)                     │
    │ 12. God of War (+2 episodes, +1h 20m)     │
    │ 34. Elden Ring (+45 mins)                 │
    │ ... and 3 more                             │
    │                                             │
    │ ✅ 1. Approve all and commit to database  │
    │ 🔍 2. Review individually                  │
    │ ❌ 3. Cancel entire sync                   │
    └─────────────────────────────────────────────┘
    """
    from ..config import JAM_USER_ID
    
    bot = get_bot_instance()
    if not bot:
        return
    
    user = await bot.fetch_user(JAM_USER_ID)
    if not user:
        return
    
    # Build message from summary
    new_games = summary['new_games']
    updates = summary['updates']
    
    message = "🔄 **Database Sync Complete**\n\n"
    message += f"📊 {summary['total_count']} games detected\n\n"
    
    # Show new games with IDs
    if new_games:
        message += f"🆕 **New Games ({len(new_games)}):**\n"
        for game in new_games:
            game_data = game['game_data']
            confidence = game.get('confidence_score', 1.0)
            platform = game.get('source_platform', 'unknown')
            playtime = game_data.get('total_playtime_minutes', 0)
            episodes = game_data.get('total_episodes', 0)
            
            warning = " ⚠️" if confidence < 0.75 else ""
            message += (
                f"{game['id']}. {game_data['canonical_name']} "
                f"({platform.title()}, {episodes} ep, "
                f"{playtime//60}h {playtime%60}m, {confidence*100:.0f}% conf){warning}\n"
            )
        message += "\n"
    
    # Show updates
    if updates:
        message += f"🔄 **Updated Games ({len(updates)}):**\n"
        for game in updates[:5]:  # Show first 5
            game_data = game['game_data']
            message += f"{game['id']}. {game_data['canonical_name']} "
            message += f"(+{game_data.get('total_episodes', 0)} ep)\n"
        if len(updates) > 5:
            message += f"... and {len(updates) - 5} more\n"
        message += "\n"
    
    message += "**Actions:**\n"
    message += "✅ 1. Approve all and commit to database\n"
    message += "🔍 2. Review individually\n"
    message += "❌ 3. Cancel entire sync\n"
    
    await user.send(message)
    
    # Store conversation state
    sync_approval_conversations[JAM_USER_ID] = {
        'type': 'sync_approval',
        'sync_session_id': sync_session_id,
        'stage': 'awaiting_choice',
        'summary': summary
    }


async def handle_sync_approval_response(message):
    """
    Handle JAM's response to sync approval.
    
    Flow:
    - "1" → Bulk approve all
    - "2" → Individual review
    - "3" → Cancel sync
    """
    user_id = message.author.id
    
    if user_id not in sync_approval_conversations:
        return
    
    conv = sync_approval_conversations[user_id]
    
    if conv['stage'] == 'awaiting_choice':
        choice = message.content.strip()
        
        if choice == "1":
            # Bulk approve
            await bulk_approve_sync(message, conv)
        elif choice == "2":
            # Individual review
            await start_individual_review(message, conv)
        elif choice == "3":
            # Cancel
            await cancel_sync(message, conv)


async def bulk_approve_sync(message, conv):
    """Approve all games and commit to database"""
    sync_session_id = conv['sync_session_id']
    
    # Mark all as approved
    staged_games = db.games.get_staged_games(sync_session_id)
    for game in staged_games:
        db.games.mark_staged_game_reviewed(game['id'], approved=True)
    
    # Commit to database
    counts = db.games.commit_staged_games(sync_session_id)
    
    # Clear staging
    db.games.clear_staging_session(sync_session_id)
    
    # Notify JAM
    await message.channel.send(
        f"✅ **Sync Complete**\n"
        f"• {counts['added']} new games added\n"
        f"• {counts['updated']} games updated\n"
        f"• {counts['skipped']} skipped\n\n"
        f"All changes committed to database."
    )
    
    # Clean up conversation
    del sync_approval_conversations[message.author.id]


async def start_individual_review(message, conv):
    """Start individual game review process"""
    await message.channel.send(
        "🔍 **Individual Review Mode**\n\n"
        "Which games need review? (comma-separated IDs, or 'all')"
    )
    
    conv['stage'] = 'awaiting_game_ids'


async def cancel_sync(message, conv):
    """Cancel the entire sync"""
    sync_session_id = conv['sync_session_id']
    
    # Clear staging without committing
    db.games.clear_staging_session(sync_session_id)
    
    await message.channel.send("❌ Sync cancelled. No changes made to database.")
    
    # Clean up conversation
    del sync_approval_conversations[message.author.id]
```

### Step 4: Integrate with Message Handler
**File**: `Live/bot/handlers/conversation_handler.py`

In the main message handler for DMs, add:

```python
async def handle_dm_message(message):
    """Handle DM messages for various conversation flows"""
    user_id = message.author.id
    
    # Check if user is in sync approval conversation
    if user_id in sync_approval_conversations:
        await handle_sync_approval_response(message)
        return
    
    # ... existing conversation handlers
```

---

## 📋 Testing Checklist

1. **Initialize Table**
   ```bash
   python Live/scripts/init_staging_table.py
   ```

2. **Test Staging**
   - Manually trigger a sync
   - Verify games are staged (not committed)
   - Check `sync_staging` table has entries

3. **Test Approval Flow**
   - Receive DM with game list
   - Reply "1" for bulk approve
   - Verify games committed to `played_games`
   - Verify `sync_staging` cleared

4. **Test Individual Review**
   - Trigger sync
   - Reply "2" for individual review
   - Provide game IDs
   - Test edit/approve/skip for each

5. **Test Cancel**
   - Trigger sync
   - Reply "3" to cancel
   - Verify no games committed
   - Verify staging cleared

---

## 🎯 Benefits

✅ **No database pollution** - Bad extractions never touch production
✅ **Fully reviewable** - See all changes before commit
✅ **Editable** - Fix game names without SQL
✅ **Resumable** - Staging survives bot restarts
✅ **Lightweight** - One-click approval for typical weeks
✅ **Thorough** - Detailed review for backlog catch-ups

---

## 📝 Implementation Priority

**Immediate** (before next Monday):
1. Run init script to create table ✅
2. Modify sync logic to use staging
3. Implement basic approval handler (option 1 only)

**Short-term** (this week):
4. Add individual review flow (option 2)
5. Add edit capabilities
6. Full testing

**Nice-to-have**:
- Auto-approve high-confidence games (>90%)
- Weekly summary statistics
- Approval history/audit log
