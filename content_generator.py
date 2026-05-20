"""
SMM Content Bot  ×  AI Storyboard System
==========================================
Интеграция с репозиторием ai-storyboard-video-starter.

Структура проекта (создаётся автоматически):
    projects/<YYYY-MM-DD>/
        01-creative-brief/approved/brief.md
        04-image-prompts/approved/prompts.md
        05-storyboard-frames/
            attempts/          <- черновики
            approved/          <- pinterest_pin.png, telegram_post.png, tiktok_bg.png
        07-transition-videos/
            attempts/
            approved/tiktok_video.mp4
        09-final-output/email_body.txt

Зависимости:
    pip install pillow requests google-generativeai

ENV:
    EMAIL_FROM        — отправитель (mail.ru)
    EMAIL_TO          — получатель
    EMAIL_PASSWORD    — пароль приложения
    GEMINI_API_KEY    — опционально
"""

import math
import os
import json
import random
import re
import shutil
import smtplib
import ssl
import subprocess
import textwrap
import time
import urllib.parse
import warnings
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

warnings.filterwarnings("ignore", category=FutureWarning)

# ══════════════════════════════════════════════════════════════
#  ENV
# ══════════════════════════════════════════════════════════════
EMAIL_FROM  = os.environ.get("EMAIL_FROM", "")
EMAIL_TO    = os.environ.get("EMAIL_TO", "")
EMAIL_PASS  = os.environ.get("EMAIL_PASSWORD", "")
GEMINI_KEY  = os.environ.get("GEMINI_API_KEY", "")

SMTP_SERVER = "smtp.mail.ru"
SMTP_PORT   = 465

# ══════════════════════════════════════════════════════════════
#  PROJECT FOLDERS  (storyboard structure)
# ══════════════════════════════════════════════════════════════

def make_project_dirs(base: Path) -> dict:
    dirs = {
        "brief_approved":   base / "01-creative-brief"    / "approved",
        "prompts_approved": base / "04-image-prompts"     / "approved",
        "frames_attempts":  base / "05-storyboard-frames" / "attempts",
        "frames_approved":  base / "05-storyboard-frames" / "approved",
        "video_attempts":   base / "07-transition-videos" / "attempts",
        "video_approved":   base / "07-transition-videos" / "approved",
        "final":            base / "09-final-output",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def write_brief(dirs: dict, plan: dict, today: str) -> None:
    brief = (
        f"# Creative Brief\n\n"
        f"**Дата:** {today}\n"
        f"**Тема:** {plan.get('topic', '—')}\n\n"
        f"## Pinterest\n"
        f"**Заголовок:** {plan['pinterest'].get('title','')}\n"
        f"**Описание:** {plan['pinterest'].get('description','')}\n\n"
        f"## Telegram\n"
        f"{plan['telegram'].get('text','')}\n\n"
        f"**CTA:** {plan['telegram'].get('cta','')}\n\n"
        f"## TikTok Script\n"
    )
    for i, scene in enumerate(plan["tiktok"].get("script", []), 1):
        brief += f"- Сцена {i}: {scene}\n"
    (dirs["brief_approved"] / "brief.md").write_text(brief, encoding="utf-8")
    print("  ok brief.md")


def write_image_prompts(dirs: dict, plan: dict) -> None:
    prompts = (
        f"# Image Prompts\n\n"
        f"## Pinterest (1000x1500, mind-map infographic)\n"
        f"Topic: {plan.get('topic','')}\n"
        f"Title: {plan['pinterest'].get('title','')}\n\n"
        f"## Telegram (1080x1080, mind-map infographic)\n"
        f"Topic: {plan.get('topic','')}\n"
        f"Post text used as node content.\n\n"
        f"## TikTok Background (1080x1920, FLUX cinematic)\n"
        f"```\n{plan['tiktok'].get('image_prompt','')}\n```\n"
    )
    (dirs["prompts_approved"] / "prompts.md").write_text(prompts, encoding="utf-8")
    print("  ok prompts.md")


# ══════════════════════════════════════════════════════════════
#  CARD GENERATOR  (dark mind-map style)
# ══════════════════════════════════════════════════════════════
_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_ACCENT    = "#5b9bd5"
_BG        = "#1a1a1a"
_NODE_BG   = "#252525"
_NODE_LINE = "#444444"
_ARROW     = "#666666"


def _wrap(text: str, width: int) -> list:
    return textwrap.fill(text, width=width).split("\n")


def _grain(d, w: int, h: int, seed: int = 42) -> None:
    rng = random.Random(seed)
    for _ in range(20000):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, h - 1)
        v = rng.randint(200, 255)
        d.point((x, y), fill=(v, v, v, rng.randint(3, 14)))


def _dashed_line(d, x1, y1, x2, y2, steps=20) -> None:
    for s in range(steps):
        if s % 2 == 0:
            ax = int(x1 + (x2 - x1) * s / steps)
            ay = int(y1 + (y2 - y1) * s / steps)
            bx = int(x1 + (x2 - x1) * (s + 1) / steps)
            by = int(y1 + (y2 - y1) * (s + 1) / steps)
            d.line([ax, ay, bx, by], fill=_ARROW, width=2)


