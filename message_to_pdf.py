#!/usr/bin/env python3
"""
Message to PDF Exporter
Converts text message conversations to organized PDF files with timestamps.

Supported input formats:
  - WhatsApp export:   MM/DD/YYYY, HH:MM AM/PM - Sender: Message
  - Bracket format:    [YYYY-MM-DD HH:MM:SS] Sender: Message
  - JSON format:       [{"sender": "...", "timestamp": "...", "message": "..."}]

Usage:
  python3 message_to_pdf.py conversation.txt
  python3 message_to_pdf.py conversation.txt -o output.pdf -t "My Chat"
  cat conversation.txt | python3 message_to_pdf.py -
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Message:
    """Represents a single chat message."""

    def __init__(self, sender: str, timestamp, text: str):
        self.sender = sender
        self.timestamp = timestamp  # datetime or None
        self.text = text

    def __repr__(self):
        return f"Message({self.sender!r}, {self.timestamp}, {self.text[:30]!r})"


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

_TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
]


def _parse_timestamp(ts_str: str):
    """Try multiple formats to parse a timestamp string. Returns datetime or None."""
    ts_str = ts_str.strip()
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


def _accumulate(messages: list, current) -> list:
    if current is not None:
        messages.append(current)
    return messages


def parse_whatsapp(content: str) -> list:
    """
    Parse WhatsApp exported chat format.
    Examples:
      12/25/2023, 10:30 AM - Alice: Hello!
      12/25/2023, 10:30 - Bob: Hi there
    """
    messages = []
    # Pattern covers both 12h (AM/PM) and 24h times
    pattern = re.compile(
        r"(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AP]M)?)\s*-\s*([^:]+):\s*(.*)"
    )
    current = None
    for line in content.splitlines():
        m = pattern.match(line)
        if m:
            _accumulate(messages, current)
            date_str, time_str, sender, text = m.groups()
            combined = f"{date_str}, {time_str}".strip()
            ts = None
            for fmt in ["%m/%d/%Y, %I:%M %p", "%m/%d/%Y, %H:%M",
                        "%m/%d/%Y, %I:%M:%S %p", "%m/%d/%Y, %H:%M:%S"]:
                try:
                    ts = datetime.strptime(combined, fmt)
                    break
                except ValueError:
                    continue
            current = Message(sender.strip(), ts, text.strip())
        elif current and line.strip():
            current.text += "\n" + line.strip()

    _accumulate(messages, current)
    return messages


def parse_bracket_format(content: str) -> list:
    """
    Parse [timestamp] Sender: message format.
    Example:
      [2024-01-15 10:30:00] Alice: Hey, how are you?
    """
    messages = []
    pattern = re.compile(r"\[([^\]]+)\]\s+([^:]+):\s*(.*)")
    current = None
    for line in content.splitlines():
        m = pattern.match(line)
        if m:
            _accumulate(messages, current)
            ts_str, sender, text = m.groups()
            current = Message(sender.strip(), _parse_timestamp(ts_str), text.strip())
        elif current and line.strip():
            current.text += "\n" + line.strip()

    _accumulate(messages, current)
    return messages


def parse_json_format(content: str) -> list:
    """
    Parse JSON array of message objects.
    Expected keys (flexible):
      sender / from / name / author
      timestamp / time / date / datetime
      message / text / content / body
    """
    data = json.loads(content)
    if isinstance(data, dict):
        # Allow {"messages": [...]} wrapper
        data = data.get("messages", data.get("conversation", [data]))

    messages = []
    for item in data:
        # Resolve sender
        sender = (
            item.get("sender")
            or item.get("from")
            or item.get("name")
            or item.get("author")
            or "Unknown"
        )
        # Resolve timestamp
        ts_str = (
            item.get("timestamp")
            or item.get("time")
            or item.get("date")
            or item.get("datetime")
            or ""
        )
        ts = _parse_timestamp(str(ts_str)) if ts_str else None
        # Resolve text
        text = (
            item.get("message")
            or item.get("text")
            or item.get("content")
            or item.get("body")
            or ""
        )
        messages.append(Message(str(sender), ts, str(text)))

    return messages


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(content: str) -> str:
    """Auto-detect message format from content."""
    snippet = content.strip()
    # JSON?
    if snippet.startswith(("[", "{")):
        try:
            json.loads(snippet)
            return "json"
        except json.JSONDecodeError:
            pass
    # WhatsApp?
    if re.search(r"\d{1,2}/\d{1,2}/\d{2,4},\s*\d{1,2}:\d{2}", snippet[:300]):
        return "whatsapp"
    # Bracket?
    if re.search(r"\[\d{4}-\d{2}-\d{2}", snippet[:300]):
        return "bracket"
    return "bracket"


def parse_messages(content: str, fmt: str = None) -> list:
    if not fmt:
        fmt = detect_format(content)
    parsers = {
        "json": parse_json_format,
        "whatsapp": parse_whatsapp,
        "bracket": parse_bracket_format,
    }
    return parsers.get(fmt, parse_bracket_format)(content)


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------

# Bubble background colours cycling per sender
_BUBBLE_COLORS = [
    colors.HexColor("#DCF8C6"),  # green (sender 0)
    colors.HexColor("#FFFFFF"),  # white (sender 1)
    colors.HexColor("#E8D5FF"),  # lavender
    colors.HexColor("#FFE8C8"),  # peach
    colors.HexColor("#C8EEFF"),  # sky blue
    colors.HexColor("#FFD6D6"),  # rose
]

_SENDER_LABEL_COLORS = [
    colors.HexColor("#1A9E4A"),
    colors.HexColor("#1565C0"),
    colors.HexColor("#7B1FA2"),
    colors.HexColor("#E65100"),
    colors.HexColor("#00838F"),
    colors.HexColor("#C62828"),
]

_PAGE_W = letter[0]
_MARGIN = 0.75 * inch
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_BUBBLE_W = _CONTENT_W * 0.78   # bubble takes ~78% of content width
_OFFSET_W = _CONTENT_W - _BUBBLE_W  # push-over for right-aligned bubbles


def _hex(c: colors.HexColor) -> str:
    r = int(c.red * 255)
    g = int(c.green * 255)
    b = int(c.blue * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def export_to_pdf(messages: list, output_path: str, title: str = "Conversation Export"):
    """Render messages to a PDF file."""

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=_MARGIN,
        leftMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
    )

    base = getSampleStyleSheet()

    # --- Shared styles ---
    title_style = ParagraphStyle(
        "ConvTitle",
        parent=base["Title"],
        fontSize=20,
        textColor=colors.HexColor("#1A1A2E"),
        spaceAfter=4,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "ConvSubtitle",
        parent=base["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#888888"),
        spaceAfter=18,
        alignment=TA_CENTER,
    )
    date_sep_style = ParagraphStyle(
        "DateSep",
        parent=base["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
        spaceBefore=14,
        spaceAfter=6,
    )
    sender_style = ParagraphStyle(
        "SenderName",
        parent=base["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
        spaceAfter=1,
        spaceBefore=0,
    )
    msg_style = ParagraphStyle(
        "MsgText",
        parent=base["Normal"],
        fontSize=11,
        leading=15,
        spaceAfter=0,
    )
    ts_style = ParagraphStyle(
        "Timestamp",
        parent=base["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#999999"),
        alignment=TA_RIGHT,
        spaceBefore=2,
    )

    # --- Build sender maps ---
    senders = list(dict.fromkeys(m.sender for m in messages))
    bubble_color = {s: _BUBBLE_COLORS[i % len(_BUBBLE_COLORS)] for i, s in enumerate(senders)}
    label_color = {s: _SENDER_LABEL_COLORS[i % len(_SENDER_LABEL_COLORS)] for i, s in enumerate(senders)}

    # --- Story ---
    story = []

    story.append(Paragraph(title, title_style))

    dated = [m for m in messages if m.timestamp]
    participants_str = " · ".join(senders)
    if dated:
        start = dated[0].timestamp.strftime("%b %d, %Y")
        end = dated[-1].timestamp.strftime("%b %d, %Y")
        date_range = f"{start} – {end}" if start != end else start
        story.append(
            Paragraph(
                f"{len(messages)} messages &nbsp;·&nbsp; {date_range} &nbsp;·&nbsp; {participants_str}",
                subtitle_style,
            )
        )
    else:
        story.append(
            Paragraph(f"{len(messages)} messages &nbsp;·&nbsp; {participants_str}", subtitle_style)
        )

    story.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DDDDDD"), spaceAfter=14)
    )

    prev_date = None

    for msg in messages:
        # Date separator when the day changes
        if msg.timestamp:
            msg_date = msg.timestamp.date()
            if msg_date != prev_date:
                label = msg.timestamp.strftime("%A, %B %d, %Y")
                story.append(Paragraph(f"<i>{label}</i>", date_sep_style))
                prev_date = msg_date

        bg = bubble_color.get(msg.sender, colors.HexColor("#F0F0F0"))
        lc = label_color.get(msg.sender, colors.HexColor("#555555"))
        sender_idx = senders.index(msg.sender)
        align_right = sender_idx % 2 == 1  # even senders left, odd senders right

        # Sender label
        sender_para = Paragraph(
            f'<font color="{_hex(lc)}"><b>{msg.sender}</b></font>', sender_style
        )

        # Message body (escape HTML entities, preserve newlines)
        safe_text = (
            msg.text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )
        msg_para = Paragraph(safe_text, msg_style)

        # Timestamp
        ts_str = msg.timestamp.strftime("%I:%M %p").lstrip("0") if msg.timestamp else ""
        ts_para = Paragraph(ts_str, ts_style)

        # Inner bubble table
        bubble = Table(
            [[sender_para], [msg_para], [ts_para]],
            colWidths=[_BUBBLE_W - 20],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("TOPPADDING",    (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING",    (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
                ("TOPPADDING",    (0, 2), (-1, 2), 2),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
                ("LEFTPADDING",   (0, 0), (-1, -1), 10),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
                ("LINEABOVE",     (0, 0), (-1, 0), 0.5, bg),
                ("LINEBELOW",     (0, -1), (-1, -1), 0.5, bg),
                ("LINEBEFORE",    (0, 0), (0, -1), 3, lc),   # colored left accent
            ]),
        )

        # Outer wrapper to push bubble left or right
        if align_right:
            row = [["", bubble]]
            col_widths = [_OFFSET_W, _BUBBLE_W]
        else:
            row = [[bubble, ""]]
            col_widths = [_BUBBLE_W, _OFFSET_W]

        wrapper = Table(
            row,
            colWidths=col_widths,
            style=TableStyle([
                ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
            ]),
        )

        story.append(KeepTogether([wrapper, Spacer(1, 6)]))

    doc.build(story)
    print(f"PDF saved to: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Export a text message conversation to a formatted PDF.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Input formats (auto-detected):
  WhatsApp:  12/25/2023, 10:30 AM - Alice: Hello!
  Bracket:   [2024-01-15 10:30:00] Alice: Hello!
  JSON:      [{"sender":"Alice","timestamp":"2024-01-15 10:30:00","message":"Hello!"}]

Examples:
  python3 message_to_pdf.py chat.txt
  python3 message_to_pdf.py chat.txt -o my_chat.pdf -t "Alice & Bob"
  python3 message_to_pdf.py chat.json --format json
  cat chat.txt | python3 message_to_pdf.py -
""",
    )
    parser.add_argument(
        "input",
        help='Path to the conversation file, or "-" to read from stdin.',
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output PDF file path (default: <input_name>.pdf or conversation.pdf for stdin).",
    )
    parser.add_argument(
        "-t", "--title",
        default="Conversation Export",
        help='Title shown at the top of the PDF (default: "Conversation Export").',
    )
    parser.add_argument(
        "-f", "--format",
        choices=["auto", "whatsapp", "bracket", "json"],
        default="auto",
        help="Input format (default: auto-detect).",
    )

    args = parser.parse_args()

    # Read input
    if args.input == "-":
        content = sys.stdin.read()
        default_output = "conversation.pdf"
    else:
        src = Path(args.input)
        if not src.exists():
            sys.exit(f"Error: File not found: {args.input}")
        content = src.read_text(encoding="utf-8", errors="replace")
        default_output = src.stem + ".pdf"

    if not content.strip():
        sys.exit("Error: Input is empty.")

    # Parse
    fmt = None if args.format == "auto" else args.format
    messages = parse_messages(content, fmt)
    if not messages:
        sys.exit("Error: No messages could be parsed from the input.")

    print(f"Parsed {len(messages)} messages.")

    # Export
    output_path = args.output or default_output
    export_to_pdf(messages, output_path, title=args.title)


if __name__ == "__main__":
    main()
