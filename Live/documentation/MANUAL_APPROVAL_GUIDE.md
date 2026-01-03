# Manual Trivia Question Approval System

## Overview

The manual approval system allows moderators to trigger quality checks for trivia questions before ad hoc sessions, ensuring content meets standards before being used.

## Commands

### `!approvequestion <target>`

Send trivia questions to JAM for manual review and approval.

**Usage Options:**

1. **Specific Question ID**
   ```
   !approvequestion 25
   ```
   - Sends question #25 to JAM for review
   - Shows question preview to moderator
   - Calculates dynamic answers if needed

2. **Auto-Selection**
   ```
   !approvequestion auto
   ```
   - Uses same priority system as `!starttrivia`
   - Sends next-in-line question for approval
   - Useful for previewing what would be auto-selected

3. **Generate New Question**
   ```
   !approvequestion generate
   ```
   - Creates new AI-generated question
   - Sends generated content to JAM for review
   - Fallback generation if dedicated AI function unavailable

### `!approvestatus`

Check status of pending JAM approvals.

**Output includes:**
- Current approval status
- Conversation step (approval/modification/etc.)
- Question preview
- Age of approval request
- Timeout information (24 hours)

## JAM Approval Workflow

When a question is sent for approval, JAM receives a DM with:

### Approval Options:
1. **✅ Approve** - Add question to database as-is
2. **✏️ Modify** - Edit question before approving  
3. **❌ Reject** - Discard question and optionally generate alternative

### Extended Features:
- **24-hour timeout** for late responses
- **Conversation persistence** across bot restarts
- **Context restoration** if JAM responds after delay
- **Modification workflow** with preview before final approval

## Use Cases

### Quality Check Before Bonus Sessions
```
Moderator: !approvequestion auto
Bot: 🎯 Auto-selected question #47 sent to JAM for approval
JAM: Reviews question via DM, approves/modifies/rejects
Moderator: !starttrivia 47  (after approval)
```

### Review Newly Added Questions
```
Moderator: !approvequestion 52
Bot: 📋 Question #52 sent to JAM for approval
JAM: Modifies question wording for clarity
Bot: ✅ Modified question approved, ready for use
```

### Preview Event Questions
```
Moderator: !approvequestion generate
Bot: 🧠 Generated question sent to JAM for approval
JAM: Reviews AI-generated content, approves with confidence
```

## Integration Points

### Database Methods Required:
- `get_next_trivia_question()` - Auto-selection priority system
- `get_trivia_question_by_id()` - Specific question retrieval
- `calculate_dynamic_answer()` - Dynamic answer calculation
- `add_trivia_question()` - Save approved questions

### Conversation Handler Integration:
- `start_jam_question_approval()` - Initiate approval workflow
- `jam_approval_conversations` - Track approval state
- Extended conversation persistence (24 hours vs 2 hours)

### AI System Integration:
- Primary: `generate_trivia_question()` if available
- Fallback: `_generate_ai_question_fallback()` using basic AI prompts
- Graceful degradation if AI systems unavailable

## Error Handling

### Database Issues:
- Clear error messages for missing methods
- Fallback suggestions for unavailable features
- Graceful degradation for offline database

### Approval System Issues:
- Detection of DM availability (JAM settings)
- Conversation handler availability checks
- Import error handling for optional components

### AI Generation Issues:
- Multiple fallback strategies for question generation
- Rate limiting awareness
- Clear feedback on AI system status

## Permissions

- Requires `manage_messages` permission (moderators only)
- Same permission level as `!starttrivia` command
- Works in server channels, not DM-restricted like question submission

## Monitoring & Logging

### Conversation Tracking:
- Approval request initiation logged
- JAM response activity tracked
- Conversation cleanup after timeout/completion

### Error Logging:
- Database method errors logged with context
- AI generation failures logged for debugging
- Approval workflow errors logged for monitoring

### Statistics:
- Approval success/failure rates trackable
- Question modification frequency monitorable
- JAM response time patterns observable

## Best Practices

### For Moderators:
1. Use `!approvequestion auto` before events to preview
2. Check `!approvestatus` if waiting for JAM response
3. Use specific IDs for reviewing newly added questions
4. Generate new questions when pool is low

### For JAM:
1. Respond to approval requests within 24 hours when possible
2. Use modification option for minor wording improvements
3. Reject questions that don't meet quality standards
4. Approve quickly during event preparation periods

### For System Maintenance:
1. Monitor approval conversation cleanup logs
2. Track database method availability
3. Ensure AI systems remain functional for generation
4. Test approval workflow after bot restarts

## Future Enhancements

### Potential Additions:
- Bulk approval for multiple questions
- Approval delegation to other moderators
- Question quality scoring system
- Automated approval for high-confidence AI questions
- Approval history and analytics dashboard

### Integration Opportunities:
- Calendar integration for event preparation
- Question pool health monitoring
- Automated quality checks before approval requests
- Integration with scheduling system for Trivia Tuesday
