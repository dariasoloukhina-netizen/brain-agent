import os
import json
import random
import textwrap
import urllib.parse
import smtplib
import requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

from moviepy.editor import (
    ColorClip, ImageClip, TextClip, CompositeVideoClip
)
import google.generativeai as genai

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

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
EMAIL_TO = os.environ["EMAIL_TO"]
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_PASS = os.environ["EMAIL_PASSWORD"]
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TG_CHAT = os.environ["TELEGRAM_CHAT_ID"]

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

def generate_plan():
    topic = random.choice(TOPICS)
    prompt = f"""
Ты — контент-креатор в нише mental health, digital wellness, anti-burnout.
Тема дня: "{topic}".

Сгенерируй план строго в JSON (без markdown-блоков):
{{
  "pinterest": {{
    "prompt": "detailed english image generation prompt for a pinterest pin, vertical 2:3 ratio, soft aesthetic, cozy, emotional, no text on image",
    "title": "заголовок пина на русском, 3-7 слов",
    "description": "описание пина на русском, 1-2 предложения"
  }},
  "telegram": {{
    "text": "текст поста для Telegram на русском, 3-5 коротких абзацев, бережный тон, эмодзи",
    "cta": "короткий призыв в конце"
  }},
  "tiktok": {{
    "script": [
      "текст на экране, сцена 1, ~12 сек",
      "текст на экране, сцена 2, ~16 сек",
      "текст на экране, сцена 3, ~17 сек"
    ],
    "prompt": "detailed english image generation prompt for vertical video background, 9:16 ratio, atmospheric, soft, cinematic mood, no text"
  }}
}}
Все тексты — русские (кроме image prompt). Image prompt — английский, подробный.
"""
    resp = model.generate_content(prompt)
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].replace("json", "").strip()
    return json.loads(text)

def generate_image(prompt, width, height, filename):
    full_prompt = f"{prompt}, {STYLE_PROMPT}"
    encoded = urllib.parse.quote(full_prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&seed=42&enhance=false"
    )
    print(f"Генерация {filename} ({width}x{height})...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(filename, "wb") as f:
        f.write(r.content)
    print(f"Сохранено: {filename}")
    return filename

def create_tiktok_video(bg_path, script, output="tiktok_video.mp4"):
    print("Рендер TikTok видео...")
    duration = 45
    bg = ColorClip(size=(1080, 1920), color=(245, 243, 240)).set_duration(duration)
    img = (
        ImageClip(bg_path)
        .resize(height=1100)
        .set_position(("center", 180))
        .set_duration(duration)
    )
    clips = [bg, img]
    starts = [0, 15, 30]
    durations = [15, 15, 15]

    for txt, start, dur in zip(script, starts, durations):
        pad = (
            ColorClip(size=(1000, 300), color=(255, 255, 255))
            .set_opacity(0.82)
            .set_position(("center", 1360))
            .set_start(start)
            .set_duration(dur)
        )
        wrapped = textwrap.fill(txt, width=24)
        txt_clip = (
            TextClip(
                wrapped,
                fontsize=58,
                color="#4a4a4a",
                font="DejaVu-Sans",
                method="caption",
                size=(900, None),
                align="center",
            )
            .set_position(("center", 1390))
            .set_start(start)
            .set_duration(dur)
            .fadein(0.8)
            .fadeout(0.8)
        )
        clips.extend([pad, txt_clip])

    video = CompositeVideoClip(clips, size=(1080, 1920))
    video.write_videofile(
        output,
        fps=24,
        codec="libx264",
        audio=False,
        threads=2,
        preset="ultrafast",
        logger=None,
    )
    print(f"Видео готово: {output}")
    return output

def send_email(subject, body, attachments=None):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachments:
        for path in attachments:
            name = os.path.basename(path)
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

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as s:
        s.starttls()
        s.login(EMAIL_FROM, EMAIL_PASS)
        s.send_message(msg)
    print(f"Email отправлен: {subject}")

def post_to_telegram(text, photo_path, video_path=None):
    print("Постинг в Telegram...")
    
    url_photo = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    with open(photo_path, "rb") as f:
        r = requests.post(
            url_photo,
            data={"chat_id": TG_CHAT, "caption": text, "parse_mode": "HTML"},
            files={"photo": f},
            timeout=30,
        )
    
    if r.status_code == 200:
        print("Telegram: фото опубликовано")
    else:
        print(f"Telegram ошибка при отправке фото {r.status_code}: {r.text}")
    
    if video_path and os.path.exists(video_path):
        print("Отправка видео в Telegram...")
        url_video = f"https://api.telegram.org/bot{TG_TOKEN}/sendVideo"
        with open(video_path, "rb") as f:
            r = requests.post(
                url_video,
                data={"chat_id": TG_CHAT, "caption": "Видео для TikTok", "parse_mode": "HTML"},
                files={"video": f},
                timeout=60,
            )
        if r.status_code == 200:
            print("Telegram: видео опубликовано")
        else:
            print(f"Telegram ошибка при отправке видео {r.status_code}: {r.text}")

def main():
    today = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"Старт: {today}")

    plan = generate_plan()

    pin_img = generate_image(
        plan["pinterest"]["prompt"], 1000, 1500, "pinterest_pin.png"
    )
    tg_img = generate_image(
        plan["telegram"].get("prompt", plan["pinterest"]["prompt"]),
        1080, 1080, "telegram_post.png",
    )
    tiktok_bg = generate_image(
        plan["tiktok"]["prompt"], 1080, 1920, "tiktok_bg.png"
    )

    video = create_tiktok_video(tiktok_bg, plan["tiktok"]["script"])

    email_body = f"""Pinterest: {plan['pinterest']['title']}

{plan['pinterest']['description']}

TikTok видео (45 сек) и Pinterest-картинка во вложении.
Дата генерации: {today}"""
    send_email(
        f"Контент на {today} — Pinterest + TikTok",
        email_body,
        attachments=[pin_img, video],
    )

    tg_text = f"{plan['telegram']['text']}\n\n{plan['telegram']['cta']}"
    post_to_telegram(tg_text, tg_img, video_path=video)

    print("Всё готово!")

if __name__ == "__main__":
    main()
