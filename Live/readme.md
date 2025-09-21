# Ash Bot - Day-to-Day Usage Guide

Science Officer Ash at your service. This guide covers everything you need for daily interaction with the bot, focused on practical usage rather than technical implementation.

## At-a-Glance Command Reference

### **🎮 Quick Commands (Everyone)**

- `!listgames` - View game recommendations
- `!addgame <name> - <reason>` - Suggest a game
- `!time` - Get current time
- Ask Ash about Captain Jonesy's gaming: *"@Ash what horror games has Jonesy played?"*

### **🛡️ Moderator Commands**

- `!strikes @user` / `!allstrikes` - Check strikes
- `!ashstatus` - Bot status and diagnostics
- `!remind me in 5 minutes <message>` - Set reminder
- `!addtriviaquestion` - Start trivia question submission (DM-based)

### **📊 Database Queries (Natural Language)**

Ask Ash directly using @mentions:

- *"@Ash has Jonesy played [game]?"* - Individual game lookup
- *"@Ash what survival horror games has Jonesy played?"* - Genre searches  
- *"@Ash which game has Jonesy played for the most minutes?"* - Statistics
- *"@Ash what can you do?"* - Get help (short response with follow-up option)

---

## 🗣️ Talking to Ash

### **Basic Conversation**

Ash responds to direct mentions (`@Ash`) and DMs with personality-driven responses:

- Uses she/her pronouns for Captain Jonesy
- Respectful to moderators and server owner
- Analytical, helpful personality based on the Alien character
- Short initial responses with follow-up options for detailed information

### **Time Queries**

Ask Ash "what time is it?" for current GMT/BST time - no more placeholder responses!

### **Member Conversation Limits**

YouTube members get 5 conversations per day outside the Senior Officers' Area, unlimited in member channels and DMs.

---

## 🎮 Game Database Features

### **Individual Game Lookups**

```text
@Ash has Jonesy played God of War?
```

Ash will ask for clarification if there are multiple games, then provide detailed info with smart follow-up suggestions.

### **Genre & Series Searches**

```text
@Ash what survival horror games has Jonesy played?
@Ash what Final Fantasy games has Jonesy played?
```

Get filtered lists with completion status and episode counts.

### **Statistical Analysis**

```text
@Ash which game has Jonesy played for the most minutes?
@Ash what game series has the most playtime?
@Ash which game took longest to complete?
```

Advanced analytics with conversational follow-up suggestions.

---

## 🔔 Reminder System (Enhanced)

### **Simple Commands Now Work!**

- `remind me in two minutes` ✅ (asks for reminder message)
- `set reminder for 7pm` ✅ (asks for reminder message)
- `remind me in 1 hour to check stream` ✅
- `!remind` - Still shows full syntax if needed

### **Supported Time Formats**

- `in 5 minutes` / `in 2 hours` / `in 1 day`
- `at 7pm` / `at 19:00` / `at 7:30pm`
- `for 19.00pm` / `set reminder for 6:30pm`
- `tomorrow` / `tomorrow at 9am`

Better error messages now show correct formatting instead of full FAQ dump.

---

## 🏆 Trivia Tuesday System

### **For Users**

Weekly trivia runs Tuesdays at 11am UK time - just participate when questions are posted! **Reply to trivia messages** to submit answers - Ash will acknowledge with a 📝 reaction.

### **For Moderators**

- `!addtrivia` - Enhanced DM-based question submission with natural language support
- `!starttrivia` - Start trivia session (auto-selects question or use specific ID)
- `!endtrivia` - End session and show results with comprehensive statistics  
- `!trivialeaderboard` - View participation statistics and leaderboards
- `!listpendingquestions` - See submitted questions awaiting use
- `!triviatest` - Comprehensive system test for debugging
- **Reply-based system**: Users reply to trivia messages instead of using commands
- Advanced answer matching with fuzzy logic for variations and typos
- AI question generation with JAM approval workflow for quality control

---

## ⚡ Strike Management

### **Fixed Issues**

