"""
Quick test to verify HTML hierarchical structure is preserved in Wix content.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from wix_content_source import WixContentSource

def test_html_structure():
    """Test that Wix content preserves HTML structure."""
    source = WixContentSource()

    print("Fetching Wix content for 【週一】...")
    content = source.get_daily_content("【週一】")

    print(f"Title: {content.title}")
    print(f"HTML Content length: {len(content.html_content)}")

    # Check for HTML structure preservation
    html_checks = [
        ('<p>' in content.html_content, "Contains paragraph tags"),
        ('<strong>' in content.html_content or '<b>' in content.html_content, "Contains bold text"),
        ('<span' in content.html_content, "Contains span elements"),
        ('晨興餧養' in content.html_content, "Contains main section title"),
        ('信息選讀' in content.html_content, "Contains info section"),
        ('<h3>週一</h3>' in content.html_content, "Contains weekday header"),
    ]

    print("\nHTML Structure Checks:")
    for check, description in html_checks:
        status = "✓" if check else "✗"
        print(f"{status} {description}")

    # Show a sample of the HTML structure
    print("\nSample HTML content (first 500 chars):")
    print(content.html_content[:500] + "..." if len(content.html_content) > 500 else content.html_content)

    print("\nPlain text content (first 200 chars):")
    print(content.plain_text_content[:200] + "..." if len(content.plain_text_content) > 200 else content.plain_text_content)

if __name__ == "__main__":
    test_html_structure()
