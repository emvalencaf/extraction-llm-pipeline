"""Render the four README diagrams as SVG files next to this script.

Run: `uv run docs/diagrams/build.py`. The icons come from `icons/aws` (official AWS
Architecture Icons) and `icons/fa` (Font Awesome Free); both are inlined into each SVG so the
files render on GitHub with no external requests.
"""

import re
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
INK, MUTED, LINE = "#1f2937", "#6b7280", "#94a3b8"
GREEN, AMBER, RED, BLUE, GRAY = "#16a34a", "#d97706", "#dc2626", "#2563eb", "#64748b"
FONT = 'font-family="Helvetica, Arial, sans-serif"'


def _icon_body(kind: str, name: str, color: str) -> tuple[str, str]:
    raw = (HERE / "icons" / kind / f"{name}.svg").read_text()
    view_box = re.search(r'viewBox="([^"]+)"', raw).group(1)
    inner = raw.split(">", 2)[2] if raw.startswith("<?xml") else raw.split(">", 1)[1]
    inner = re.sub(r"<title>.*?</title>|<!--.*?-->", "", inner, flags=re.S)
    inner = inner.rsplit("</svg>", 1)[0]
    inner = re.sub(r'\sid="[^"]*"', "", inner)
    return view_box, inner.replace("currentColor", color)


class Canvas:
    def __init__(self, width: int, height: int, title: str, desc: str) -> None:
        self.w, self.h, self.title, self.desc = width, height, title, desc
        self.parts: list[str] = []

    def add(self, svg: str) -> None:
        self.parts.append(svg)

    def text(self, x, y, s, size=12, weight="normal", fill=INK, anchor="middle") -> None:
        self.add(
            f'<text x="{x}" y="{y}" {FONT} font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>'
        )

    def icon(self, kind, name, cx, cy, size=52, color=INK) -> None:
        view_box, inner = _icon_body(kind, name, color)
        self.add(
            f'<svg x="{cx - size / 2}" y="{cy - size / 2}" width="{size}" height="{size}" '
            f'viewBox="{view_box}">{inner}</svg>'
        )

    def node(self, cx, cy, kind, name, label, sub=None, color=INK, pos="below") -> None:
        self.icon(kind, name, cx, cy, color=color)
        if pos == "left":
            self.text(cx - 38, cy - 2, label, 12, "bold", anchor="end")
            if sub:
                self.text(cx - 38, cy + 12, sub, 10.5, fill=MUTED, anchor="end")
            return
        top = pos == "above"
        self.text(cx, cy - 42 if top else cy + 44, label, 12, "bold")
        if sub:
            self.text(cx, cy - 56 if top else cy + 58, sub, 10.5, fill=MUTED)

    def group(self, x, y, w, h, title, color=LINE, dash="6 4") -> None:
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="none" '
            f'stroke="{color}" stroke-width="1.5" stroke-dasharray="{dash}"/>'
        )
        self.text(x + 12, y + 20, title, 12, "bold", color, "start")

    def box(self, cx, cy, w, h, title, sub=None, stroke=BLUE, fill="#f8fafc", icon=None) -> None:
        self.add(
            f'<rect x="{cx - w / 2}" y="{cy - h / 2}" width="{w}" height="{h}" rx="9" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>'
        )
        shift = 0
        if icon:
            kind, name = icon
            self.icon(kind, name, cx - w / 2 + 24, cy, 28, stroke if kind == "fa" else INK)
            shift = 20
        self.text(cx + shift, cy - (4 if sub else -4), title, 12.5, "bold")
        if sub:
            for i, line in enumerate(sub.split("\n")):
                self.text(cx + shift, cy + 12 + i * 12, line, 10, fill=MUTED)

    def edge(self, pts, label=None, color=LINE, dash=False, at=None, step=None, anchor="middle"):
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        da = ' stroke-dasharray="6 4"' if dash else ""
        self.add(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.8"{da} '
            f'marker-end="url(#arrow-{color[1:]})"/>'
        )
        if label:
            if at is None:
                (x1, y1), (x2, y2) = pts[len(pts) // 2 - 1], pts[len(pts) // 2]
                at = ((x1 + x2) / 2, (y1 + y2) / 2 - 7)
            for i, line in enumerate(label.split("\n")):
                self.text(
                    at[0],
                    at[1] + i * 12,
                    line,
                    10.5,
                    fill=color if color != LINE else MUTED,
                    anchor=anchor,
                )
        if step:
            x, y = pts[0]
            self.add(f'<circle cx="{x}" cy="{y}" r="9" fill="{BLUE}"/>')
            self.text(x, y + 4, str(step), 10.5, "bold", "#ffffff")

    def save(self, name: str) -> None:
        colors = {c for c in (LINE, GREEN, AMBER, RED, BLUE, GRAY, MUTED)}
        markers = "".join(
            f'<marker id="arrow-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
            f'fill="{c}"/></marker>'
            for c in colors
        )
        body = "\n".join(self.parts)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t d">\n'
            f'<title id="t">{escape(self.title)}</title><desc id="d">{escape(self.desc)}</desc>\n'
            f"<defs>{markers}</defs>\n"
            f'<rect width="{self.w}" height="{self.h}" fill="#ffffff"/>\n{body}\n</svg>\n'
        )
        (HERE / name).write_text(svg)


