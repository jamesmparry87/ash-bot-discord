# Trivia Reply Detection - Staging Validation Guide

This guide explains how to validate the reply-based trivia system on staging without disrupting actual trivia sessions.

## **Quick Test: !triviatest Command**

The `!triviatest` command provides a complete end-to-end test of the reply detection system.

### **Usage**
```
!triviatest
```
**(Moderator permissions required)**

### **What It Does**
1. **Creates real temporary test question** in database (satisfies foreign key constraints)  
2. **Posts test messages** with clear "TEST MODE" indicators
3. **Captures message IDs** using the same workflow as real trivia
4. **Waits for replies** to either test message
5. **Validates reply detection** using production logic
6. **Auto-cleanup** after 60 seconds (removes test question and session)

### **Expected Workflow**
```
1. Run: !triviatest
2. Bot posts: 🧪 TRIVIA TEST MODE question + confirmation messages
3. Reply to either message with: "Ash"
4. Bot responds: 📝 Answer recorded (if system works)
5. Messages auto-delete after 60 seconds
```

### **Success Indicators**
- ✅ Test session created successfully
- ✅ Message tracking stored in database
- ✅ Reply detection works (bot responds to your reply)
- ✅ Answer stored in database
- ✅ Auto-cleanup completes

### **Failure Indicators**
- ❌ Database connection fails
- ❌ Message tracking storage fails  
- ❌ No response to reply (reply detection broken)
- ❌ Error messages during test

## **Production Debugging Command**

For deeper investigation, use:
```
python test_production_trivia_debug.py
```

This validates:
- Database connectivity
- Message tracking columns exist
- Recent sessions have tracking data
- Session lookup by message ID works
- Reply processing logic functions

## **Live Monitoring Command**

Add this command to your bot for real-time production monitoring:

```python
@bot.command(name="debugtrivia")
@commands.has_permissions(manage_messages=True)
async def debug_trivia(ctx):
    """Debug trivia reply detection in production"""
    try:
        embed = discord.Embed(
            title="🔧 Trivia Debug Report",
            color=0xff9900,
            timestamp=datetime.now(ZoneInfo("Europe/London"))
        )
        
        # Check active session
        active_session = db.get_active_trivia_session()
        if active_session:
            embed.add_field(
                name="Active Session",
                value=f"Session {active_session.get('id')} - Q:{active_session.get('question_message_id')} C:{active_session.get('confirmation_message_id')}",
                inline=False
            )
        else:
            embed.add_field(name="Active Session", value="None", inline=False)
        
        # Test message lookup
        test_result = db.get_trivia_session_by_message_id(999999999999999999)
        embed.add_field(
            name="Database Lookup Test", 
            value="✅ Working" if test_result is None else "❌ Unexpected result",
            inline=True
        )
        
        # Recent sessions with tracking
        conn = db.get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as recent_count
                FROM trivia_sessions 
                WHERE started_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
                AND question_message_id IS NOT NULL
            """)
            result = cur.fetchone()
            recent_count = result[0] if result else 0
            
        embed.add_field(
            name="Recent Sessions (24h)",
            value=f"{recent_count} with message tracking",
            inline=True
        )
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Debug error: {str(e)}")
```

## **Manual Validation Steps**

If you prefer manual testing:

### **Step 1: Start Real Trivia Session**
```
!starttrivia
```

### **Step 2: Reply to Question Message**
Reply to the question embed with any answer (e.g., "test")

### **Step 3: Check Response**
- ✅ Expected: `📝 Answer recorded. Results will be revealed when the session ends!`
- ❌ Problem: No response or error message

### **Step 4: End Session**  
```
!endtrivia
```

### **Step 5: Verify Results**
Check that your answer appears in the results and statistics.

## **Troubleshooting**

### **Database Connection Issues**
- Verify `DATABASE_URL` environment variable is set
- Check database connectivity with debug script
- Ensure database has required message tracking columns

### **Reply Detection Not Working**
- Confirm users are **replying** to messages (not just posting answers)
- Check bot has message permissions in the channel
- Verify message tracking was stored during `!starttrivia`
- Use `!debugtrivia` to check recent session tracking

### **Message Tracking Failures**
- Check database for `question_message_id` and `confirmation_message_id` columns
- Verify `update_trivia_session_messages()` method works
- Look for error messages during session creation

## **Environment Differences**

### **Development Environment**
- Database may not be available (shows warnings)
- Tests will show connection failures
- Reply detection won't work without database

### **Production Environment** 
- Database should be fully connected
- All tests should pass
- Reply detection should work seamlessly

## **Success Criteria**

The reply-based trivia system is working correctly when:

1. ✅ `!triviatest` completes successfully
2. ✅ Bot responds to replies with neutral feedback
3. ✅ `!endtrivia` shows accurate participation stats
4. ✅ No more gaming query interference with trivia answers
5. ✅ Users understand to reply (not just post answers)

## **User Education**

Ensure users know to:
- **Reply to trivia messages** (using Discord's reply feature)
- **Not just post answers** in chat
- **Use one answer per session** (duplicates are rejected)

The reply-based system eliminates false positives but requires users to use Discord's reply functionality correctly.
