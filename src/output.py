"""Output: render daily.html + email HTML, send via SMTP."""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jinja2 import Template

from .config import BASE, TEST_MODE, FULLTEST_MODE, UITEST_MODE


# ── Render context ────────────────────────────────────────────────────────────
def build_render_context(run_type, weekend_mode, now, edition,
                          indices_data, commodities_data, fx_data,
                          hist_dates, watchlist_items,
                          market_news_entries, japan_news_entries, hot_markets,
                          portfolio_data=None):
    """Assemble Jinja2 template context dict."""
    if weekend_mode:
        s1_title = 'Daily Markets · Global News'
        s1_sub   = "Weekend Edition — prices reflect Friday's last close"
        s2_title = 'Daily Markets · Japan News'
        s2_sub   = 'Weekend Edition'
    elif run_type == 'morning':
        s1_title = 'Daily Markets · Global Markets'
        s1_sub   = 'US/EU overnight · Japan opens 09:00 JST'
        s2_title = 'Daily Markets · Japan Markets'
        s2_sub   = 'Open preview — 09:00 JST'
    else:
        s1_title = 'Daily Markets · Global Markets'
        s1_sub   = 'EU open · US opens 22:30 JST'
        s2_title = 'Daily Markets · Japan Markets'
        s2_sub   = 'Session recap — closed 15:30 JST'

    return dict(
        edition=edition,
        run_type=run_type,
        weekend_mode=weekend_mode,
        update_date=now.strftime('%Y-%m-%d'),
        update_time=now.strftime('%Y-%m-%d %H:%M:%S'),
        indices=indices_data,
        commodities=commodities_data,
        fx=fx_data,
        hist_dates=hist_dates,
        watchlist=watchlist_items,
        market_news=market_news_entries,
        japan_news=japan_news_entries,
        hot_markets=hot_markets,
        news_section_1_title=s1_title,
        news_section_1_sub=s1_sub,
        news_section_2_title=s2_title,
        news_section_2_sub=s2_sub,
        portfolio=portfolio_data,
    )


# ── HTML rendering ────────────────────────────────────────────────────────────
def render_daily_html(ctx):
    """Render and write docs/daily.html. Returns output path."""
    tmpl = Template(open('daily_template.html', encoding='utf-8').read())
    path = os.path.join(BASE, 'daily.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(tmpl.render(**ctx))
    print(f"[output] daily.html -> {path}")
    return path

def render_email_html(ctx):
    """Render email HTML string."""
    return Template(open('email_template.html', encoding='utf-8').read()).render(**ctx)


# ── Email sending ─────────────────────────────────────────────────────────────
def send_daily_email(email_html, edition, now):
    smtp_host = os.environ.get('SMTP_HOST')
    smtp_port = int(os.environ.get('SMTP_PORT') or '587')
    smtp_user = os.environ.get('SMTP_USER')
    smtp_pass = os.environ.get('SMTP_PASS')
    recipient = os.environ.get('RECIPIENT_EMAIL')

    if not all([smtp_host, smtp_user, smtp_pass, recipient]):
        print("[email] Not configured - set SMTP_HOST, SMTP_USER, SMTP_PASS, RECIPIENT_EMAIL.")
        return

    if FULLTEST_MODE:
        subject = f'[FULLTEST] {edition} {now.strftime("%Y-%m-%d")}'
    elif TEST_MODE:
        subject = f'[TEST] {edition} {now.strftime("%Y-%m-%d %H:%M")}'
    else:
        subject = f'{edition} {now.strftime("%Y-%m-%d")}'

    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = smtp_user
    msg['To']      = recipient
    msg.attach(MIMEText(email_html, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, recipient, msg.as_string())
        print(f"[email] Digest sent to {recipient}")
    except Exception as e:
        print(f"[email] Failed to send: {e}")