def architecture() -> None:
    c = Canvas(1100, 690, "AWS architecture", "API Gateway, Lambda, S3, SQS, DynamoDB and Gemini.")
    c.text(30, 32, "AWS architecture", 18, "bold", anchor="start")
    c.text(
        30, 50, "Numbers follow one job from request to result.", 11.5, fill=MUTED, anchor="start"
    )
    c.group(170, 70, 650, 600, "AWS account · us-east-1 · Terraform-managed")
    c.node(70, 170, "fa", "user", "Client", "API key header")
    c.node(250, 150, "aws", "Amazon-API-Gateway", "API Gateway", "key + usage plan")
    c.node(440, 150, "aws", "AWS-Lambda", "API Lambda", "container image")
    c.node(640, 150, "aws", "Amazon-DynamoDB", "Jobs table", "state per job")
    c.node(250, 320, "aws", "Amazon-Simple-Storage-Service", "S3 bucket", "uploads/ · text/")
    c.node(440, 320, "aws", "Amazon-Simple-Queue-Service", "Jobs queue", "SQS")
    c.node(640, 320, "aws", "AWS-Lambda", "Worker Lambda", "LangGraph pipeline")
    c.node(960, 320, "fa", "robot", "Gemini API", "sees Placeholders only")
    c.node(250, 480, "aws", "Amazon-Elastic-Container-Registry", "ECR", "Lambda images, tag = SHA")
    c.node(440, 480, "aws", "Amazon-Simple-Queue-Service", "Dead-letter queue", "after 5 receives")
    c.node(640, 480, "aws", "AWS-Systems-Manager", "SSM Parameter", "Gemini key")
    c.node(300, 585, "aws", "Amazon-CloudWatch", "CloudWatch", "alarms + dashboard")
    c.node(560, 585, "aws", "Amazon-Simple-Notification-Service", "SNS", "")
    c.node(790, 520, "aws", "AWS-Budgets", "Budget", "")
    c.node(960, 585, "fa", "envelope", "Alert e-mail", "")
    c.edge([(98, 160), (222, 150)], "POST /jobs · GET /jobs/{id}", at=(160, 130), step=1)
    c.edge([(278, 150), (412, 150)], step=2)
    c.edge([(468, 150), (612, 150)], "create job,\npresigned URL", at=(540, 122), step=3)
    c.edge([(112, 212), (222, 305)], "PUT PDF", at=(140, 262), step=4)
    c.edge([(278, 320), (412, 320)], "ObjectCreated", at=(345, 306), step=5)
    c.edge([(468, 320), (612, 320)], "poll", at=(540, 306), step=6)
    c.edge([(640, 292), (640, 222)], "job state", at=(668, 262), step=7)
    c.edge([(668, 320), (930, 320)], "anonymized text", at=(800, 306), step=8)
    c.edge([(440, 390), (440, 452)], "5th failed receive", RED, True, at=(520, 425))
    c.edge([(640, 452), (640, 392)], "read key", at=(672, 425))
    c.edge([(415, 552), (332, 572)], "DLQ depth", at=(372, 546))
    c.edge([(330, 585), (528, 585)], "alarm")
    c.edge([(764, 534), (588, 572)], "budget", at=(700, 548))
    c.edge([(590, 585), (928, 585)], "e-mail", at=(760, 573))
    c.save("architecture.svg")


