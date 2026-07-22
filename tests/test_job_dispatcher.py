import datetime as dt

import job_dispatcher as jd
import schedule_manager as sm


def _rule(name: str, weekday: int, hour: int, minute: int = 0):
    return jd.DispatchRule(
        name=name,
        time=dt.time(hour, minute, tzinfo=sm.TAIWAN_TZ),
        weekdays=(weekday,),
        commands=(("echo", name),),
    )


def test_get_jobs_to_run_finds_due_jobs():
    now = dt.datetime(2025, 1, 1, 6, 0, tzinfo=sm.TAIWAN_TZ)  # Wednesday
    rules = [_rule("daily", now.weekday(), 6)]

    state = {}
    jobs_to_run = jd.get_jobs_to_run(rules, now, state, dt.timedelta(minutes=30))

    assert len(jobs_to_run) == 1
    assert jobs_to_run[0].name == "daily"
    assert jobs_to_run[0].commands == (("echo", "daily"),)


def test_get_jobs_to_run_skips_when_already_run():
    now = dt.datetime(2025, 1, 2, 6, 5, tzinfo=sm.TAIWAN_TZ)  # Thursday
    rule = _rule("daily", now.weekday(), 6)
    state = {"daily": dt.datetime(2025, 1, 2, 6, 1, tzinfo=sm.TAIWAN_TZ).isoformat()}
    jobs_to_run = jd.get_jobs_to_run([rule], now, state, dt.timedelta(minutes=30))

    assert jobs_to_run == []


def test_load_rules_from_config(tmp_path):
    config = tmp_path / "dispatch.json"
    config.write_text(
        """
        [
          {
            "name": "combo",
            "time": "06:00",
            "days": ["sun"],
            "commands": [
              ["echo", "first"],
              "bash scripts/run_weekly_schedule_summary.sh"
            ]
          }
        ]
        """,
        encoding="utf-8",
    )
    rules = jd.load_rules(config)

    assert len(rules) == 1
    rule = rules[0]
    assert rule.name == "combo"
    assert rule.weekdays == (6,)
    assert rule.commands[0] == ["echo", "first"]
    assert rule.commands[1] == ["bash", "-lc", "bash scripts/run_weekly_schedule_summary.sh"]
