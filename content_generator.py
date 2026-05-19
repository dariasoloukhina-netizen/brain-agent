import os
import json
import random
import textwrap
import urllib.parse
import smtplib
import requests
import re
import subprocess
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

# ФИХ #2: Используем новый пакет google-genai вместо устаревшего google-generativeai
# pip install google-genai
from google import genai
from google.genai import types

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
    "the weight of information overload",
    "doom scrolling anxiety at 2 AM",
    "need for digital detox and silence",
    "emotional exhaustion from online world",
    "tired eyes and tired soul from screens",
    "the pressure to always be online",
    "reclaiming peace in hyperconnected world",
    "fatigue from comparison on social media",
    "mental heaviness after hours of scrolling",
]

# ==================== ENV VARS ====================
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_PASS = os.environ.get("EMAIL_PASSWORD", "")
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")

# ФИХ #1: Безопасное чтение SMTP_PORT — если переменная пустая или отсутствует, берём 587
_smtp_port_raw = os.environ.get("SMTP_PORT", "587").strip()
SMTP_PORT = int(_smtp_port_raw) if _smtp_port_raw else 587

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

# ==================== FALLBACK ====================
FALLBACK_PLAN = {
    "pinterest": {
        "prompt": "soft pastel illustration of tired person resting in cozy bed, warm morning light, gentle colors, peaceful atmosphere, no text, no letters, dreamy mood, pinterest style",
        "title": "Разрешите себе отдохнуть",
        "description": "Ваш мозг устал не от работы, а от бесконечного потока информации. Сегодня — день, чтобы остановиться."
    },
    "telegram": {
        "prompt": "soft pastel illustration of peaceful morning, cozy atmosphere, warm light, no text",  # ФИХ #3: добавлен prompt
        "text": "Сегодня поговорим о том, почему мы чувствуем усталость, даже если \"ничего не делали\".\n\nБесконечный скроллинг ленты — это не отдых. Это нагрузка на мозг, который пытается обработать сотни образов за минуту.\n\nПопробуйте отложить телефон на 20 минут. Просто посидите в тишине. Это уже забота о себе.",
        "cta": "Как вы отдыхаете от экранов? Поделитесь в комментариях."
    },
    "tiktok": {
        "script": [
            "Ты устал, хотя целый день \"ничего не делал\"?",
            "Бесконечный скроллинг — это не отдых. Это нагрузка.",
            "Поставь телефон в сторону. Вдохни. Ты заслуживаешь покоя."
        ],
        "prompt": "soft illustration of hand putting phone away, peaceful sunset colors, warm atmosphere, pastel tones, cinematic mood, no text"
    }
}

# ==================== INIT GEMINI ====================
# ФИХ #2: Инициализация через новый SDK
try:
    if GEMINI_KEY:
        client = genai.Client(api_key=GEMINI_KEY)
        print("Gemini client initialized (google-genai SDK)")
    else:
        print("WARNING: No GEMINI_API_KEY set")
        client = None
except Exception as e:
    print(f"WARNING: Gemini init failed: {e}")
    client = None