def job_flow() -> None:
    c = Canvas(1100, 640, "Job flow", "Job states and the SQS retry and dead-letter lane.")
    c.text(30, 32, "Job flow", 18, "bold", anchor="start")
    c.text(
        30,
        50,
        "States are written conditionally, so a duplicate delivery cannot move a job backwards.",
        11.5,
        fill=MUTED,
        anchor="start",
    )
    s = {"w": 160, "h": 46}
    c.box(110, 140, **s, title="awaiting_upload", stroke=BLUE)
    c.box(110, 290, **s, title="expired", stroke=GRAY, fill="#f1f5f9")
    c.box(340, 140, **s, title="queued", stroke=BLUE)
    c.box(580, 140, **s, title="processing", stroke=BLUE)
    c.box(880, 85, **s, title="succeeded", stroke=GREEN, fill="#f0fdf4")
    c.box(880, 165, **s, title="failed_validation", stroke=AMBER, fill="#fffbeb")
    c.box(880, 250, **s, title="failed", stroke=RED, fill="#fef2f2")
    c.edge([(190, 140), (260, 140)], "S3 event", at=(225, 128))
    c.edge([(420, 140), (500, 140)], "worker claims", at=(460, 128))
    c.edge([(110, 163), (110, 267)], "not uploaded\nin 15 min", GRAY, at=(125, 215), anchor="start")
    c.edge([(660, 125), (800, 85)], "valid Extraction", GREEN, at=(730, 96))
    c.edge(
        [(660, 145), (800, 165)], "business failure:\ninvalid after repair", AMBER, at=(735, 118)
    )
    c.edge(
        [(650, 163), (800, 250)],
        "infrastructure failure,\n5th receive",
        RED,
        at=(715, 228),
        anchor="end",
    )
    c.edge(
        [(560, 117), (560, 70), (350, 70), (350, 117)],
        "transient error: message returns after 30 s x 2^n (max 900 s)",
        at=(455, 62),
    )
    c.edge(
        [(880, 273), (880, 330), (600, 330), (600, 163)],
        "redrive (only when the cause was retries_exhausted)",
        BLUE,
        True,
        at=(740, 322),
    )

    c.group(60, 380, 900, 220, "SQS lane · infrastructure failures only")
    c.node(200, 500, "aws", "Amazon-Simple-Queue-Service", "Jobs queue", "", pos="left")
    c.node(500, 500, "aws", "AWS-Lambda", "Worker Lambda", "", pos="above")
    c.node(800, 500, "aws", "Amazon-Simple-Queue-Service", "Dead-letter queue", "alarm on depth")
    c.edge([(228, 500), (472, 500)], "deliver", at=(350, 488))
    c.edge([(528, 500), (772, 500)], "5th receive fails", RED, at=(650, 488))
    c.edge(
        [(500, 535), (500, 590), (200, 590), (200, 535)],
        "infrastructure error: back to the queue after the delay",
        at=(350, 582),
    )
    c.edge(
        [(800, 458), (800, 415), (200, 415), (200, 468)],
        "redrive: native SQS redrive moves the messages back",
        BLUE,
        True,
        at=(500, 408),
    )
    c.text(
        30,
        626,
        "Business failures consume the message and end the job; "
        "only infrastructure failures reach the DLQ (ADR 0004).",
        10.5,
        fill=MUTED,
        anchor="start",
    )
    c.save("job-flow.svg")