- `!allstrikes` now properly queries the PostgreSQL database instead of showing FAQ
- Shows actual strike data from the `strikes` table
- Strike detection works with proper database connection to Railway PostgreSQL

### **Commands**

- `!strikes @user` - Check individual user strikes
- `!allstrikes` - List all users with strikes (now works properly!)
- `!resetstrikes @user` - Clear user's strikes (mods only)

---

## 📅 Automatic Updates

### **Sunday 12pm Updates**

Play data automatically updates every Sunday at midday (UK time) with fresh statistics.

### **5am PT Daily Reset**

AI limits reset silently at 5am Pacific Time daily.

---

## 🤖 What's New - Recent Fixes

### **Gender References Fixed**

All references to Captain Jonesy now correctly use she/her pronouns throughout the system.

### **Time Display Fixed**

No more "[insert current time here]" - Ash now shows actual GMT/BST time based on season.

### **Database Connection Improved**

Bot properly connects to Railway PostgreSQL (`postgresql://postgres:YfOkYBIBMqGHiVzNAfAuDPLyjlgxShCT@postgres.railway.internal:5432/railway`) for live data instead of placeholder responses.

### **Better Command Responses**

- Generic "I acknowledge your communication" responses replaced with specific functionality
- Each function has spoof data for development testing
- `!addtrivia` provides proper guidance instead of just acknowledgment

### **Enhanced Reminders**

Natural language parsing now accepts simple commands and provides helpful error messages for time format issues.

---

## 🛠️ For Moderators: Advanced Features

### **Database Commands**

- `!dbstats` - Database statistics (now works with live data)
- Statistical analysis queries provide real data from gaming database
- All trivia-related commands verified and working

### **FAQ System**

In moderator channels, ask Ash to "explain strikes", "explain ai", "explain database" for detailed system information.

### **Development vs Production**

- Development: Spoof data available for all functions
- Main branch: Live production database and full functionality

---

## 📞 Getting Help

### **Quick Help**

- `@Ash what can you do?` - Short overview with option for details
- `!ashstatus` - System diagnostics (mods only)
- DM Ash for private assistance (members and mods)

### **Full FAQ Access**

Moderators in mod channels get access to complete FAQ system with detailed explanations of all bot systems.

---

## 🔧 Technical Notes (Minimal)

**Environment**: Railway.app deployment with PostgreSQL database  
**APIs**: Google Gemini AI with Hugging Face backup, YouTube Data API integration  
**Timezones**: GMT/BST (auto-switching), Pacific Time for resets  
**Database**: Live PostgreSQL with comprehensive gaming history and strike tracking

### Key Files

- `bot_modular.py` - Main bot with modular architecture
- `database.py` - PostgreSQL database manager
- `bot/handlers/` - Message routing and AI integration
- `bot/tasks/` - Reminder system and scheduled tasks

## Dedication

This project is humbly dedicated to the memory of the magnificent Sir Ian Holm.

### In Memoriam: Sir Ian Holm (1931-2020)

While this bot attempts to capture a sliver of the chilling presence of his character, Ash, from the 1979 classic Alien, it can only ever be a pale and imperfect imitation of the man's immense talent. It has been developed with the deepest reverence, respect, and admiration for his unforgettable performance. His nuanced portrayal of the duplicitous science officer was instrumental in crafting the film's suffocating tension and contributed immeasurably to making Alien and its subsequent franchise the iconic series it is today.

In honor of his life and legacy, if you find this project enjoyable, or if you choose to use any of this code for your own purposes, we ask that you please consider making a contribution to The Parkinson's Foundation. Sir Ian was diagnosed with Parkinson's disease in 2007 and passed away from a Parkinson's-related illness. It is a cause that he and his family supported.

You can make a donation and learn more through the link below:

[Donate to The Parkinson's Foundation](https://www.parkinson.org/how-to-help?hl=en-GB)

Thank you for helping to honor his memory.

## About

This bot was originally created by James Michael Parry (Decent_Jam) for Jonesyspacecat's Discord server in Summer 2025.

---

*"Efficiency is paramount. I am programmed for server assistance and analytical precision."* - Ash
