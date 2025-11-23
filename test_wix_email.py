#!/usr/bin/env python3
"""
Test script to send an email using the Wix content source.
Note: Source .env externally before running this script.
"""
import os
import sys

# Import the content source and email sender
from wix_content_source import WixContentSource
import sjzl_daily_email as sjzl

def main():
    # Get the weekday selector (default to Monday)
    selector = os.getenv('TEST_SELECTOR', '【週一】')
    
    print(f"Testing Wix content source with selector: {selector}")
    print("-" * 60)
    
    # Create content source
    src = WixContentSource()
    
    # Fetch content
    print("Fetching content from Wix...")
    try:
        content = src.get_daily_content(selector)
        print(f"✓ Content fetched successfully")
        print(f"  Title: {content.title}")
        print(f"  HTML length: {len(content.html_content)} chars")
        print(f"  Plain text length: {len(content.plain_text_content)} chars")
        print(f"  Has 晨興餧養: {'晨興餧養' in content.html_content}")
        print(f"  Has 信息選讀: {'信息選讀' in content.html_content}")
        print()
        
        # Prepare email
        subject = f"[TEST] 晨興聖言 - {content.title}"
        
        # Show preview
        print("Email preview:")
        print(f"  Subject: {subject}")
        print(f"  To: {os.getenv('EMAIL_TO')}")
        print(f"  From: {os.getenv('EMAIL_FROM')}")
        print()
        print("First 500 chars of HTML content:")
        print(content.html_content[:500])
        print()
        
        # Send email
        print("Sending email...")
        sjzl.send_email(subject, content.plain_text_content, html_body=content.html_content)
        print("✓ Email sent successfully!")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