def graph() -> None:
    c = Canvas(
        1180, 650, "Extraction graph", "LangGraph nodes with anonymization before the model call."
    )
    c.text(30, 32, "Extraction graph (LangGraph)", 18, "bold", anchor="start")
    c.text(
        30,
        50,
        "The model only ever sees Placeholders; real identifiers come back in post.",
        11.5,
        fill=MUTED,
        anchor="start",
    )
    c.icon("fa", "file-pdf", 60, 160, 40, RED)
    c.text(60, 196, "PDF", 11, "bold")
    c.box(
        210,
        160,
        180,
        76,
        "pre",
        "limits · read text · clean\nanonymize (Presidio)",
        icon=("fa", "eraser"),
    )
    c.box(450, 160, 180, 76, "call", "Gemini · 3 attempts\njittered backoff", icon=("fa", "robot"))
    c.box(
        690,
        160,
        180,
        76,
        "post",
        "guard output\nrestore identifiers",
        icon=("fa", "wand-magic-sparkles"),
    )
    c.box(
        920,
        160,
        170,
        76,
        "validate",
        "Extraction schema\n+ grounding rate",
        icon=("fa", "shield-halved"),
    )
    c.box(1105, 160, 120, 46, "succeeded", stroke=GREEN, fill="#f0fdf4")
    c.edge([(82, 160), (120, 160)])
    c.edge([(300, 160), (360, 160)], "text with\n[NAME_1]…", at=(330, 138))
    c.edge([(540, 160), (600, 160)], "reply with\nPlaceholders", at=(570, 138))
    c.edge([(780, 160), (835, 160)])
    c.edge([(1005, 160), (1045, 160)], "valid", GREEN, at=(1025, 148))
    c.edge(
        [(210, 122), (210, 85), (690, 85), (690, 122)],
        "PlaceholderMap: in memory only, never sent to the model",
        BLUE,
        True,
        at=(450, 77),
    )
    c.icon("fa", "lock", 450, 100, 16, BLUE)

    c.box(310, 340, 150, 52, "fall_back", "primary → fallback model", stroke=AMBER, fill="#fffbeb")
    c.box(570, 340, 170, 52, "unavailable", "raises → SQS retry → DLQ", stroke=RED, fill="#fef2f2")
    c.edge([(380, 198), (335, 314)], "primary\nexhausted", AMBER, at=(345, 250), anchor="end")
    c.edge([(360, 314), (400, 198)], "retry", AMBER, at=(390, 262), anchor="start")
    c.edge(
        [(525, 198), (555, 314)],
        "fallback or\nescalation\ndown",
        RED,
        at=(550, 245),
        anchor="start",
    )

    c.box(760, 340, 150, 52, "repair", "up to 2x with the errors", stroke=BLUE)
    c.box(935, 340, 150, 52, "escalate", "1x quality model", stroke=BLUE)
    c.box(1100, 340, 130, 52, "give_up", "schema_invalid", stroke=AMBER, fill="#fffbeb")
    c.edge([(880, 198), (790, 314)], "invalid", BLUE, at=(848, 262), anchor="start")
    c.edge([(925, 198), (935, 314)], "repairs used", BLUE, at=(945, 255), anchor="start")
    c.edge([(975, 198), (1075, 314)], "escalated already", AMBER, at=(1060, 255), anchor="start")
    c.edge(
        [(760, 366), (760, 440), (440, 440), (440, 198)],
        "repair: back to call",
        BLUE,
        at=(600, 432),
    )
    c.edge(
        [(935, 366), (935, 480), (470, 480), (470, 198)],
        "escalate: back to call with the quality model",
        BLUE,
        at=(700, 472),
    )
    c.edge([(1100, 366), (1100, 537)], "", AMBER)
    c.box(1100, 560, 150, 46, "failed_validation", stroke=AMBER, fill="#fffbeb")

    c.box(
        130,
        340,
        150,
        52,
        "PDF rejected",
        "too large · too long\nunreadable",
        stroke=AMBER,
        fill="#fffbeb",
    )
    c.edge([(160, 198), (150, 314)], "terminal", AMBER, at=(165, 255), anchor="start")
    c.box(700, 262, 130, 30, "output_rejected", stroke=AMBER, fill="#fffbeb")
    c.edge([(700, 198), (700, 247)], "", AMBER)
    c.text(
        30,
        628,
        "Business outcomes end the job and consume the message; "
        "ModelUnavailableError is the only exit that retries.",
        10.5,
        fill=MUTED,
        anchor="start",
    )
    c.save("extraction-graph.svg")


