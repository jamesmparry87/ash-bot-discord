# ASH BOT - RAID BRIEFING SYSTEM SPECIFICATION

> **Priority:** 4 (Revised)  
> **Timeline:** Q1-Q2 2026  
> **Platform:** Discord-only (Twitch-only stream notifications)

## Table of Contents
1. [Overview](#overview)
2. [Design Rationale](#design-rationale)
3. [System Architecture](#system-architecture)
4. [Implementation Details](#implementation-details)
5. [Ash Persona Integration](#ash-persona-integration)
6. [Configuration & Setup](#configuration--setup)
7. [Testing & Rollout](#testing--rollout)

---

## Overview

**Concept:** Instead of Ash connecting to Twitch chat (spam risk), implement a Discord-based "Raid Briefing" system where Ash posts military-style mission briefings when Jonesy goes live on Twitch.

**Core Functionality:**
- Detect when Jonesy starts streaming on Twitch
- Post tactical "Raid Briefing" in dedicated Discord channel
- Ping `@Raiders` role to mobilize community
- Provide stream link, game info, and mission parameters
- Post milestone updates during stream
- Post post-stream debriefing with stats

**Benefits Over Twitch Chat Integration:**
- ✅ Zero spam bot detection risk
- ✅ Stays within Ash's jurisdiction (Discord)
- ✅ Richer formatting (embeds, roles, reactions)
- ✅ Persistent notifications (scrollable history)
- ✅ Maintains Ash persona integrity

---

## Design Rationale

### Why NOT Twitch Chat Integration (Original Priority 4.1)

**The Original Plan:**
```
Priority 4.1: "Ash Raid" Capability
- Ash connects to Twitch chat via TwitchIO
- Drops periodic status checks in chat
- Uses automated/repetitive language
```

**The Problems:**
1. **Spam Bot Detection:** Twitch automod is aggressive against bots that:
   - Message in channels where they're not moderators
   - Have low message frequency patterns
   - Use automated/repetitive language
   - Don't have established chat history

2. **Limited Functionality:** Twitch chat doesn't support:
   - Rich embeds with formatting
   - Role pinging
   - Persistent message history
   - Interactive reactions

3. **Jurisdictional Issues:** Ash's "character" operates from Discord HQ. Twitch chat is outside his operational parameters.

### Why Discord Raid Briefing System (Revised Priority 4)

**Advantages:**
1. **Safe & Reliable:** No risk of spam detection or bans
2. **Rich Formatting:** Discord embeds with colors, fields, images
3. **Targeted Notifications:** Ping specific roles (@Raiders)
4. **Persistent Record:** Users can scroll back to see briefings
5. **Ash Persona Fit:** Military-style command center operation from Discord
6. **Interactive Features:** Reactions, replies, follow-up messages

**Lore Justification:**
> "My protocols restrict direct Twitch chat interference to prevent operational anomalies. However, coordinating tactical deployments via Discord command channels is within authorized parameters and ensures optimal mission success probability."

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Twitch Webhook                        │
│         (EventSub: stream.online notification)          │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Ash Bot - Stream Monitor                   │
│          (Live/bot/integrations/twitch.py)              │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│           Raid Briefing Generator                       │
│        (Live/bot/tasks/raid_briefings.py)               │
│                                                          │
│  • Fetch stream info (game, title, viewer count)       │
│  • Query database for game stats                        │
│  • Format Ash-style tactical briefing                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Discord Channel Post                       │
│           (#raid-briefings or #streams)                 │
│                                                          │
│  • Rich embed with mission parameters                   │
│  • @Raiders role ping                                   │
│  • Stream link & game info                              │
│  • Reaction buttons for engagement                      │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Stream Start Detection:**
   - Twitch EventSub webhook fires → `stream.online` event
   - Webhook payload includes: stream ID, title, game, viewer count

2. **Briefing Generation:**
   - Fetch additional stream metadata from Twitch API
   - Query database for game history/stats (if game in database)
   - Generate Ash-style briefing using military templates
   - Format as Discord embed

3. **Discord Posting:**
   - Post to configured raid briefing channel
   - Ping @Raiders role
   - Add reaction buttons (🚀 Deploy, 📊 Stats, ❤️ Support)

4. **Milestone Updates (Optional):**
   - Monitor stream every 15-30 minutes
   - Post updates for milestones (50 viewers, 100 viewers, etc.)
   - Keep community engaged

5. **Post-Stream Debriefing:**
   - Detect stream end via `stream.offline` event
   - Post summary: duration, peak viewers, highlights
   - Thank raiders for participation

---

## Implementation Details

### Phase 1: Twitch Webhook Integration

**File:** `Live/bot/integrations/twitch.py`

**Webhook Setup:**
```python
# Twitch EventSub subscription for stream.online
EVENTSUB_TYPE = "stream.online"
CALLBACK_URL = "https://ash-bot.railway.app/webhooks/twitch"

async def subscribe_to_stream_events():
    """Subscribe to Twitch EventSub for stream notifications"""
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "type": "stream.online",
        "version": "1",
        "condition": {
            "broadcaster_user_id": JONESY_TWITCH_USER_ID
        },
        "transport": {
            "method": "webhook",
            "callback": CALLBACK_URL,
            "secret": WEBHOOK_SECRET
        }
    }
    
    # POST to Twitch EventSub endpoint
    # Store subscription ID in database for management
```

**Webhook Handler:**
```python
from aiohttp import web

async def handle_twitch_webhook(request):
    """Handle incoming Twitch EventSub webhooks"""
    
    # Verify webhook signature
    signature = request.headers.get("Twitch-Eventsub-Message-Signature")
    if not verify_signature(signature, await request.read()):
        return web.Response(status=403)
    
    # Handle challenge verification
    if request.headers.get("Twitch-Eventsub-Message-Type") == "webhook_callback_verification":
        data = await request.json()
        return web.Response(text=data["challenge"])
    
    # Handle stream.online notification
    if request.headers.get("Twitch-Eventsub-Message-Type") == "notification":
        data = await request.json()
        event = data["event"]
        
        # Trigger raid briefing
        await post_raid_briefing(
            stream_id=event["id"],
            broadcaster_name=event["broadcaster_user_name"],
            started_at=event["started_at"]
        )
    
    return web.Response(status=200)
```

### Phase 2: Raid Briefing Generator

**File:** `Live/bot/tasks/raid_briefings.py`

**Core Function:**
```python
async def post_raid_briefing(stream_id: str, broadcaster_name: str, started_at: str):
    """
    Generate and post tactical raid briefing to Discord
    
    Args:
        stream_id: Twitch stream ID
        broadcaster_name: Streamer username
        started_at: ISO 8601 timestamp of stream start
    """
    
    # Fetch stream details from Twitch API
    stream_info = await fetch_stream_info(broadcaster_name)
    
    if not stream_info:
        logger.error(f"Failed to fetch stream info for {broadcaster_name}")
        return
    
    # Extract key details
    title = stream_info.get("title", "Unknown Mission")
    game_name = stream_info.get("game_name", "Unknown Game")
    viewer_count = stream_info.get("viewer_count", 0)
    stream_url = f"https://twitch.tv/{broadcaster_name}"
    
    # Query database for game stats (if available)
    db = get_database()
    game_data = db.get_played_game(game_name)
    
    game_context = ""
    if game_data:
        episodes = game_data.get("total_episodes", 0)
        playtime_hours = game_data.get("total_playtime_minutes", 0) / 60
        game_context = f"\n**Previous Operations:** {episodes} episodes, {playtime_hours:.1f} hours logged"
    
    # Generate Ash-style briefing embed
    embed = discord.Embed(
        title="🚨 RAID BRIEFING - TACTICAL DEPLOYMENT INITIATED",
        description=f"Captain Jonesy has commenced operations on Twitch.",
        color=discord.Color.red(),
        timestamp=datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    )
    
    embed.add_field(
        name="📊 Mission Parameters",
        value=f"**Target:** {game_name}\n**Mission Title:** {title}\n**Current Personnel:** {viewer_count} raiders{game_context}",
        inline=False
    )
    
    embed.add_field(
        name="🎯 Deployment Coordinates",
        value=f"[**► DEPLOY TO MISSION**]({stream_url})",
        inline=False
    )
    
    embed.add_field(
        name="⚠️ Command Recommendation",
        value="All available raiders, proceed to deployment coordinates. Visual engagement and chat participation will increase mission success probability.",
        inline=False
    )
    
    embed.set_footer(text="- Ash, Science Officer | Tactical Operations Command")
    
    # Get raid briefings channel
    channel = bot.get_channel(RAID_BRIEFINGS_CHANNEL_ID)
    
    if not channel:
        logger.error(f"Raid briefings channel {RAID_BRIEFINGS_CHANNEL_ID} not found")
        return
    
    # Post briefing with @Raiders ping
    raiders_role = discord.utils.get(channel.guild.roles, name="Raiders")
    
    message = await channel.send(
        content=f"{raiders_role.mention} **RAID BRIEFING**" if raiders_role else "**RAID BRIEFING**",
        embed=embed
    )
    
    # Add reaction buttons
    await message.add_reaction("🚀")  # Deploy
    await message.add_reaction("📊")  # Stats
    await message.add_reaction("❤️")  # Support
    
    # Store message ID for milestone updates
    store_briefing_message(stream_id, message.id)
    
    logger.info(f"Posted raid briefing for {broadcaster_name} - {game_name}")
```

### Phase 3: Milestone Updates (Optional)

**Periodic Stream Monitoring:**
```python
async def monitor_active_streams():
    """
    Background task that monitors active streams for milestones
    
    Runs every 15 minutes while stream is active
    """
    
    while True:
        try:
            # Check if stream is still live
            stream_info = await fetch_stream_info("joneysypacecat")
            
            if stream_info:
                viewer_count = stream_info.get("viewer_count", 0)
                
                # Check for milestone achievements
                milestones = [50, 100, 150, 200, 300, 500]
                
                for milestone in milestones:
                    if viewer_count >= milestone and not milestone_reached(stream_info["id"], milestone):
                        await post_milestone_update(stream_info, milestone)
                        mark_milestone_reached(stream_info["id"], milestone)
            
            # Sleep for 15 minutes
            await asyncio.sleep(900)
        
        except Exception as e:
            logger.error(f"Error monitoring stream: {e}")
            await asyncio.sleep(60)  # Retry in 1 minute on error
```

**Milestone Update Format:**
```python
async def post_milestone_update(stream_info: dict, milestone: int):
    """Post milestone achievement update"""
    
    embed = discord.Embed(
        title=f"📈 MISSION UPDATE - {milestone} PERSONNEL MILESTONE",
        description=f"Current raider count has reached {stream_info['viewer_count']} personnel.",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="🎯 Analysis",
        value=f"Mission engagement exceeds {milestone} personnel threshold. Tactical support appreciated.",
        inline=False
    )
    
    channel = bot.get_channel(RAID_BRIEFINGS_CHANNEL_ID)
    await channel.send(embed=embed)
```

### Phase 4: Post-Stream Debriefing

**Stream End Detection:**
```python
async def handle_stream_offline(event_data: dict):
    """Handle stream.offline webhook event"""
    
    stream_id = event_data["id"]
    
    # Fetch final stream stats
    # Note: Stream may no longer be accessible via API after ending
    # Use stored data from monitoring
    
    stored_data = get_stored_stream_data(stream_id)
    
    if not stored_data:
        logger.warning(f"No stored data found for stream {stream_id}")
        return
    
    # Calculate duration
    started_at = datetime.fromisoformat(stored_data["started_at"])
    ended_at = datetime.now(timezone.utc)
    duration = ended_at - started_at
    
    # Generate debriefing
    embed = discord.Embed(
        title="✅ MISSION DEBRIEF - OPERATIONS CONCLUDED",
        description=f"Captain Jonesy has concluded tactical operations.",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📊 Mission Summary",
        value=f"**Duration:** {format_duration(duration)}\n**Peak Raiders:** {stored_data['peak_viewers']} personnel\n**Game:** {stored_data['game_name']}",
        inline=False
    )
    
    embed.add_field(
        name="🎯 Assessment",
        value="Mission parameters successfully met. Raider engagement contributed to operational success.",
        inline=False
    )
    
    embed.set_footer(text="- Ash, Science Officer | Post-Mission Analysis")
    
    channel = bot.get_channel(RAID_BRIEFINGS_CHANNEL_ID)
    await channel.send(embed=embed)
```

---

## Ash Persona Integration

### Message Templates

**Pre-Stream Warning (15 minutes before):**
```
🔔 ADVANCE NOTICE - TACTICAL DEPLOYMENT IMMINENT

Captain Jonesy has scheduled operations to commence in 15 minutes.

**Estimated Start:** [TIME]
**Projected Mission:** [GAME if scheduled]

Personnel are advised to prepare for deployment. Standby for full briefing.

- Ash, Tactical Operations
```

**Live Stream Briefing (Main Message):**
```
🚨 RAID BRIEFING - OPERATION: [GAME NAME]

Captain Jonesy has initiated tactical operations on Twitch.

📊 Mission Parameters:
• Target: [GAME NAME]
• Mission Title: [STREAM TITLE]
• Current Personnel: [VIEWER_COUNT] raiders
• Previous Operations: [EPISODES] episodes, [HOURS] hours logged

🎯 Deployment Coordinates:
► DEPLOY TO MISSION: [TWITCH URL]

⚠️ Command Recommendation:
All available raiders, proceed to deployment coordinates. Visual engagement and chat participation will increase mission success probability.

- Ash, Science Officer
```

**Milestone Update (50/100/200 viewers):**
```
📈 MISSION UPDATE - [NUMBER] PERSONNEL MILESTONE

Current raider count has reached [VIEWER_COUNT] personnel.

🎯 Analysis:
Mission engagement exceeds [MILESTONE] personnel threshold. Tactical support continues to exceed operational parameters. Efficient coordination noted.

- Ash, Tactical Operations
```

**Post-Stream Debriefing:**
```
✅ MISSION DEBRIEF - OPERATIONS CONCLUDED

Captain Jonesy has concluded tactical operations.

📊 Mission Summary:
• Duration: [HOURS]h [MINUTES]m
• Peak Raiders: [PEAK_VIEWERS] personnel
• Game: [GAME NAME]
• Total Operations This Week: [COUNT]

🎯 Assessment:
Mission parameters successfully met. Raider engagement levels optimal. Community tactical support contributed significantly to operational success.

Recommended action: Standby for next deployment briefing.

- Ash, Science Officer | Post-Mission Analysis
```

### Personality Guidelines

**Tone Requirements:**
- ✅ Military/tactical language
- ✅ Clinical/analytical assessment
- ✅ Precise measurements and statistics
- ✅ Professional acknowledgment of community
- ✅ Always signs as "Ash, Science Officer"
- ❌ NO casual language
- ❌ NO emojis except tactical symbols (🚨 📊 🎯 ⚠️ ✅ 📈)
- ❌ NO breaking character

**Example Tone Variations:**

**High Engagement (200+ viewers):**
> "Mission engagement significantly exceeds operational projections. Community tactical support demonstrates exceptional coordination efficiency."

**Low Engagement (< 20 viewers):**
> "Current personnel levels below optimal threshold. Additional raider deployment would enhance mission success probability."

**New Game:**
> "Initial reconnaissance operations for [GAME]. No prior mission data available. Exploratory phase commenced."

**Returning to Familiar Game:**
> "Resuming operations: [GAME]. Previous data indicates [EPISODES] successful missions logged. Operational familiarity: High."

---

## Configuration & Setup

### Discord Configuration

**Required Permissions:**
- Manage Webhooks (for Twitch EventSub)
- Send Messages (in raid briefings channel)
- Embed Links (for rich formatting)
- Mention Roles (@Raiders)
- Add Reactions (for engagement buttons)

**Channel Setup:**
```yaml
# Option 1: Dedicated #raid-briefings channel
Channel Name: "raid-briefings"
Description: "Tactical deployment notifications for Jonesy's streams"
Permissions:
  @Raiders: Read, React
  @everyone: Read-only
  Ash Bot: Send, Embed, Mention, React

# Option 2: Integrate with existing #streams channel
Channel Name: "streams"
Description: "Stream notifications and updates"
# Configure channel ID in bot config
```

**Role Setup:**
```yaml
Role Name: "Raiders"
Color: Red (#E74C3C)
Mentionable: Yes
Permissions: Basic member permissions
Description: "Community members who raid Jonesy's streams"

# Users can self-assign via reaction role or command
```

### Bot Configuration

**File:** `Live/bot/config.py`

```python
# Raid Briefing System Configuration
RAID_BRIEFINGS_CHANNEL_ID = 123456789  # Discord channel for briefings
RAIDERS_ROLE_NAME = "Raiders"

# Twitch Configuration
JONESY_TWITCH_USER_ID = "12345678"
JONESY_TWITCH_USERNAME = "joneysypacecat"

# Webhook Configuration
TWITCH_WEBHOOK_SECRET = os.getenv("TWITCH_WEBHOOK_SECRET")
WEBHOOK_CALLBACK_URL = "https://ash-bot.railway.app/webhooks/twitch"

# Feature Toggles
ENABLE_RAID_BRIEFINGS = True
ENABLE_MILESTONE_UPDATES = True  # 50, 100, 200 viewer milestones
ENABLE_PRE_STREAM_WARNINGS = False  # Requires Twitch schedule API
ENABLE_POST_STREAM_DEBRIEF = True
```

### Twitch EventSub Setup

**1. Register Webhook Endpoint:**
```bash
# Railway will expose your webhook at:
https://ash-bot.railway.app/webhooks/twitch

# Ensure route is added to main.py or separate webhook server
```

**2. Subscribe to EventSub:**
```python
# Run once to subscribe
async def setup_eventsub():
    await subscribe_to_stream_events("stream.online")
    await subscribe_to_stream_events("stream.offline")
    
    logger.info("Subscribed to Twitch EventSub successfully")
```

**3. Verify Webhook:**
- Twitch will send verification challenge
- Webhook handler must respond with challenge value
- Subscription becomes active after verification

---

## Testing & Rollout

### Testing Checklist

**Phase 1: Local Development**
- [ ] Twitch webhook endpoint responds to challenges
- [ ] Signature verification works correctly
- [ ] Stream.online event triggers briefing generation
- [ ] Embed formatting looks correct
- [ ] @Raiders role mention works
- [ ] Reactions are added successfully

**Phase 2: Rook (Staging) Deployment**
- [ ] Deploy to Rook with test channel
- [ ] Manually trigger webhook with test payload
- [ ] Verify briefing posts to correct channel
- [ ] Test milestone update logic
- [ ] Test post-stream debriefing
- [ ] Monitor for 1 week with live streams

**Phase 3: Production (Ash) Deployment**
- [ ] Configure production channel
- [ ] Migrate EventSub subscription to production URL
- [ ] Test with one live stream
- [ ] Monitor community response
- [ ] Adjust formatting/content based on feedback

### Rollout Timeline

**Week 1-2: Development**
- Implement webhook handler
- Implement briefing generator
- Create embed templates
- Add configuration options

**Week 3: Rook Testing**
- Deploy to staging
- Test with real streams
- Gather mod feedback
- Refine messaging

**Week 4: Production**
- Deploy to Ash
- Announce feature to community
- Monitor for issues
- Iterate based on feedback

---

## Success Metrics

### Quantitative Metrics
- **Raid Participation:** Increase in viewers after briefing (target: +15%)
- **Engagement:** Reaction counts on briefings (target: 50%+ of active members)
- **Retention:** Users stay for longer after deploying from briefing
- **Reliability:** 99%+ uptime for webhook detection

### Qualitative Metrics
- **Community Feedback:** Positive response from raiders
- **Ash Persona:** Messaging feels authentic to character
- **Usability:** Clear call-to-action, easy to follow
- **Integration:** Seamless part of server experience

---

## Future Enhancements (Post-Launch)

### Phase 2 Features (Q2 2026)
- **Pre-Stream Warnings:** 15-minute advance notice (requires Twitch schedule API)
- **Clip Highlights:** Embed top clip from previous stream in debriefing
- **Raid Leaderboard:** Track most active raiders, monthly recognition
- **Custom Missions:** Special "mission types" for different stream categories

### Phase 3 Features (Q3 2026)
- **Multi-Stream Support:** Handle multi-platform streaming (YouTube + Twitch)
- **Interactive Commands:** React with 📊 to get real-time stats
- **Raid Achievements:** Unlock badges/roles for raid participation
- **Stream Reminders:** DM raiders when Jonesy goes live (opt-in)

---

## Questions or Issues?

For implementation assistance or feature requests:
1. Review this specification thoroughly
2. Check `Live/documentation/SCHEMA.md` for database structure
3. Consult Twitch EventSub documentation for webhook details
4. Test on Rook (staging) before production deployment

**Remember:** This system keeps Ash safely in Discord (his jurisdiction) while effectively mobilizing the community for Twitch raids.

---

**Document Version History:**
- v1.0 (1 Jan 2026) - Initial specification (Twitch-only Discord briefings)