# ==================== FUNCTIONS ====================
def generate_plan():
    """Генерирует план контента через Gemini. При ошибке возвращает fallback."""
    if not client:
        print("No Gemini client available, using fallback")
        return FALLBACK_PLAN

    topic = random.choice(TOPICS)

    prompt = f"""Generate a content plan in valid JSON format only. No markdown, no code blocks, no explanations. Just raw JSON.

Topic: {topic}

Required structure:
{{
  "pinterest": {{
    "prompt": "english image prompt for pinterest pin, vertical 2:3, soft aesthetic, no text",
    "title": "russian title 3-7 words",
    "description": "russian description 1-2 sentences"
  }},
  "telegram": {{
    "prompt": "english image prompt for square 1:1 image, soft aesthetic, no text",
    "text": "russian post text 3-5 paragraphs, gentle tone, emojis",
    "cta": "russian call to action"
  }},
  "tiktok": {{
    "script": ["scene 1 text ~12 sec", "scene 2 text ~16 sec", "scene 3 text ~17 sec"],
    "prompt": "english image prompt for 9:16 video background, atmospheric, no text"
  }}
}}

Rules:
- All text fields must be in Russian (except image prompts which must be in English)
- Image prompts must be detailed and descriptive
- Output ONLY valid JSON, nothing else"""

    try:
        print("Requesting plan from Gemini...")
        # ФИХ #2: Новый способ вызова API
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()

        print(f"Raw response length: {len(text)} chars")
        print(f"First 200 chars: {text[:200]}")

        # Убираем markdown-обёртку если есть
        if "```" in text:
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1).strip()
                print("Extracted JSON from markdown block")

        plan = json.loads(text)
        print("JSON parsed successfully!")

        # Проверяем структуру
        required_keys = ["pinterest", "telegram", "tiktok"]
        for key in required_keys:
            if key not in plan:
                print(f"Missing key: {key}, using fallback")
                return FALLBACK_PLAN

        if "prompt" not in plan["pinterest"] or "script" not in plan["tiktok"]:
            print("Invalid plan structure, using fallback")
            return FALLBACK_PLAN

        # ФИХ #3: Убеждаемся что у telegram есть prompt, иначе берём из pinterest
        if "prompt" not in plan["telegram"]:
            plan["telegram"]["prompt"] = plan["pinterest"]["prompt"]

        return plan

    except Exception as e:
        print(f"ERROR in generate_plan: {type(e).__name__}: {e}")
        print("Using fallback plan")
        return FALLBACK_PLAN


def generate_image(prompt, width, height, filename):
    """Генерирует картинку через Pollinations AI."""
    full_prompt = f"{prompt}, {STYLE_PROMPT}"
    encoded = urllib.parse.quote(full_prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&seed=42&enhance=false"
    )
    print(f"Generating image: {filename} ({width}x{height})...")

    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        with open(filename, "wb") as f:
            f.write(r.content)
        print(f"Image saved: {filename} ({len(r.content)} bytes)")
        return filename
    except Exception as e:
        print(f"ERROR generating image: {e}")
        open(filename, "a").close()
        return filename


def create_tiktok_video(bg_path, script, output="tiktok_video.mp4"):
    """Создаёт TikTok-видео через ffmpeg напрямую."""
    print("Rendering TikTok video with ffmpeg...")

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("ffmpeg found")
    except Exception:
        print("WARNING: ffmpeg not found, creating dummy video file")
        open(output, "a").close()
        return output

    use_color_bg = not os.path.exists(bg_path) or os.path.getsize(bg_path) == 0

    drawtext_filters = []
    for i, txt in enumerate(script):
        start = i * 15
        end = (i + 1) * 15
        safe_txt = txt.replace("'", "'\\''").replace(":", "\\:").replace("=", "\\=")
        wrapped = textwrap.fill(safe_txt, width=20)
        lines = wrapped.split("\n")

        y_start = 1400
        for j, line in enumerate(lines):
            y_pos = y_start + j * 70
            filter_str = (
                f"drawtext=text='{line}':"
                f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
                f"fontsize=50:fontcolor=#4a4a4a:"
                f"x=(w-text_w)/2:y={y_pos}:"
                f"enable='between(t,{start},{end})':"
                f"box=1:boxcolor=white@0.8:boxborderw=20"
            )
            drawtext_filters.append(filter_str)

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
        full_vf = f"loop=loop=-1:size=1:start=0,{scale_pad}" + (f",{vf}" if drawtext_filters else "")
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", bg_path,
            "-vf", full_vf,
            "-c:v", "libx264", "-t", "45", "-pix_fmt", "yuv420p",
            "-preset", "ultrafast", "-threads", "2",
            output,
        ]

    print("Running ffmpeg command...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"Video ready: {output}")
        else:
            print(f"ffmpeg error: {result.stderr[:500]}")
            open(output, "a").close()
    except Exception as e:
        print(f"ERROR running ffmpeg: {e}")
        open(output, "a").close()

    return output


def send_email(subject, body, attachments=None):
    """Отправляет email с вложениями."""
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASS]):
        print("WARNING: Email credentials not configured, skipping email")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachments:
        for path in attachments:
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                print(f"WARNING: Attachment {path} missing or empty, skipping")
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
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
            s.starttls()
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.send_message(msg)
        print(f"Email sent: {subject}")
    except Exception as e:
        print(f"ERROR sending email: {e}")