def cicd() -> None:
    c = Canvas(
        1180,
        620,
        "CI/CD pipeline",
        "Pull request checks, regression gate, approval, apply and smoke test.",
    )
    c.text(30, 32, "CI/CD pipeline", 18, "bold", anchor="start")
    c.text(
        30,
        50,
        "Nothing reaches AWS without a passing gate and a human approval.",
        11.5,
        fill=MUTED,
        anchor="start",
    )
    c.group(30, 70, 1120, 170, "Pull request · ci.yml and the deploy.yml plan job")
    c.box(
        150,
        160,
        190,
        70,
        "Work branch → PR",
        "into development\nthen development → master",
        icon=("fa", "code-branch"),
    )
    c.box(
        410,
        160,
        220,
        90,
        "CI checks",
        "Unicode · ruff · wiki · unit tests\nimport layers · terraform validate\n"
        "actionlint · 11 compose scenarios",
        icon=("fa", "circle-check"),
        stroke=GREEN,
    )
    c.box(
        700,
        160,
        220,
        70,
        "Terraform plan",
        "role: plan (read-only, OIDC)\npublished in the job summary",
        icon=("aws", "AWS-Identity-and-Access-Management"),
    )
    c.box(
        990,
        160,
        200,
        70,
        "Review and merge",
        "master only gets PRs\nfrom development",
        icon=("fa", "user-shield"),
    )
    c.edge([(245, 160), (300, 160)])
    c.edge([(520, 160), (590, 160)])
    c.edge([(810, 160), (890, 160)])

    c.group(
        30,
        280,
        1120,
        230,
        "Push to master · deploy.yml (also workflow_dispatch by SHA for rollback)",
    )
    c.box(
        150,
        400,
        170,
        70,
        "Regression gate",
        "only if extraction paths\nchanged · floor 90 %",
        icon=("fa", "flask-vial"),
        stroke=AMBER,
    )
    c.box(
        390,
        400,
        170,
        70,
        "Approval",
        "environment: production\nrequired reviewers",
        icon=("fa", "hand"),
        stroke=BLUE,
    )
    c.box(
        650,
        400,
        240,
        70,
        "Apply",
        "role: deploy (OIDC, production only)\nimage tagged by SHA · terraform apply",
        icon=("aws", "Amazon-Elastic-Container-Registry"),
    )
    c.box(
        930,
        400,
        170,
        70,
        "Smoke test",
        "POST /jobs end to end\non the deployed endpoint",
        icon=("fa", "circle-check"),
        stroke=GREEN,
    )
    c.box(1105, 400, 80, 46, "live", stroke=GREEN, fill="#f0fdf4")
    c.edge([(235, 400), (305, 400)], "pass", GREEN, at=(270, 388))
    c.edge([(475, 400), (530, 400)], "OK", BLUE, at=(510, 388))
    c.edge([(770, 400), (845, 400)])
    c.edge([(1015, 400), (1065, 400)], "pass", GREEN, at=(1040, 388))
    c.edge([(150, 435), (150, 470)], "", RED)
    c.text(150, 486, "fail: deploy stops", 10.5, fill=RED)
    c.edge([(930, 435), (930, 470)], "", RED)
    c.node(990, 560, "fa", "rotate-left", "Rollback", "no automatic rollback", RED)
    c.text(
        280,
        565,
        "git revert on master, or run deploy.yml by SHA of the last good commit "
        "(still needs approval)",
        10.5,
        fill=MUTED,
        anchor="start",
    )
    c.edge([(930, 470), (930, 520), (990, 520), (990, 530)], "smoke fails", RED, at=(868, 508))
    c.save("ci-cd.svg")


if __name__ == "__main__":
    architecture()
    job_flow()
    graph()
    cicd()
