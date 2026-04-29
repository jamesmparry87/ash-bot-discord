"""
API Connection Test Script
Tests YouTube and Twitch API connections without exposing credentials
"""
import os
import sys

import requests


def test_youtube_api():
    """Test YouTube API connection"""
    print("[*] Testing YouTube API...")
    
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        print("[FAIL] YOUTUBE_API_KEY environment variable not set")
        return False
    
    # Test with Jonesy's channel
    channel_id = "UCPoUxLHeTnE9SUDAkqfJzDQ"
    url = f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id={channel_id}&key={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'items' in data and len(data['items']) > 0:
                channel_name = data['items'][0]['snippet']['title']
                print(f"[OK] YouTube API: Working! Found channel: '{channel_name}'")
                return True
            else:
                print("[FAIL] YouTube API: No channel data returned")
                return False
        elif response.status_code == 403:
            print("[FAIL] YouTube API: Access forbidden - check API key validity")
            print(f"   Error: {response.json().get('error', {}).get('message', 'Unknown')}")
            return False
        elif response.status_code == 400:
            print("[FAIL] YouTube API: Bad request - check API key format")
            return False
        else:
            print(f"[FAIL] YouTube API: HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"[FAIL] YouTube API: Connection error - {e}")
        return False


def test_twitch_api():
    """Test Twitch API connection with OAuth"""
    print("\n[*] Testing Twitch API...")
    
    client_id = os.getenv('TWITCH_CLIENT_ID')
    client_secret = os.getenv('TWITCH_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("[FAIL] TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET environment variable not set")
        return False
    
    # Step 1: Get OAuth token
    print("   [*] Requesting OAuth token...")
    token_url = "https://id.twitch.tv/oauth2/token"
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials"
    }
    
    try:
        token_response = requests.post(token_url, data=token_data, timeout=10)
        
        if token_response.status_code != 200:
            print(f"[FAIL] Twitch OAuth: HTTP {token_response.status_code}")
            print(f"   Response: {token_response.text[:200]}")
            return False
        
        token = token_response.json().get('access_token')
        if not token:
            print("[FAIL] Twitch OAuth: No access token received")
            return False
        
        print("   [OK] OAuth token obtained")
        
        # Step 2: Test API with token
        print("   [*] Testing API with channel lookup...")
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}"
        }
        
        # Test with Jonesy's Twitch channel
        user_url = "https://api.twitch.tv/helix/users?login=jonesyspacecat"
        user_response = requests.get(user_url, headers=headers, timeout=10)
        
        if user_response.status_code == 200:
            data = user_response.json()
            if 'data' in data and len(data['data']) > 0:
                display_name = data['data'][0]['display_name']
                print(f"[OK] Twitch API: Working! Found channel: '{display_name}'")
                return True
            else:
                print("[FAIL] Twitch API: No user data returned")
                return False
        else:
            print(f"[FAIL] Twitch API: HTTP {user_response.status_code}")
            print(f"   Response: {user_response.text[:200]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"[FAIL] Twitch API: Connection error - {e}")
        return False


def main():
    """Run all API tests"""
    print("=" * 60)
    print("API Connection Test")
    print("=" * 60)
    print()
    
    youtube_ok = test_youtube_api()
    twitch_ok = test_twitch_api()
    
    print()
    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    print(f"YouTube API: {'[OK] WORKING' if youtube_ok else '[FAIL] FAILED'}")
    print(f"Twitch API:  {'[OK] WORKING' if twitch_ok else '[FAIL] FAILED'}")
    print()
    
    if youtube_ok and twitch_ok:
        print("[SUCCESS] All APIs are working correctly!")
        print("          You can proceed with the sync staging implementation.")
        return 0
    else:
        print("[WARNING] Some APIs are not working.")
        print("          Fix the failing APIs before implementing staging.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
