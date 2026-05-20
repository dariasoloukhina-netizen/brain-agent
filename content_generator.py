import os
import json
import random
import textwrap
import urllib.parse
import smtplib
import requests
import re
import subprocess
import warnings
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

warnings.filterwarnings("ignore", category=FutureWarning)

# ==================== GEMINI ====================
try:
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    # gemini-2.0-flash-lite имеет более высокий бесплатный лимит чем gemini-2.0-flash
    GEMINI_MODEL = genai.GenerativeModel("gemini-2.0-flash-lite")
    print("Gemini SDK loaded OK (gemini-2.0-flash-lite)")
except Exception as _e:
    print(f"WARNING: Gemini unavailable: {_e}")
    GEMINI_MODEL = None

# ==================== ENV VARS ====================
GEMINI_KEY  = os.environ.get("GEMINI_API_KEY", "")
EMAIL_TO    = os.environ.get("EMAIL_TO", "")
EMAIL_FROM  = os.environ.get("EMAIL_FROM", "")
EMAIL_PASS  = os.environ.get("EMAIL_PASSWORD", "")
# SMTP захардкожен — не зависит от GitHub Secrets
SMTP_SERVER = "smtp.mail.ru"
SMTP_PORT   = 465  # mail.ru SSL
TG_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT     = os.environ.get("TELEGRAM_CHAT_ID", "")

# ==================== КОНФИГ ====================
STYLE_PROMPT = (
    "soft minimalist digital illustration, muted pastel colors, flat design, "
    "gentle gradients, cozy aesthetic, clean composition, no text, no watermark, "
    "no letters, dreamy atmosphere, pinterest trending style"
)

TOPICS = [
    "mental exhaustion from endless scrolling",
    "digital burnout and social media fatigue",
    "brain fog and inability to focus",
    "doom scrolling anxiety at 2 AM",
    "need for digital detox and silence",
    "emotional exhaustion from online world",
    "reclaiming peace in hyperconnected world",
]

# ==================== FALLBACK ====================
FALLBACK_PLAN = {
    "pinterest": {
        "prompt": (
            "soft pastel illustration of tired person resting in cozy bed, "
            "warm morning light, gentle colors, peaceful atmosphere, no text, dreamy mood"
        ),
        "title": "Разрешите себе отдохнуть",
        "description": (
            "Ваш мозг устал не от работы, а от бесконечного потока информации. "
            "Сегодня день чтобы остановиться."
        ),
    },
    "telegram": {
        "prompt": "soft pastel illustration of peaceful morning, cozy atmosphere, warm light, no text",
        "text": (
            "Сегодня поговорим о том, почему мы чувствуем усталость, "
            "даже если ничего не делали.\n\n"
            "Бесконечный скроллинг ленты — это не отдых. "
            "Это нагрузка на мозг, который пытается обработать сотни образов за минуту.\n\n"
            "Попробуйте отложить телефон на 20 минут. "
            "Просто посидите в тишине. Это уже забота о себе."
        ),
        "cta": "Как вы отдыхаете от экранов? Поделитесь в комментариях.",
    },
    "tiktok": {
        "script": [
            "Ты устал хотя целый день ничего не делал?",
            "Бесконечный скроллинг — это не отдых. Это нагрузка.",
            "Поставь телефон в сторону. Вдохни. Ты заслуживаешь покоя.",
        ],
        "prompt": (
            "soft illustration of hand putting phone away, peaceful sunset colors, "
            "warm atmosphere, pastel tones, no text"
        ),
    },
}


# ==================== ДИАГНОСТИКА ====================

def check_secrets():
    print("--- SECRETS CHECK ---")
    print(f"GEMINI_API_KEY:     {'OK len=' + str(len(GEMINI_KEY)) if GEMINI_KEY else 'MISSING!'}")
    print(f"EMAIL_FROM:         {EMAIL_FROM if EMAIL_FROM else 'MISSING!'}")
    print(f"EMAIL_TO:           {EMAIL_TO if EMAIL_TO else 'MISSING!'}")
    print(f"EMAIL_PASSWORD:     {'OK len=' + str(len(EMAIL_PASS)) if EMAIL_PASS else 'MISSING!'}")
    print(f"SMTP_SERVER:        {SMTP_SERVER}")
    print(f"SMTP_PORT:          {SMTP_PORT}")
    print(f"TELEGRAM_BOT_TOKEN: {'OK len=' + str(len(TG_TOKEN)) if TG_TOKEN else 'MISSING!'}")
    print(f"TELEGRAM_CHAT_ID:   {TG_CHAT if TG_CHAT else 'MISSING!'}")
    print("---------------------")


# ==================== ФУНКЦИИ ====================

