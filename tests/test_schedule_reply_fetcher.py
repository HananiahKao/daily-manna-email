import datetime as dt

import pytest

import schedule_reply_fetcher as srf
import schedule_reply_processor as srp

from email.message import EmailMessage


def test_extract_text_body_prefers_plain_text():
    msg = EmailMessage()
    msg['From'] = 'Admin <admin@example.com>'
    msg['Subject'] = 'Re: Weekly Schedule'
    msg.set_content('Plain body line\n\n[AAA111] skip travel')
    msg.add_alternative('<p>HTML body</p>', subtype='html')

    body = srf.extract_text_body(msg)

    assert '[AAA111]' in body
    assert 'HTML' not in body


def test_build_confirmation_email_contains_outcomes(tmp_path):
    outcome = srp.InstructionOutcome(
        token='AAA111',
        verb='skip',
        status='applied',
        message='marked as skipped',
        date=dt.date(2025, 6, 2),
    )
    record = srf.ReplyProcessingRecord(
        uid='123',
        subject='Re: Weekly Schedule',
        from_address='admin@example.com',
        message_id='<abc@id>',
        received_at=dt.datetime(2025, 6, 1, 8, tzinfo=dt.timezone.utc),
        instruction_count=1,
        applied_count=1,
        error_count=0,
        schedule_changed=True,
        confirmation_sent=False,
        outcomes=[outcome],
    )

    subject, text_body, html_body = srf.build_confirmation_email(
        record,
        subject_prefix='[DailyManna]',
        schedule_path=tmp_path / 'ezoe_schedule.json',
    )

    assert subject.startswith('[DailyManna] Reply Outcome')
    assert 'AAA111' in text_body
    assert 'marked as skipped' in text_body
    assert '<td>AAA111</td>' in html_body


def test_imap_config_from_env_requires_credentials(monkeypatch):
    monkeypatch.delenv('IMAP_USER', raising=False)
    monkeypatch.delenv('IMAP_PASSWORD', raising=False)
    monkeypatch.setenv('SMTP_USER', 'admin@example.com')
    monkeypatch.setenv('SMTP_PASSWORD', 'secret')
    monkeypatch.setenv('ADMIN_SUMMARY_TO', 'admin@example.com')

    config = srf.ImapConfig.from_env()

    assert config.username == 'admin@example.com'
    assert 'admin@example.com' in config.allowed_senders