def post_to_telegram(text, photo_path, video_path=None):
    """Публикует фото и опционально видео в Telegram."""
    if not all([TG_TOKEN, TG_CHAT]):
        print("WARNING: Telegram credentials not configured, skipping Telegram")
        return

    print("Posting to Telegram...")

    if os.path.exists(photo_path) and os.path.getsize(photo_path) > 0:
        try:
            url_photo = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
            with open(photo_path, "rb") as f:
                r = requests.post(
                    url_photo,
                    data={"chat_id": TG_CHAT, "caption": text, "parse_mode": "HTML"},
                    files={"photo": f},
                    timeout=30,
                )
            if r.status_code == 200:
                print("Telegram: photo posted")
            else:
                print(f"Telegram photo error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"ERROR posting photo to Telegram: {e}")
    else:
        print("WARNING: Photo missing or empty, skipping Telegram photo")

    if video_path and os.path.exists(video_path) and os.path.getsize(video_path) > 0:
        try:
            print("Sending video to Telegram...")
            url_video = f"https://api.telegram.org/bot{TG_TOKEN}/sendVideo"
            with open(video_path, "rb") as f:
                r = requests.post(
                    url_video,
                    data={"chat_id": TG_CHAT, "caption": "Видео для TikTok", "parse_mode": "HTML"},
                    files={"video": f},
                    timeout=60,
                )
            if r.status_code == 200:
                print("Telegram: video posted")
            else:
                print(f"Telegram video error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"ERROR posting video to Telegram: {e}")
    else:
        print("WARNING: Video missing or empty, skipping Telegram video")


def main():
    """Главная функция."""
    today = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"=== START: {today} ===")

    # 1. Генерируем план
    plan = generate_plan()
    print(f"Plan keys: {list(plan.keys()) if isinstance(plan, dict) else 'INVALID'}")

    # 2. Генерируем картинки
    try:
        pin_img = generate_image(plan["pinterest"]["prompt"], 1000, 1500, "pinterest_pin.png")
    except Exception as e:
        print(f"ERROR generating pin image: {e}")
        pin_img = "pinterest_pin.png"

    try:
        # ФИХ #3: telegram теперь гарантированно имеет поле prompt
        tg_img = generate_image(plan["telegram"]["prompt"], 1080, 1080, "telegram_post.png")
    except Exception as e:
        print(f"ERROR generating telegram image: {e}")
        tg_img = "telegram_post.png"

    try:
        tiktok_bg = generate_image(plan["tiktok"]["prompt"], 1080, 1920, "tiktok_bg.png")
    except Exception as e:
        print(f"ERROR generating tiktok background: {e}")
        tiktok_bg = "tiktok_bg.png"

    # 3. Создаём видео
    try:
        video = create_tiktok_video(tiktok_bg, plan["tiktok"]["script"])
    except Exception as e:
        print(f"ERROR creating video: {e}")
        video = "tiktok_video.mp4"
        open(video, "a").close()

    # 4. Отправляем email
    try:
        email_body = (
            f"Pinterest: {plan['pinterest']['title']}\n\n"
            f"{plan['pinterest']['description']}\n\n"
            f"TikTok video (45 sec) and Pinterest image attached.\n"
            f"Generated: {today}"
        )
        send_email(
            f"Content for {today} — Pinterest + TikTok",
            email_body,
            attachments=[pin_img, video],
        )
    except Exception as e:
        print(f"ERROR in email sending: {e}")

    # 5. Публикуем в Telegram
    try:
        tg_text = f"{plan['telegram']['text']}\n\n{plan['telegram']['cta']}"
        post_to_telegram(tg_text, tg_img, video_path=video)
    except Exception as e:
        print(f"ERROR in Telegram posting: {e}")

    print("=== ALL DONE ===")


if __name__ == "__main__":
    main()