def generate_plan():
    if GEMINI_MODEL is None or not GEMINI_KEY:
        print("Gemini not available, using fallback plan")
        return FALLBACK_PLAN

    topic = random.choice(TOPICS)
    prompt = (
        "Generate a content plan in valid JSON format only. "
        "No markdown, no code blocks, no explanations. Just raw JSON.\n\n"
        f"Topic: {topic}\n\n"
        "Required JSON structure:\n"
        "{\n"
        '  "pinterest": {\n'
        '    "prompt": "english image prompt, vertical 2:3, soft aesthetic, no text",\n'
        '    "title": "russian title 3-7 words",\n'
        '    "description": "russian description 1-2 sentences"\n'
        "  },\n"
        '  "telegram": {\n'
        '    "prompt": "english image prompt, square 1:1, soft aesthetic, no text",\n'
        '    "text": "russian post 3-5 paragraphs, gentle tone, emojis",\n'
        '    "cta": "russian call to action"\n'
        "  },\n"
        '  "tiktok": {\n'
        '    "script": ["scene 1 ~12 sec", "scene 2 ~16 sec", "scene 3 ~17 sec"],\n'
        '    "prompt": "english image prompt, 9:16, atmospheric, no text"\n'
        "  }\n"
        "}\n\n"
        "IMPORTANT: output ONLY valid JSON. Text fields in Russian, prompts in English."
    )

    try:
        print("Requesting plan from Gemini...")
        response = GEMINI_MODEL.generate_content(prompt)
        raw = response.text.strip()
        print(f"Response: {len(raw)} chars | First 150: {raw[:150]}")

        if "```" in raw:
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1).strip()

        plan = json.loads(raw)

        for key in ("pinterest", "telegram", "tiktok"):
            if key not in plan:
                print(f"Missing key '{key}', using fallback")
                return FALLBACK_PLAN

        if "prompt" not in plan["pinterest"] or "script" not in plan["tiktok"]:
            print("Bad plan structure, using fallback")
            return FALLBACK_PLAN

        if "prompt" not in plan["telegram"]:
            plan["telegram"]["prompt"] = plan["pinterest"]["prompt"]

        print("Plan generated OK")
        return plan

    except Exception as e:
        print(f"generate_plan ERROR ({type(e).__name__}): {e} — using fallback")
        return FALLBACK_PLAN


def generate_image(prompt, width, height, filename):
    full_prompt = f"{prompt}, {STYLE_PROMPT}"
    encoded = urllib.parse.quote(full_prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&seed=42&enhance=false"
    )
    print(f"Generating image '{filename}' ({width}x{height})...")
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        with open(filename, "wb") as f:
            f.write(r.content)
        print(f"Image saved: {filename} ({len(r.content)} bytes)")
    except Exception as e:
        print(f"generate_image ERROR: {e}")
        open(filename, "a").close()
    return filename


def create_tiktok_video(bg_path, script, output="tiktok_video.mp4"):
    print("Rendering TikTok video...")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("WARNING: ffmpeg not found")
        open(output, "a").close()
        return output

    use_color_bg = not os.path.exists(bg_path) or os.path.getsize(bg_path) == 0

    drawtext_filters = []
    for i, txt in enumerate(script):
        start = i * 15
        end = (i + 1) * 15
        # Убираем спецсимволы которые ломают ffmpeg
        safe = txt.replace("'", "").replace('"', "").replace(":", " ").replace("=", " ")
        for j, line in enumerate(textwrap.fill(safe, width=20).split("\n")):
            y = 1400 + j * 70
            drawtext_filters.append(
                f"drawtext=text='{line}'"
                f":fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                f":fontsize=50:fontcolor=#4a4a4a"
                f":x=(w-text_w)/2:y={y}"
                f":enable='between(t,{start},{end})'"
                f":box=1:boxcolor=white@0.8:boxborderw=20"
            )

    vf = ",".join(drawtext_filters) if drawtext_filters else "null"

    if use_color_bg:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=0xF5F3F0:s=1080x1920:d=45",
            "-vf", vf,
            "-c:v", "libx264", "-t", "45", "-pix_fmt", "yuv420p",
            "-preset", "ultrafast", "-threads", "2",
            output,
        ]
    else:
        scale_pad = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:0xF5F3F0"
        )
        full_vf = f"loop=loop=-1:size=1:start=0,{scale_pad}"
        if drawtext_filters:
            full_vf += f",{vf}"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", bg_path,
            "-vf", full_vf,
            "-c:v", "libx264", "-t", "45", "-pix_fmt", "yuv420p",
            "-preset", "ultrafast", "-threads", "2",
            output,
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"Video ready: {output}")
        else:
            print(f"ffmpeg error: {result.stderr[:500]}")
            open(output, "a").close()
    except Exception as e:
        print(f"create_tiktok_video ERROR: {e}")
        open(output, "a").close()
    return output


