# Weekly Briefings Overview

Currently, Ash sends two weekly scheduled greetings/briefings. Both are generated using the exact same underlying AI function (`generate_weekly_report`), but they serve two distinct purposes and are fed different sets of data.

## 1. Monday Content Sync (`monday_content_sync`)
**Purpose:** Summarize the weekend's or previous week's external media transmissions (YouTube/Twitch syncs). It runs early on Monday morning.
**Current Data Points Passed to AI:**
- `new_content_count`: Number of new videos/VODs published.
- `new_hours`: Total hours of new gameplay/mission data.
- `new_views`: Total new viewer engagements.
- `completed_games`: A list of game series where the final episode was archived.
- `top_video`: The most engaged transmission (title and view count).

## 2. Friday Community Analysis (`friday_community_analysis`)
**Purpose:** Summarize the week's internal Discord community interactions before the weekend operational pause. It runs on Friday morning.
**Current Data Points Passed to AI:**
- `jonesy_message`: The most highly reacted message posted by Captain Jonesy in the past 7 days (includes the message text and reaction count).
- `trivia_recap`: The stats from that week's Trivia Tuesday (includes the winner's ID and the ID of any notable "suboptimal" participant).
- `general_activity`: The total number of messages sent in the primary public channels over the past 7 days.

---

# Available Database Data Points (For Future Enhancements)

If we want to rewrite the templates to be more contextual and specific (and fix the formatting issues properly), we have access to a rich set of data from the PostgreSQL database that we aren't currently feeding into the weekly reports.

**1. Processed Video Clips (Clip Lore)**
- *Data:* Game title, trigger (what caused the event), reaction, outcome, notable quote, emotion category, characters involved.
- *Potential Use:* As you suggested, these make great "Stream Highlights". We could feed 3-5 of the funniest or most dramatic clips processed that week into the **Monday** report to recap stream shenanigans.

**2. Gaming Timeline**
- *Data:* Recently played games, their genres, and completion status.
- *Potential Use:* Ash could provide a timeline update on Friday ("This week, Command personnel engaged in Survival Horror and RPGs...").

**3. Strike System**
- *Data:* Users who have recently received moderation strikes.
- *Potential Use:* A very clinical, passive-aggressive "Friendly reminder of the rules" in the Friday briefing, specifically targeting (or just vaguely mentioning) recent infractions.

**4. Member Statistics**
- *Data:* Active members, playtime, etc.
- *Potential Use:* Calling out the most active crew members of the week in the Friday community analysis.
