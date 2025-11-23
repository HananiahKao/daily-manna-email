#!/usr/bin/env python3
"""
Test to verify get_email_title() method works correctly with the new signature.
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_email_titles():
    """Test that both content sources return appropriate email titles with weekday and content title."""
    
    # Test Ezoe content source
    from ezoe_content_source import EzoeContentSource
    ezoe = EzoeContentSource()
    
    # Test different days
    test_cases_ezoe = [
        ("2-1-1", "第一課 第一天", "聖經之旅 | 週一 第一課 第一天"),
        ("2-1-3", "晨興餧養", "聖經之旅 | 週三 晨興餧養"),
        ("2-1-7", "主日信息", "聖經之旅 | 主日信息"),
    ]
    
    for selector, content_title, expected in test_cases_ezoe:
        result = ezoe.get_email_subject(selector, content_title)
        print(f"Ezoe ({selector}): {result}")
        assert result == expected, f"Expected '{expected}', got '{result}'"
    
    # Test Wix content source
    from wix_content_source import WixContentSource
    wix = WixContentSource()
    
    test_cases_wix = [
        ("【週一】", "晨興餧養", "晨興聖言 | 週一"),
        ("【週三】", "信息選讀", "晨興聖言 | 週三"),
        ("【主日】", "主日信息", "晨興聖言 | 主日"),
    ]
    
    for selector, content_title, expected in test_cases_wix:
        result = wix.get_email_subject(selector, content_title)
        print(f"Wix ({selector}): {result}")
        assert result == expected, f"Expected '{expected}', got '{result}'"
    
    print("\n✅ All tests passed!")
    print("\nExample email subjects:")
    print("- Ezoe: '聖經之旅 | 週三 晨興餧養 | 2025-11-23'")
    print("- Wix:  '晨興聖言 | 週一 | 2025-11-23'")
    return True

if __name__ == "__main__":
    try:
        test_email_titles()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
