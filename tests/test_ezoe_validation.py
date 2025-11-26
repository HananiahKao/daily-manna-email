import unittest
from unittest.mock import patch, MagicMock
import datetime as dt
from ezoe_week_scraper import get_volume_lessons
from ezoe_content_source import EzoeContentSource
from schedule_manager import ensure_date_range, Schedule, ScheduleEntry

# Mock HTML for volume page
VOLUME_HTML = """
<html>
<body>
<div class="main">
    <p>第一课 <a href="2264-2-1.html">Lesson 1</a></p>
    <p>第二课 <a href="2264-2-2.html">Lesson 2</a></p>
    <p>第三课 <a href="2264-2-3.html">Lesson 3</a></p>
    
    <!-- Non-lesson resources -->
    <p>以色列出埃及至迦南路线图 <a href="2264-2-19.html">Map 1</a></p>
    <p>帐幕平面图 <a href="2264-2-20.html">Map 2</a></p>
    <p>以色列子民安营图 <a href="2264-2-21.html">Map 3</a></p>
</div>
</body>
</html>
"""

class TestEzoeValidation(unittest.TestCase):
    @patch('ezoe_week_scraper._fetch')
    def test_get_volume_lessons(self, mock_fetch):
        mock_fetch.return_value = VOLUME_HTML
        
        lessons = get_volume_lessons(2)
        
        # Should include 1, 2, 3
        self.assertIn(1, lessons)
        self.assertIn(2, lessons)
        self.assertIn(3, lessons)
        
        # Should NOT include 19, 20, 21
        self.assertNotIn(19, lessons)
        self.assertNotIn(20, lessons)
        self.assertNotIn(21, lessons)
        
        # Verify length
        self.assertEqual(len(lessons), 3)

    @patch('ezoe_week_scraper._fetch')
    def test_schedule_rollover(self, mock_fetch):
        # Setup mock to return lessons 1-3 only
        mock_fetch.return_value = VOLUME_HTML
        
        source = EzoeContentSource()
        schedule = Schedule()
        
        # Start with lesson 3, day 7 (last day of last valid lesson)
        # Next should be lesson 4, day 1 -> INVALID -> Should roll over to Volume 3, Lesson 1
        
        start_date = dt.date(2023, 1, 1) # Sunday
        # Pre-populate schedule with last entry
        schedule.upsert_entry(ScheduleEntry(start_date, "2-3-7"))
        
        # Ensure next week (Monday to Sunday)
        next_monday = start_date + dt.timedelta(days=1)
        next_sunday = next_monday + dt.timedelta(days=6)
        
        # Mock fetch for volume 3 as well (empty or valid, doesn't matter for the rollover trigger)
        # But we need to make sure validate_lesson_exists(2, 4) returns False.
        # It calls get_volume_lessons(2), which returns [1, 2, 3]. So 4 is not in it. Correct.
        
        ensure_date_range(schedule, source, next_monday, next_sunday)
        
        # Check the entry for next Monday
        entry = schedule.get_entry(next_monday)
        self.assertIsNotNone(entry)
        
        # Expected: 3-1-1 (Volume 3, Lesson 1, Day 1)
        # Because 2-4-1 is invalid.
        self.assertEqual(entry.selector, "3-1-1")
        
        # Check Tuesday
        entry_tue = schedule.get_entry(next_monday + dt.timedelta(days=1))
        self.assertEqual(entry_tue.selector, "3-1-2")

if __name__ == '__main__':
    unittest.main()