def _make_mindmap(title: str, subtitle: str, nodes: list, width: int, height: int, output: str) -> str:
    img = Image.new("RGB", (width, height), _BG)
    d   = ImageDraw.Draw(img, "RGBA")
    _grain(d, width, height)

    cx, cy   = width // 2, height // 2
    r_center = min(width, height) // 7

    for gr in range(r_center + 80, r_center, -1):
        alpha = int(35 * (1 - (gr - r_center) / 80))
        d.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], fill=(80, 80, 80, alpha))
    d.ellipse([cx - r_center, cy - r_center, cx + r_center, cy + r_center],
              fill="#2d2d2d", outline="#555", width=2)

    ts = max(28, min(52, int(r_center * 0.6)))
    f_title = ImageFont.truetype(_FONT_BOLD, ts)
    f_sub   = ImageFont.truetype(_FONT_REG,  max(16, ts // 2))

    title_lines = _wrap(title.upper(), width=12)
    total_th    = len(title_lines) * (ts + 6)
    for i, line in enumerate(title_lines):
        bb = d.textbbox((0, 0), line, font=f_title)
        tw = bb[2] - bb[0]
        d.text((cx - tw // 2, cy - total_th // 2 + i * (ts + 6)), line, font=f_title, fill="white")
    if subtitle:
        bb = d.textbbox((0, 0), subtitle, font=f_sub)
        tw = bb[2] - bb[0]
        d.text((cx - tw // 2, cy + total_th // 2 + 6), subtitle, font=f_sub, fill="#999")

    margin  = max(160, int(min(width, height) * 0.16))
    orbit   = min(width, height) // 2 - margin
    n       = len(nodes)
    node_w  = int(width * 0.22)
    line_h  = max(18, int(width * 0.022))
    f_lbl   = ImageFont.truetype(_FONT_BOLD, max(18, int(width * 0.024)))
    f_body  = ImageFont.truetype(_FONT_REG,  max(14, int(width * 0.018)))

    for i, node in enumerate(nodes):
        angle = i * 360 / n
        rad   = math.radians(angle)
        nx    = cx + int(orbit * math.sin(rad))
        ny    = cy - int(orbit * math.cos(rad))

        ex = cx + int((r_center + 12) * math.sin(rad))
        ey = cy - int((r_center + 12) * math.cos(rad))
        ae = cx + int((orbit - node_w // 2 - 14) * math.sin(rad))
        af = cy - int((orbit - node_w // 2 - 14) * math.cos(rad))
        _dashed_line(d, ex, ey, ae, af)
        d.ellipse([ae - 4, af - 4, ae + 4, af + 4], fill=_ARROW)

        label   = node["label"]
        wrapped = _wrap(node.get("body", ""), width=20)
        lbb     = d.textbbox((0, 0), label, font=f_lbl)
        lh      = lbb[3] - lbb[1]
        box_h   = lh + 14 + len(wrapped) * line_h + 16
        bx      = nx - node_w // 2
        by      = ny - box_h // 2

        d.rounded_rectangle([bx + 4, by + 4, bx + node_w + 4, by + box_h + 4], radius=8, fill=(0, 0, 0, 90))
        d.rounded_rectangle([bx, by, bx + node_w, by + box_h], radius=8, fill=_NODE_BG, outline=_NODE_LINE, width=1)
        r8 = 8
        d.rounded_rectangle([bx, by, bx + node_w, by + 4 + r8], radius=r8, fill=_ACCENT)
        d.rectangle([bx, by + r8, bx + node_w, by + 4 + r8], fill=_ACCENT)

        lw = d.textbbox((0, 0), label, font=f_lbl)[2]
        d.text((bx + (node_w - lw) // 2, by + 10), label, font=f_lbl, fill=_ACCENT)
        for j, bl in enumerate(wrapped):
            d.text((bx + 10, by + lh + 20 + j * line_h), bl, font=f_body, fill="#cccccc")

    img.save(output)
    return output


def _nodes_pinterest(plan: dict):
    p          = plan["pinterest"]
    topic      = plan.get("topic", "Тема")
    paragraphs = [x.strip() for x in plan["telegram"]["text"].split("\n\n") if x.strip()][:4]
    nodes      = []
    for para in paragraphs:
        clean = re.sub(r"[✨💛🌿☕🌸🍂📚🧘‍♀️🌊🪞📵💆‍♀️🌅]", "", para).strip()
        lines = clean.split("\n")
        nodes.append({"label": lines[0][:28], "body": " ".join(lines[1:])[:80]})
    if not nodes:
        nodes = [{"label": "Ключевая мысль", "body": p.get("description", "")[:80]}]
    return p.get("title", topic), topic, nodes[:6]


def _nodes_telegram(plan: dict):
    tg         = plan["telegram"]
    topic      = plan.get("topic", "Тема")
    paragraphs = [x.strip() for x in tg["text"].split("\n\n") if x.strip()]
    nodes      = []
    for para in paragraphs[:5]:
        clean = re.sub(r"[✨💛🌿☕🌸🍂📚🧘‍♀️🌊🪞📵💆‍♀️🌅]", "", para).strip()
        lines = clean.split("\n")
        nodes.append({"label": lines[0][:28].strip("•- "), "body": " ".join(lines[1:])[:75]})
    cta = tg.get("cta", "")
    if cta:
        nodes.append({"label": "Вопрос", "body": re.sub(r"[👇🤍💪]", "", cta)[:75]})
    return topic.upper(), "Подумай об этом", nodes[:6]


def generate_pinterest_card(plan: dict, output: str) -> str:
    title, subtitle, nodes = _nodes_pinterest(plan)
    return _make_mindmap(title, subtitle, nodes, 1000, 1500, output)


def generate_telegram_card(plan: dict, output: str) -> str:
    title, subtitle, nodes = _nodes_telegram(plan)
    return _make_mindmap(title, subtitle, nodes, 1080, 1080, output)


# ══════════════════════════════════════════════════════════════
#  TIKTOK BACKGROUND  (Pollinations FLUX)
# ══════════════════════════════════════════════════════════════
_TIKTOK_STYLE = (
    "vertical cinematic shot, moody atmospheric lighting, "
    "aesthetic vibe, warm golden hour colors, dreamy soft focus, "
    "lifestyle photography style, ultra realistic, "
    "no text, no watermark, no letters"
)


def generate_tiktok_bg(prompt: str, output: str) -> str:
    encoded = urllib.parse.quote(f"{prompt}, {_TIKTOK_STYLE}")
    seed    = random.randint(1, 999999)
    for model_name in ["flux", "flux-realism", "flux-cablyai"]:
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1080&height=1920&model={model_name}"
            f"&seed={seed}&nologo=true&enhance=true&nofeed=true"
        )
        print(f"  TikTok BG via {model_name}...")
        for attempt in range(2):
            try:
                if attempt:
                    time.sleep(8)
                r = requests.get(url, timeout=180)
                if r.status_code == 200 and len(r.content) > 15000:
                    with open(output, "wb") as f:
                        f.write(r.content)
                    print(f"  ok {Path(output).name} ({len(r.content)//1024}KB)")
                    return output
            except Exception as e:
                print(f"  {model_name}[{attempt}] error: {e}")
        time.sleep(3)
    print("  All BG models failed, stub created")
    open(output, "a").close()
    return output


# ══════════════════════════════════════════════════════════════
#  TIKTOK VIDEO  (ffmpeg)
# ══════════════════════════════════════════════════════════════

def create_tiktok_video(bg_path: str, script: list, output: str) -> str:
    print("  Rendering TikTok video...")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("  WARNING: ffmpeg not found")
        open(output, "a").close()
        return output

    has_bg  = os.path.exists(bg_path) and os.path.getsize(bg_path) > 15000
    filters = []

    for i, txt in enumerate(script):
        safe  = (txt.replace("'","").replace('"',"")
                    .replace(":"," ").replace("="," ")
                    .replace("\\","").replace("%"," процентов"))
        lines = textwrap.fill(safe, width=24).split("\n")
        for j, line in enumerate(lines):
            y = 1480 - (len(lines) * 80 // 2) + j * 80
            filters.append(
                f"drawtext=text='{line}'"
                f":fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                f":fontsize=52:fontcolor=white:x=(w-text_w)/2:y={y}"
                f":enable='between(t,{i*15},{(i+1)*15})'"
                f":box=1:boxcolor=black@0.5:boxborderw=28"
                f":shadowcolor=black@0.9:shadowx=2:shadowy=2"
            )

    vf_txt = ",".join(filters) if filters else "null"

    if has_bg:
        vf = ("loop=loop=-1:size=1:start=0,"
              "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920")
        if filters:
            vf += f",{vf_txt}"
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", bg_path,
               "-vf", vf, "-c:v", "libx264", "-t", "45",
               "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "22", output]
    else:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=#1a0a2e:s=1080x1920:d=45",
               "-vf", vf_txt, "-c:v", "libx264", "-t", "45",
               "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "22", output]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if res.returncode == 0:
            print(f"  ok tiktok_video.mp4 ({os.path.getsize(output)/1024/1024:.1f}MB)")
        else:
            print(f"  ffmpeg error: {res.stderr[-300:]}")
            open(output, "a").close()
    except Exception as e:
        print(f"  Video ERROR: {e}")
        open(output, "a").close()
    return output


# ══════════════════════════════════════════════════════════════
#  CONTENT POOL
# ══════════════════════════════════════════════════════════════
CONTENT_POOL = [
    {
        "topic": "цифровое выгорание",
        "pinterest": {
            "title": "Разреши себе просто быть",
            "description": "Твой мозг устал не от работы — он устал от бесконечного шума. Иногда лучшее что ты можешь сделать — это ничего.",
        },
        "telegram": {
            "text": (
                "✨ Ты замечала, как после часа в соцсетях чувствуешь себя ещё более уставшей?\n\n"
                "Это не случайность. Наш мозг не создан для такого потока информации.\n\n"
                "Каждый раз когда ты листаешь ленту — ты тратишь ресурс, который мог бы пойти "
                "на творчество, отдых или просто на радость от момента.\n\n"
                "💛 Попробуй сегодня: 20 минут без телефона. Просто посиди. Понаблюдай за тишиной."
            ),
            "cta": "Напиши в комментариях — когда ты последний раз была в тишине без телефона? 👇",
        },
        "tiktok": {
            "script": [
                "Ты чувствуешь усталость хотя весь день просто листала телефон?",
                "Это называется цифровое выгорание. И это реальная проблема нашего времени.",
                "Отложи телефон прямо сейчас. Вдохни. Твой покой важнее чужих новостей.",
            ],
            "image_prompt": "woman peacefully putting down smartphone, looking at golden sunset through window, cinematic vertical shot, warm glowing light, silhouette mood",
        },
    },
    {
        "topic": "утреннее спокойствие",
        "pinterest": {
            "title": "Утро которое принадлежит тебе",
            "description": "Первый час утра — это твоё время. До уведомлений, до чужих ожиданий. Только ты и тишина.",
        },
        "telegram": {
            "text": (
                "🌅 Знаешь что происходит когда ты с утра первым делом берёшь телефон?\n\n"
                "Ты отдаёшь своё самое свежее, самое ценное утреннее внимание — чужим новостям, "
                "чужим проблемам, чужим жизням.\n\n"
                "А что если первые 30 минут утра — только твои?\n\n"
                "☕ Кофе. Тишина. Мысли о том, чего хочешь именно ты."
            ),
            "cta": "Как начинается твоё утро? Телефон или тишина? 🌿",
        },
        "tiktok": {
            "script": [
                "Стоп. Не бери телефон первые 30 минут после пробуждения.",
                "Вместо этого — кофе, окно, свои мысли. Звучит просто, меняет всё.",
                "Попробуй завтра. Одно утро. И посмотри как изменится твой день.",
            ],
            "image_prompt": "peaceful morning routine, woman looking out window with coffee, golden morning light, cozy home interior, vertical cinematic composition",
        },
    },
    {
        "topic": "медленная жизнь",
        "pinterest": {
            "title": "Медленно — это тоже движение",
            "description": "Мир кричит: быстрее, больше, продуктивнее. А что если твоя суперсила — это уметь замедлиться?",
        },
        "telegram": {
            "text": (
                "📚 Продуктивность — это не всегда про скорость.\n\n"
                "Иногда самое важное происходит в тишине. В паузе. В моменте когда ты "
                "просто сидишь и думаешь — без повестки, без таймера.\n\n"
                "Мы так боимся замедлиться, будто жизнь засчитывается только когда мы заняты.\n\n"
                "🍂 Но именно в медленных моментах рождаются лучшие идеи, решения и воспоминания."
            ),
            "cta": "Что для тебя значит медленная жизнь? Расскажи 👇",
        },
        "tiktok": {
            "script": [
                "Я перестала гнаться за продуктивностью. И вот что случилось.",
                "Появилось время думать. Чувствовать. Замечать маленькие радости.",
                "Медленная жизнь — это не лень. Это выбор качества вместо количества.",
            ],
            "image_prompt": "woman walking slowly in autumn park, fallen leaves, golden hour light, peaceful solitude, cinematic vertical frame, warm tones",
        },
    },
    {
        "topic": "границы и отдых",
        "pinterest": {
            "title": "Отдых — это не награда",
            "description": "Ты не должна заслуживать отдых. Он не выдаётся за хорошее поведение. Он просто нужен тебе.",
        },
        "telegram": {
            "text": (
                "💆‍♀️ «Отдохну когда всё сделаю» — самая опасная ловушка.\n\n"
                "Потому что список дел никогда не заканчивается. Никогда.\n\n"
                "А ты тем временем работаешь на износ, говоришь себе «ещё чуть-чуть» "
                "и удивляешься откуда эта пустота внутри.\n\n"
                "🌸 Отдых — это не финишная черта. Это часть пути. Каждый день."
            ),
            "cta": "Когда ты последний раз отдыхала без чувства вины? 🤍",
        },
        "tiktok": {
            "script": [
                "Ты снова говоришь себе что отдохнёшь потом?",
                "Потом не наступит пока ты сама не решишь что оно наступило.",
                "Дай себе разрешение прямо сейчас. Без условий. Ты это заслужила.",
            ],
            "image_prompt": "woman lying in flower field, eyes closed, peaceful expression, golden hour sunlight, dreamy bokeh, vertical cinematic shot",
        },
    },
    {
        "topic": "тревога и принятие",
        "pinterest": {
            "title": "Отпусти то что не твоё",
            "description": "Тревога часто живёт в будущем которое ещё не случилось. Возвращайся в сейчас — здесь безопаснее.",
        },
        "telegram": {
            "text": (
                "🧘 Тревога врёт.\n\n"
                "Она говорит тебе что всё пойдёт не так. Что ты недостаточно хороша. "
                "Что нужно контролировать всё и всех.\n\n"
                "Но вот правда: большинство того о чём мы беспокоимся — никогда не происходит.\n\n"
                "🌊 Попробуй прямо сейчас: три глубоких вдоха. Что реально происходит в эту секунду? "
                "Скорее всего — всё в порядке."
            ),
            "cta": "Чем ты успокаиваешь себя в моменты тревоги? Делись — это помогает другим 🤍",
        },
        "tiktok": {
            "script": [
                "Твоя тревога думает о будущем. Но ты живёшь прямо сейчас.",
                "Три вдоха. Что происходит в эту секунду? Назови пять вещей которые видишь.",
                "Это называется заземление. И это работает. Попробуй прямо сейчас.",
            ],
            "image_prompt": "hands holding small plant in soil, grounding concept, natural light, earthy tones, mindfulness photography, vertical close-up shot",
        },
    },
    {
        "topic": "сравнение и самооценка",
        "pinterest": {
            "title": "Ты не соревнуешься ни с кем",
            "description": "Лента создана чтобы ты сравнивала себя с другими. Не давай алгоритму решать как ты себя чувствуешь.",
        },
        "telegram": {
            "text": (
                "🪞 Ты открываешь Instagram и через 10 минут чувствуешь что твоя жизнь недостаточно хороша?\n\n"
                "Это не твоя проблема. Это дизайн платформы.\n\n"
                "Люди показывают лучшие 1% своей жизни. Ты сравниваешь свои будни "
                "с чужими праздниками. Это нечестная игра.\n\n"
                "✨ Твоя жизнь — не контент. Она не обязана выглядеть красиво для чужих глаз."
            ),
            "cta": "Какой аккаунт заставляет тебя чувствовать себя хуже? Может пора отписаться? 💪",
        },
        "tiktok": {
            "script": [
                "Стоп. Ты снова сравниваешь себя с кем-то в интернете?",
                "Ты видишь их хайлайты. Не их 6 утра, не их слёзы, не их сомнения.",
                "Единственный человек с кем стоит себя сравнивать — это ты вчера.",
            ],
            "image_prompt": "woman confidently walking in city street, natural beauty, authentic moment, candid photography style, urban aesthetic, vertical shot",
        },
    },
    {
        "topic": "цифровой детокс",
        "pinterest": {
            "title": "Что если выключить всё это",
            "description": "День без соцсетей кажется страшным только первые два часа. Потом начинается что-то настоящее.",
        },
        "telegram": {
            "text": (
                "📵 Я провела день без телефона. Вот что произошло.\n\n"
                "Первые два часа — странная тревога. Рука сама тянулась к карману.\n\n"
                "Потом — тишина. Настоящая. Я заметила как пахнет кофе. Услышала птиц. "
                "Додумала мысль до конца.\n\n"
                "К вечеру пришло ощущение которое я не могу точно назвать. "
                "Кажется это называется — присутствие."
            ),
            "cta": "Ты когда-нибудь пробовала день без соцсетей? Что было сложнее всего? 👇",
        },
        "tiktok": {
            "script": [
                "Я убрала все соцсети на 24 часа. Вот что изменилось.",
                "Появилось время. Буквально — часы которых раньше не было. Это пугает.",
                "Попробуй завтра. Один день. Не удалить — просто не открывать.",
            ],
            "image_prompt": "smartphone lying on grass face down, person's bare feet visible, nature background, freedom concept, warm summer light, vertical cinematic",
        },
    },
]

# ══════════════════════════════════════════════════════════════
#  PLAN GENERATION  — каждый запуск уникален
# ══════════════════════════════════════════════════════════════

# Расширенный банк тем: больше тем = меньше повторений
_TOPICS = [
    "цифровое выгорание", "утреннее спокойствие", "медленная жизнь",
    "границы и отдых", "тревога и принятие", "сравнение и самооценка",
    "цифровой детокс", "внутренний критик", "синдром самозванца",
    "прокрастинация", "одиночество в толпе", "страх осуждения",
    "перфекционизм", "эмоциональное истощение", "потеря смысла",
    "зависимость от одобрения", "токсичная продуктивность",
    "страх перемен", "самосаботаж", "ценность тишины",
]

# Банки вариаций для каждого элемента поста
_HOOKS = [
    "Ты замечала, как {trigger}?",
    "Стоп. А ты когда последний раз {trigger}?",
    "Есть кое-что важное о {topic}, о чём никто не говорит.",
    "Почему {trigger} — это не твоя вина?",
    "{Topic} — это не слабость. Это сигнал.",
    "Ты снова говоришь себе «потом»? Поговорим о {topic}.",
    "Один вопрос: когда ты последний раз думала о себе, а не о других?",
    "Это может быть неудобно читать. Но важно.",
]

_MIDDLES = [
    (
        "Это не случайность и не твоя слабость.\n\n"
        "Это результат системы, которая зарабатывает на твоей тревоге, усталости и сомнениях.\n\n"
        "Каждый раз когда ты чувствуешь себя «недостаточно» — кто-то получает деньги за это ощущение."
    ),
    (
        "Наш мозг не создан для такого темпа.\n\n"
        "Он создан для пауз, для скуки, для медленных мыслей у окна.\n\n"
        "Когда ты не даёшь себе этого — он начинает кричать через тело и эмоции."
    ),
    (
        "Это тихо накапливается.\n\n"
        "Сначала просто усталость. Потом раздражение на пустом месте.\n\n"
        "Потом — ощущение что ты живёшь чужую жизнь по чужому сценарию."
    ),
    (
        "Никто не учит нас замечать этот момент.\n\n"
        "Момент когда «стараться» превращается в «уничтожать себя».\n\n"
        "Между ними — тонкая грань. И ты заслуживаешь её знать."
    ),
    (
        "Самое страшное — это не усталость.\n\n"
        "Страшно когда усталость становится фоном, нормой, «ну и ладно».\n\n"
        "Нет. Это не ладно. Это сигнал."
    ),
]

_ACTIONS = [
    "Попробуй сегодня: {minutes} минут без {thing}. Просто посиди. Понаблюдай.",
    "Одно маленькое действие: скажи себе «достаточно» прямо сейчас.",
    "Начни с малого: одно утро без телефона. Один вечер без плана.",
    "Разреши себе ничего не делать ровно {minutes} минут. Без вины.",
    "Напомни себе: ты не обязана быть продуктивной каждую секунду.",
    "Сделай что-то только для себя сегодня. Без причины. Просто потому что хочешь.",
]

_CTAS = [
    "Напиши в комментариях — как ты себя чувствуешь прямо сейчас? 👇",
    "А у тебя это есть? Поделись — ты не одна в этом 🤍",
    "Сохрани этот пост — пригодится в момент когда снова накроет 💛",
    "Расскажи — что помогает тебе в такие моменты? 👇",
    "Тегни подругу, которой это нужно сегодня 🌿",
    "Как давно ты это чувствуешь? Напиши цифру в комментариях 👇",
    "Что из этого откликнулось больше всего? 💬",
]

_HOOKS_TRIGGERS = {
    "цифровое выгорание":         ("листаешь телефон и чувствуешь пустоту", "цифровое выгорание"),
    "утреннее спокойствие":       ("просыпаешься уже уставшей", "утреннее время"),
    "медленная жизнь":            ("торопишься, но не знаешь куда", "скорость жизни"),
    "границы и отдых":            ("говоришь «ещё чуть-чуть» уже несколько часов", "отдых"),
    "тревога и принятие":         ("тревожишься о том, чего ещё нет", "тревога"),
    "сравнение и самооценка":     ("сравниваешь себя с чужими хайлайтами", "сравнение"),
    "цифровой детокс":            ("чувствуешь зависимость от телефона", "детокс"),
    "внутренний критик":          ("критикуешь себя жёстче, чем любого другого", "внутренний критик"),
    "синдром самозванца":         ("думаешь что тебя «раскроют»", "синдром самозванца"),
    "прокрастинация":             ("откладываешь важное снова и снова", "прокрастинация"),
    "одиночество в толпе":        ("чувствуешь себя одинокой среди людей", "одиночество"),
    "страх осуждения":            ("сдерживаешь себя из-за чужого мнения", "страх осуждения"),
    "перфекционизм":              ("не начинаешь пока не будет идеально", "перфекционизм"),
    "эмоциональное истощение":   ("устала чувствовать", "эмоциональное истощение"),
    "потеря смысла":              ("делаешь всё правильно, но что-то не так", "смысл"),
    "зависимость от одобрения":   ("ждёшь реакции других прежде чем решить", "одобрение"),
    "токсичная продуктивность":   ("чувствуешь вину за отдых", "продуктивность"),
    "страх перемен":              ("знаешь что надо изменить, но не меняешь", "перемены"),
    "самосаботаж":                ("мешаешь себе когда всё идёт хорошо", "самосаботаж"),
    "ценность тишины":            ("не помнишь когда была в настоящей тишине", "тишина"),
}

_TIKTOK_PROMPTS = [
    "woman looking out rain window golden hour cinematic vertical moody",
    "hands holding warm cup steam morning light bokeh vertical lifestyle",
    "silhouette woman sunset window curtains golden glow cinematic vertical",
    "woman in cozy sweater autumn park leaves falling vertical dreamy",
    "close up hands writing journal morning light flowers vertical aesthetic",
    "woman meditating forest sunrays peaceful vertical cinematic warm tones",
    "empty road fog morning mist peaceful solitude vertical cinematic",
    "candle flame close up bokeh dark background warm amber vertical",
    "woman sitting rooftop city lights night dreamy vertical cinematic",
    "wildflowers field golden hour wind blur vertical aesthetic lifestyle",
]

_PIN_TITLES = {
    "цифровое выгорание":        ["Разреши себе просто быть", "Мозг просит тишины", "Усталость — это сигнал"],
    "утреннее спокойствие":      ["Утро которое принадлежит тебе", "До уведомлений — твоё время", "Тихое утро меняет всё"],
    "медленная жизнь":           ["Медленно — это тоже движение", "Замедлись и почувствуй", "Скорость — не синоним жизни"],
    "границы и отдых":           ["Отдых — это не награда", "Ты не обязана заслуживать паузу", "Стоп — это тоже действие"],
    "тревога и принятие":        ["Отпусти то что не твоё", "Тревога врёт тебе", "Сейчас — единственное место"],
    "сравнение и самооценка":    ["Ты не соревнуешься ни с кем", "Сравнение крадёт радость", "Твоя жизнь не контент"],
    "цифровой детокс":           ["Что если выключить всё это", "Один день без шума", "Присутствие — это роскошь"],
    "внутренний критик":         ["Будь добрее к себе", "Ты говоришь с собой слишком жёстко", "Смени тон внутреннего голоса"],
    "синдром самозванца":        ["Ты заслуживаешь своё место", "Сомнения — не факты", "Достаточно быть собой"],
    "прокрастинация":            ["Начни с малого", "Откладывать — это тоже усилие", "Один шаг меняет всё"],
    "одиночество в толпе":       ["Быть рядом — не значит понять", "Одиночество в онлайне реально", "Ты не одна в этом"],
    "страх осуждения":           ["Живи для себя", "Чужое мнение — не правда о тебе", "Свобода от чужих ожиданий"],
    "перфекционизм":             ["Хорошо — уже достаточно", "Несовершенство — это честность", "Начни несовершенно"],
    "эмоциональное истощение":   ["Чувствовать — это нормально", "Дай себе право устать", "Восстановление — не слабость"],
    "потеря смысла":             ["Смысл находят в движении", "Пауза — это тоже путь", "Ищи маленькие радости"],
    "зависимость от одобрения":  ["Твоё мнение важнее", "Живи не для лайков", "Одобрение начинается внутри"],
    "токсичная продуктивность":  ["Отдых — это работа над собой", "Делать меньше — иногда больше", "Ценность не в занятости"],
    "страх перемен":             ["Перемены — это рост", "Неизвестность — не враг", "Шаг в неизвестное — смелость"],
    "самосаботаж":               ["Ты на своей стороне?", "Перестань мешать себе", "Ты заслуживаешь хорошего"],
    "ценность тишины":           ["Тишина — это не пустота", "В тишине слышишь себя", "Найди свою тишину"],
}


def _variate_plan(topic: str) -> dict:
    """
    Собирает уникальный план из банков вариаций.
    Каждый вызов — другой результат даже для той же темы.
    """
    trigger, topic_short = _HOOKS_TRIGGERS.get(
        topic, ("чувствуешь усталость без причины", topic)
    )

    hook_tpl  = random.choice(_HOOKS)
    hook      = (hook_tpl
                 .replace("{trigger}", trigger)
                 .replace("{topic}", topic_short)
                 .replace("{Topic}", topic_short.capitalize()))

    middle    = random.choice(_MIDDLES)

    action_tpl = random.choice(_ACTIONS)
    action     = (action_tpl
                  .replace("{minutes}", random.choice(["10", "15", "20", "30"]))
                  .replace("{thing}",   random.choice(["телефона", "соцсетей", "новостей", "экрана"])))

    emoji_open  = random.choice(["✨", "💛", "🌿", "🌸", "🌊", "🍂", "☕", "🪴"])
    emoji_mid   = random.choice(["💡", "🔍", "📌", "👀", "🤔", "💭"])
    emoji_close = random.choice(["🌿", "💛", "🤍", "✨", "🌸"])

    tg_text = (
        f"{emoji_open} {hook}\n\n"
        f"{emoji_mid} {middle}\n\n"
        f"{emoji_close} {action}"
    )

    cta = random.choice(_CTAS)

    titles    = _PIN_TITLES.get(topic, [f"О {topic}"])
    pin_title = random.choice(titles)

    pin_descriptions = [
        f"{hook} — это не случайность. Это система. И ты можешь её изменить.",
        f"Если это откликается — ты не одна. {topic.capitalize()} касается каждой из нас.",
        f"Иногда важнее остановиться, чем продолжать. Особенно когда речь о {topic_short}.",
    ]

    tiktok_scripts = [
        [hook, middle.split("\n\n")[0], action],
        [
            f"Это про {topic_short}. И это важно.",
            middle.split("\n\n")[1] if "\n\n" in middle else middle,
            f"{action} Начни прямо сейчас.",
        ],
        [
            f"Один вопрос про {topic_short}.",
            middle.split("\n\n")[0],
            cta.replace("👇", "").replace("🤍", "").replace("💛", "").strip(),
        ],
    ]

    return {
        "topic": topic,
        "pinterest": {
            "title":       pin_title,
            "description": random.choice(pin_descriptions),
        },
        "telegram": {
            "text": tg_text,
            "cta":  cta,
        },
        "tiktok": {
            "script":       random.choice(tiktok_scripts),
            "image_prompt": random.choice(_TIKTOK_PROMPTS),
        },
    }


def _generate_plan_gemini():
    if not GEMINI_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        print(f"Gemini init error: {e}")
        return None

    # Берём случайную тему — НЕ детерминированную по дню
    topic = random.choice(_TOPICS)
    # Добавляем случайный угол чтобы даже одна тема давала разный текст
    angle = random.choice([
        "личный опыт от первого лица",
        "научный факт + личный вывод",
        "неожиданный поворот мышления",
        "история без морали в конце",
        "жёсткая честность без утешений",
        "нежная поддержка без советов",
    ])

    prompt = (
        "Ты профессиональный SMM-автор для женской аудитории 25-35 лет. "
        "Пиши живо, честно, без клише. "
        "Верни ТОЛЬКО валидный JSON без markdown.\n\n"
        f"Тема: {topic}\n"
        f"Угол подачи: {angle}\n\n"
        "JSON структура:\n"
        '{\n  "topic": "тема",\n'
        '  "pinterest": {\n'
        '    "title": "3-5 слов, цепляющий, без глаголов-призывов",\n'
        '    "description": "2 предложения, эмоционально и точно"\n  },\n'
        '  "telegram": {\n'
        '    "text": "3-4 абзаца с эмодзи, живой текст, не список",\n'
        '    "cta": "вопрос в комментарии, не банальный"\n  },\n'
        '  "tiktok": {\n'
        '    "script": ["крючок 1 предложение", "основная мысль 2 предложения", "вывод-действие"],\n'
        '    "image_prompt": "english cinematic vertical photo prompt, no text, 9:16"\n  }\n}\n'
        "Текст на русском, image_prompt на английском. Только JSON."
    )
    try:
        print(f"Gemini: topic='{topic}', angle='{angle}'")
        raw = model.generate_content(prompt).text.strip()
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1).strip()
        plan = json.loads(raw)
        for s in ("pinterest", "telegram", "tiktok"):
            if s not in plan:
                return None
        print(f"Gemini OK: topic='{plan.get('topic','?')}'")
        return plan
    except Exception as e:
        print(f"Gemini ERROR ({type(e).__name__}): {e}")
        return None


def generate_plan() -> dict:
    # 1. Пробуем Gemini (всегда случайная тема + случайный угол)
    plan = _generate_plan_gemini()
    if plan:
        return plan
    # 2. Fallback: вариатор на Python — уникальный каждый раз
    topic = random.choice(_TOPICS)
    print(f"Fallback variator: topic='{topic}'")
    return _variate_plan(topic)


# ══════════════════════════════════════════════════════════════
#  EMAIL
# ══════════════════════════════════════════════════════════════

def send_email(subject: str, body: str, attachments=None) -> None:
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASS]):
        print("WARNING: email creds missing")
        return

    msg = MIMEMultipart()
    msg["From"], msg["To"], msg["Subject"] = EMAIL_FROM, EMAIL_TO, subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    attached = []
    for path in (attachments or []):
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            print(f"  Skipping empty: {path}")
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
            attached.append(name)
        except Exception as e:
            print(f"  Attach error {name}: {e}")

    print(f"Sending email, {len(attached)} attachments: {attached}")
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ssl.create_default_context()) as s:
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.send_message(msg)
        print("ok Email sent!")
    except smtplib.SMTPAuthenticationError as e:
        print(f"AUTH FAILED: {e}")
        print("mail.ru -> Настройки -> Безопасность -> Пароли для внешних приложений")
    except Exception as e:
        print(f"send_email ERROR: {e}")


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def check_secrets() -> None:
    print("--- SECRETS ---")
    print(f"GEMINI_API_KEY  {'OK len='+str(len(GEMINI_KEY)) if GEMINI_KEY else 'MISSING (pool fallback)'}")
    print(f"EMAIL_FROM      {'SET' if EMAIL_FROM else 'MISSING!'}")
    print(f"EMAIL_TO        {'SET' if EMAIL_TO else 'MISSING!'}")
    print(f"EMAIL_PASSWORD  {'OK len='+str(len(EMAIL_PASS)) if EMAIL_PASS else 'MISSING!'}")
    print(f"SMTP            {SMTP_SERVER}:{SMTP_PORT}")
    print("---------------")


def main() -> None:
    today   = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"=== START: {now_str} ===")
    check_secrets()

    # Storyboard project folder
    base = Path("projects") / today
    dirs = make_project_dirs(base)
    print(f"Project folder: {base}/")

    plan = generate_plan()

    print("\n[1/5] Writing creative brief...")
    write_brief(dirs, plan, now_str)

    print("\n[2/5] Writing image prompts...")
    write_image_prompts(dirs, plan)

    print("\n[3/5] Generating storyboard frames...")
    pin_attempt = str(dirs["frames_attempts"] / "pinterest_pin.png")
    tg_attempt  = str(dirs["frames_attempts"] / "telegram_post.png")
    bg_attempt  = str(dirs["frames_attempts"] / "tiktok_bg.png")

    generate_pinterest_card(plan, pin_attempt)
    generate_telegram_card(plan,  tg_attempt)
    generate_tiktok_bg(plan["tiktok"]["image_prompt"], bg_attempt)

    pin_img   = str(dirs["frames_approved"] / "pinterest_pin.png")
    tg_img    = str(dirs["frames_approved"] / "telegram_post.png")
    tiktok_bg = str(dirs["frames_approved"] / "tiktok_bg.png")

    for src, dst in [(pin_attempt, pin_img), (tg_attempt, tg_img), (bg_attempt, tiktok_bg)]:
        if os.path.exists(src) and os.path.getsize(src) > 0:
            shutil.copy2(src, dst)
            print(f"  ok approved: {Path(dst).name}")

    print("\n[4/5] Rendering TikTok video...")
    vid_attempt = str(dirs["video_attempts"] / "tiktok_video.mp4")
    create_tiktok_video(tiktok_bg, plan["tiktok"]["script"], vid_attempt)

    video = str(dirs["video_approved"] / "tiktok_video.mp4")
    if os.path.exists(vid_attempt) and os.path.getsize(vid_attempt) > 0:
        shutil.copy2(vid_attempt, video)
        print("  ok approved: tiktok_video.mp4")

    tiktok_script = "\n".join(f"  Сцена {i+1}: {s}" for i, s in enumerate(plan["tiktok"]["script"]))
    email_body = (
        f"📅 Дата: {now_str}\n"
        f"🎯 Тема: {plan.get('topic','—')}\n\n"
        f"{'='*45}\n📌 PINTEREST\n{'='*45}\n"
        f"Заголовок: {plan['pinterest']['title']}\n"
        f"Описание:  {plan['pinterest'].get('description','')}\n\n"
        f"{'='*45}\n✈️  TELEGRAM POST\n{'='*45}\n"
        f"{plan['telegram']['text']}\n\n"
        f"CTA: {plan['telegram']['cta']}\n\n"
        f"{'='*45}\n🎵 TIKTOK СЦЕНАРИЙ\n{'='*45}\n"
        f"{tiktok_script}\n\n"
        f"{'='*45}\n📁 Файлы: projects/{today}/\n"
        f"  05-storyboard-frames/approved/pinterest_pin.png\n"
        f"  05-storyboard-frames/approved/telegram_post.png\n"
        f"  05-storyboard-frames/approved/tiktok_bg.png\n"
        f"  07-transition-videos/approved/tiktok_video.mp4\n"
    )
    (dirs["final"] / "email_body.txt").write_text(email_body, encoding="utf-8")

    print("\n[5/5] Sending email...")
    send_email(
        subject=f"🎨 Контент {now_str} | {plan.get('topic','')}",
        body=email_body,
        attachments=[pin_img, tg_img, tiktok_bg, video],
    )

    print(f"\n=== ALL DONE === Project: projects/{today}/")


if __name__ == "__main__":
    main()
