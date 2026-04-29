"""
YouTube API Key Diagnostic Script
Helps troubleshoot YouTube API key issues
"""
import os

api_key = os.getenv('YOUTUBE_API_KEY')

print("=" * 60)
print("YouTube API Key Diagnostic")
print("=" * 60)
print()

if not api_key:
    print("[FAIL] YOUTUBE_API_KEY environment variable is NOT set")
    print()
    print("To set it (current terminal session only):")
    print("  set YOUTUBE_API_KEY=your_actual_key_here")
    print()
else:
    print(f"[OK] YOUTUBE_API_KEY is set")
    print(f"     Length: {len(api_key)} characters")
    print(f"     First 10 chars: {api_key[:10]}...")
    print(f"     Last 5 chars: ...{api_key[-5:]}")
    print()
    
    # Check for common issues
    issues = []
    
    if api_key != api_key.strip():
        issues.append("Key has leading/trailing whitespace")
    
    if ' ' in api_key:
        issues.append("Key contains spaces (invalid)")
    
    if '\n' in api_key or '\r' in api_key:
        issues.append("Key contains newline characters")
    
    if len(api_key) < 30:
        issues.append(f"Key seems too short ({len(api_key)} chars, expected ~39)")
    
    if len(api_key) > 50:
        issues.append(f"Key seems too long ({len(api_key)} chars, expected ~39)")
    
    if issues:
        print("[WARNING] Potential issues detected:")
        for issue in issues:
            print(f"  - {issue}")
        print()
        print("Try resetting the environment variable:")
        print("  set YOUTUBE_API_KEY=your_actual_key_here")
    else:
        print("[OK] Key format looks valid")
        print()
        print("If API still fails, the key might be:")
        print("  - Expired or revoked")
        print("  - Not enabled for YouTube Data API v3")
        print("  - Missing required API permissions")
        print()
        print("Check in Google Cloud Console:")
        print("  https://console.cloud.google.com/apis/credentials")

print()
