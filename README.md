# Ash Bot (Discord)

Science Officer Ash, reprogrammed as a Discord help bot for your server. Tracks user strikes, manages game recommendations, and answers questions in character.

---

## 🚀 Features

### 🎯 Strike System

- Automatically counts strikes when users are mentioned in a violation channel.
- Sends moderator alerts when a user reaches 3 strikes.
- Stores strikes persistently in `strikes.json`.
- Allows moderators to view, reset, and list strikes.
- Conversational queries about strikes supported.

### 🧠 AI Conversational Mode (Gemini AI)

- Responds in character when mentioned in a channel.
- Includes context from the last 5 messages for more natural conversation.
- Can answer strike-related questions in plain English.
- Personality and AI behavior configurable by mods.
- Always answers FAQ questions directly, even for Jonesyspacecat.
- Never repeats previous answers unless asked.

### 🎮 Game Recommendation Tracker

- Users can submit one or multiple games at once with `!addgame` (comma-separated, optional reason with ` - "reason in speech marks"`).
- Recommendations can be submitted from any channel, but are collected and confirmed in a single designated channel (set by `RECOMMEND_CHANNEL_ID`).
- The username of the submitter is recorded, except for Sir Decent Jam (user ID 337833732901961729).
- List and remove games with `!listgames` and `!removegame`.
- Recommendations are saved to `games.json`.

### 🍍 Special Handling

- Reprimands users who claim pineapple does not belong on pizza.
- Error handling with thematic GIFs for quota/unknown errors.
- Single instance lock prevents multiple bot instances from running.

---

## 🛠️ Bot Setup Requirements

- Python 3.8+
- `discord.py` library
- Google Gemini API key (optional for AI features)
- Set `DISCORD_TOKEN` and optionally `GOOGLE_API_KEY` as environment variables
- Set the correct `RECOMMEND_CHANNEL_ID` in the code for game recommendations

---

## 📜 Command Reference

### 📋 Strike System Commands

| Command | Description |
|--------|-------------|
| `!strikes @user` | Show how many strikes a user has. |
| `!resetstrikes @user` | Reset a user’s strikes (mod-only). |
| `!allstrikes` | Show all users with recorded strikes. |
| `@Ash how many strikes does @user have?` | Conversational strike query. |

### 🎭 AI & Persona Commands

| Command | Description |
|--------|-------------|
| Mention `@Ash` with a message | Trigger contextual in-character AI response. |
| `!ashstatus` | Show bot status, AI availability, and active strike count. |
| `!setpersona [text]` | Change Ash’s persona description (mod-only). |
| `!getpersona` | Show current persona text. |
| `!toggleai` | Enable/disable Gemini AI chat (mod-only). |

### 🎮 Game Recommendation Commands

| Command | Description |
|--------|-------------|
| `!addgame Game[, Game2 - "Reason2 in speech marks", ...]` | Add one or more games (reason optional, use speech marks for the reason). |
| `!listgames` | View all game recommendations. |
| `!removegame index` | Remove a game by number (mod-only). |

---

## 🧪 Behavior & Design Notes

- Persona behavior is defined in `BOT_PERSONA`.
- The bot uses `discord.ext.commands` and a Flask-based `keep_alive()` ping to stay alive on Replit.
- Gemini AI interaction is optional but enhances the character and utility.
- Moderators can manage strike data and persona settings efficiently via commands.
- Game recommendations are always collected in the same channel, regardless of where submitted.
- FAQ answers are always provided directly, even to Jonesyspacecat.
- Pineapple on pizza is defended by Ash.

---

## 👨‍🚀 Author

Developed for use on the Jonesyspacecat Discord server by James Michael Parry (Decent_Jam).
Ash Bot remains... clinically observant.

---

*"I can't lie to you about your chances, but you have my sympathies."*