def send_email(subject, body, attachments=None):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASS]):
        print("WARNING: Email credentials missing — skipping")
        print(f"  EMAIL_FROM={'set' if EMAIL_FROM else 'EMPTY'}, EMAIL_TO={'set' if EMAIL_TO else 'EMPTY'}, EMAIL_PASSWORD={'set' if EMAIL_PASS else 'EMPTY'}")
        return
    EMAIL_FROM_REAL = EMAIL_FROM
    EMAIL_TO_REAL   = EMAIL_TO

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM_REAL
    msg["To"] = EMAIL_TO_REAL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    for path in (attachments or []):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            print(f"WARNING: skipping attachment: {path}")
            continue
        name = os.path.basename(path)
        try:
            if name.lower().endswith((".png", ".jpg", ".jpeg")):
                with open(path, "rb") as f:
                    part = MIMEImage(f.read())
            else:
                with open(path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
            part.add_header("Content-Disposition", "attachment", filename=name)
            msg.attach(part)
            print(f"Attached: {name}")
        except Exception as e:
            print(f"ERROR attaching {name}: {e}")

    try:
        if SMTP_PORT == 465:
            import ssl
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ctx) as s:
                s.login(EMAIL_FROM_REAL, EMAIL_PASS)
                s.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
                s.ehlo()
                s.starttls()
                s.ehlo()
                s.login(EMAIL_FROM_REAL, EMAIL_PASS)
                s.send_message(msg)
        print(f"Email sent OK to {EMAIL_TO_REAL}")
    except smtplib.SMTPAuthenticationError as e:
        print(f"EMAIL AUTH FAILED: {e}")
        print("HINT mail.ru: Настройки -> Безопасность -> Пароли для внешних приложений")
        print("HINT Gmail: нужен App Password, не обычный пароль")
    except Exception as e:
        print(f"send_email ERROR: {e}")


def post_to_telegram(text, photo_path, video_path=None):
    if not TG_TOKEN or not TG_CHAT:
        print("WARNING: Telegram credentials missing — skipping")
        return

    print(f"Posting to Telegram (chat: {TG_CHAT})...")

    if os.path.exists(photo_path) and os.path.getsize(photo_path) > 0:
        try:
            with open(photo_path, "rb") as f:
                r = requests.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                    data={"chat_id": TG_CHAT, "caption": text, "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=30,
                )
            if r.status_code == 200:
                print("Telegram: photo sent OK")
            else:
                print(f"Telegram photo ERROR {r.status_code}: {r.text[:300]}")
        except Exception as e:
            print(f"post_to_telegram photo ERROR: {e}")
    else:
        print("WARNING: photo missing — skipping")

    if video_path and os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        try:
            with open(video_path, "rb") as f:
                r = requests.post(
                    f"https://api.telegram.org/bot{TG_TOKEN}/sendVideo",
                    data={
                        "chat_id": TG_CHAT,
                        "caption": "Видео для TikTok",
                        "parse_mode": "HTML",
                    },
                    files={"video": f},
                    timeout=60,
                )
            if r.status_code == 200:
                print("Telegram: video sent OK")
            else:
                print(f"Telegram video ERROR {r.status_code}: {r.text[:300]}")
        except Exception as e:
            print(f"post_to_telegram video ERROR: {e}")
    else:
        print("WARNING: video missing — skipping")


# ==================== MAIN ====================

def main():
    today = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"=== START: {today} ===")

    check_secrets()  # покажет какие секреты пустые

    plan      = generate_plan()
    pin_img   = generate_image(plan["pinterest"]["prompt"], 1000, 1500, "pinterest_pin.png")
    tg_img    = generate_image(plan["telegram"]["prompt"],  1080, 1080, "telegram_post.png")
    tiktok_bg = generate_image(plan["tiktok"]["prompt"],    1080, 1920, "tiktok_bg.png")
    video     = create_tiktok_video(tiktok_bg, plan["tiktok"]["script"])

    send_email(
        subject=f"Content {today} — Pinterest + TikTok",
        body=(
            f"Pinterest: {plan['pinterest']['title']}\n\n"
            f"{plan['pinterest']['description']}\n\n"
            f"Attached: Pinterest image + TikTok video (45s)\n"
            f"Generated: {today}"
        ),
        attachments=[pin_img, video],
    )

    post_to_telegram(
        text=f"{plan['telegram']['text']}\n\n{plan['telegram']['cta']}",
        photo_path=tg_img,
        video_path=video,
    )

    print("=== ALL DONE ===")


if __name__ == "__main__":
    main()



