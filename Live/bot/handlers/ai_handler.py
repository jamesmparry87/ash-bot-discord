"""
AI Handler Module

Handles AI integration and response processing for the Discord bot.
Supports Gemini API with dual-project architecture.
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..config import (
    ERROR_MESSAGE,
    FALLBACK_GREETINGS,
    FALLBACK_STATUS_RESPONSES,
    FALLBACK_WELCOME_RESPONSES,
    GUILD_ID,
    JAM_USER_ID,
    JONESY_USER_ID,
    MEMBER_ROLE_IDS,
    POPS_ARCADE_USER_ID,
    GEMINI_LIVE_API_KEY,
    GEMINI_BATCH_API_KEY,
    MAX_CONVERSATION_TURNS,
    INACTIVITY_TTL_MINUTES,
)
from ..database import get_database
from ..persona.context_builder import build_ash_context
from ..persona.examples import ASH_FEW_SHOT_EXAMPLES
from ..persona.prompts import ASH_SYSTEM_INSTRUCTION
import google.genai as genai
from google.genai import types

# AI Configuration
gemini_live_client: Any = None
gemini_batch_client: Any = None
ai_enabled = False
ai_status_message = "Offline"
primary_ai = "gemini"

# Sliding window tracking
conversation_history: Dict[int, List[Dict[str, Any]]] = {}
conversation_last_active: Dict[int, datetime] = {}

pacific_tz = ZoneInfo("US/Pacific")

db: Any = None

def _get_db():
    global db
    if db is None:
        db = get_database()
    return db

def initialize_ai():
    global gemini_live_client, gemini_batch_client, ai_enabled, ai_status_message
    try:
        if GEMINI_LIVE_API_KEY:
            gemini_live_client = genai.Client(api_key=GEMINI_LIVE_API_KEY)
            ai_enabled = True
            ai_status_message = "Online (Live Client)"
        if GEMINI_BATCH_API_KEY:
            gemini_batch_client = genai.Client(api_key=GEMINI_BATCH_API_KEY)
    except Exception as e:
        print(f"Failed to initialize AI: {e}")
        ai_enabled = False
        ai_status_message = f"Error: {str(e)}"

def safe_initialize_ai():
    try:
        initialize_ai()
        return True
    except Exception:
        return False

async def safe_initialize_ai_async():
    return await asyncio.to_thread(safe_initialize_ai)

def get_ai_status() -> str:
    return ai_status_message

def toggle_ai_system() -> bool:
    global ai_enabled, ai_status_message
    if not gemini_live_client:
        ai_status_message = "Cannot enable: No API key configured"
        return False
    ai_enabled = not ai_enabled
    ai_status_message = "Online" if ai_enabled else "Manually Disabled"
    return ai_enabled

async def detect_user_context(user_id: int, member_obj=None, bot=None) -> Dict[str, Any]:
    # Hardcoded user overrides
    if user_id == JONESY_USER_ID:
        return {"clearance": "COMMANDING_OFFICER", "relationship": "COMMANDING_OFFICER"}
    elif user_id == JAM_USER_ID:
        return {"clearance": "CREATOR", "relationship": "CREATOR"}
    elif user_id == POPS_ARCADE_USER_ID:
        return {"clearance": "MODERATOR", "relationship": "ANTAGONISTIC"}
    return {"clearance": "STANDARD", "relationship": "NEUTRAL"}

def filter_ai_response(response: str) -> str:
    # Filter discord formatting and markdown if needed
    if not response:
        return ""
    # Discord Message Sanitisation
    response = re.sub(r'<@!?([0-9]+)>', r'@User', response)
    response = re.sub(r'<:([a-zA-Z0-9_]+):[0-9]+>', r'::', response)
    return response.strip()

def _update_sliding_window(user_id: int, role: str, content: str):
    now = datetime.now(pacific_tz)
    # Check TTL
    if user_id in conversation_last_active:
        if now - conversation_last_active[user_id] > timedelta(minutes=INACTIVITY_TTL_MINUTES):
            conversation_history[user_id] = []
            
    if user_id not in conversation_history:
        conversation_history[user_id] = []
        
    conversation_history[user_id].append({"role": role, "parts": [{"text": content}]})
    conversation_last_active[user_id] = now
    
    # Trim to max turns
    if len(conversation_history[user_id]) > MAX_CONVERSATION_TURNS * 2:
        conversation_history[user_id] = conversation_history[user_id][-(MAX_CONVERSATION_TURNS * 2):]

async def call_ai_with_rate_limiting(prompt: str, context: Optional[str] = None, user_name: Optional[str] = None, priority: str = "medium", user_id: Optional[int] = None, context_data: Optional[Dict] = None) -> Tuple[Optional[str], str]:
    if not ai_enabled or not gemini_live_client:
        return random.choice(FALLBACK_GREETINGS), "fallback"
        
    try:
        sys_instruction = ASH_SYSTEM_INSTRUCTION
        if context:
            sys_instruction += f"\n\n[ADDITIONAL CONTEXT]\n{context}"
        
        config = types.GenerateContentConfig(
            system_instruction=sys_instruction,
            temperature=0.75,
            max_output_tokens=500
        )
        
        if user_id:
            _update_sliding_window(user_id, "user", prompt)
            contents = conversation_history[user_id]
        else:
            contents = [{"role": "user", "parts": [{"text": prompt}]}]
            
        response = await asyncio.to_thread(
            gemini_live_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=contents,
            config=config
        )
        
        reply = filter_ai_response(response.text)
        if user_id:
            _update_sliding_window(user_id, "model", reply)
            
        return reply, "success"
    except Exception as e:
        print(f"AI Call error: {e}")
        return ERROR_MESSAGE, "error"

async def call_ai_for_generation(prompt: str, system_instruction: str = None, temperature: float = 0.7, max_tokens: int = 1000) -> Tuple[Optional[str], str]:
    if not ai_enabled or not gemini_live_client:
        return None, "offline"
    try:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction or ASH_SYSTEM_INSTRUCTION,
            temperature=temperature,
            max_output_tokens=max_tokens
        )
        response = await asyncio.to_thread(
            gemini_live_client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=config
        )
        return filter_ai_response(response.text), "success"
    except Exception as e:
        print(f"Generation error: {e}")
        return None, "error"

async def upload_and_analyze_media(file_path: str, prompt: str, is_batch: bool = True) -> Tuple[Optional[str], str]:
    client = gemini_batch_client if is_batch and gemini_batch_client else gemini_live_client
    if not client:
        return None, "offline"
        
    try:
        uploaded_file = await asyncio.to_thread(
            client.files.upload, file=file_path
        )
        
        config = types.GenerateContentConfig(
            temperature=0.4,
            response_mime_type="application/json"
        )
        
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[uploaded_file, prompt],
            config=config
        )
        
        await asyncio.to_thread(client.files.delete, name=uploaded_file.name)
        
        return response.text, "success"
    except Exception as e:
        print(f"Media analysis error: {e}")
        return None, "error"

async def generate_contextual_trivia(category: str, difficulty: str, context: Optional[str] = None) -> Tuple[Optional[str], str]:
    prompt = f"Generate a {difficulty} trivia question about {category}. Provide the question and correct answer."
    if context:
        prompt += f" Context: {context}"
    return await call_ai_for_generation(prompt, temperature=0.7)

async def create_ai_announcement_content(topic: str, context: Optional[str] = None) -> Tuple[Optional[str], str]:
    prompt = f"Write an announcement about {topic}."
    if context:
        prompt += f" Context: {context}"
    return await call_ai_for_generation(prompt, temperature=0.75)

async def generate_weekly_report(stats: Dict[str, Any]) -> Tuple[Optional[str], str]:
    prompt = f"Generate a weekly report summarizing these stats: {stats}"
    return await call_ai_for_generation(prompt, temperature=0.7)

initialize_ai()
