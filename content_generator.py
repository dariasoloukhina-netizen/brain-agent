"""
SMM Content Bot
===============
Генерирует ежедневный контент-план для Pinterest, Telegram и TikTok.
Карточки Pinterest и Telegram — инфографика в стиле mind-map (Pillow).
TikTok — атмосферный фон через Pollinations FLUX + видео через ffmpeg.
Готовый контент отправляется на email.

Зависимости:
    pip install pillow requests google-generativeai

ENV переменные:
    EMAIL_FROM        — адрес отправителя (mail.ru)
    EMAIL_TO          — адрес получателя
    EMAIL_PASSWORD    — пароль приложения mail.ru
    GEMINI_API_KEY    — опционально; без него берётся план из пула
"""

import math
import os
import json
import random
import re
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
#  CARD GENERATOR  (стиль: тёмный mind-map)
# ══════════════════════════════════════════════════════════════
_FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_ACCENT    = "#5b9bd5"
_BG        = "#1a1a1a"
_NODE_BG   = "#252525"
_NODE_LINE = "#444444"
_ARROW     = "#666666"


def _wrap(text: str, width: int) -> list[str]:
    return textwrap.fill(text, width=width).split("\n")


def _grain(d: ImageDraw.Draw, w: int, h: int, seed: int = 42) -> None:
    rng = random.Random(seed)
    for _ in range(20000):
        x = rng.randint(0, w - 1)
        y = rng.randint(0, h - 1)
        v = rng.randint(200, 255)
        d.point((x, y), fill=(v, v, v, rng.randint(3, 14)))


def _dashed_line(d, x1, y1, x2, y2, steps=20, color=_ARROW, width=2) -> None:
    for s in range(steps):
        if s % 2 == 0:
            ax = int(x1 + (x2 - x1) * s / steps)
            ay = int(y1 + (y2 - y1) * s / steps)
            bx = int(x1 + (x2 - x1) * (s + 1) / steps)
            by = int(y1 + (y2 - y1) * (s + 1) / steps)
            d.line([ax, ay, bx, by], fill=color, width=width)


def _make_mindmap(
    title: str,
    subtitle: str,
    nodes: list[dict],
    width: int,
    height: int,
    output: str,
    accent: str = _ACCENT,
) -> str:
    """
    Рисует тёмную инфографику с центральным блоком и узлами вокруг.
    nodes = [{"label": str, "body": str}, ...]
    """
    img = Image.new("RGB", (width, height), _BG)
    d   = ImageDraw.Draw(img, "RGBA")
    _grain(d, width, height)

    cx, cy   = width // 2, height // 2
    r_center = min(width, height) // 7

    # Свечение за центральным кругом
    for gr in range(r_center + 80, r_center, -1):
        alpha = int(35 * (1 - (gr - r_center) / 80))
        d.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], fill=(80, 80, 80, alpha))
    d.ellipse(
        [cx - r_center, cy - r_center, cx + r_center, cy + r_center],
        fill="#2d2d2d", outline="#555", width=2,
    )

    # Текст центра
    ts = max(28, min(52, int(r_center * 0.6)))
    f_title = ImageFont.truetype(_FONT_BOLD, ts)
    f_sub   = ImageFont.truetype(_FONT_REG,  max(16, ts // 2))

    title_lines = _wrap(title.upper(), width=12)
    total_th    = len(title_lines) * (ts + 6)
    for i, line in enumerate(title_lines):
        bb = d.textbbox((0, 0), line, font=f_title)
        tw = bb[2] - bb[0]
        d.text((cx - tw // 2, cy - total_th // 2 + i * (ts + 6)), line,
               font=f_title, fill="white")
    if subtitle:
        bb = d.textbbox((0, 0), subtitle, font=f_sub)
        tw = bb[2] - bb[0]
        d.text((cx - tw // 2, cy + total_th // 2 + 6), subtitle,
               font=f_sub, fill="#999")

    # Узлы
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

        # Стрелка
        ex = cx + int((r_center + 12) * math.sin(rad))
        ey = cy - int((r_center + 12) * math.cos(rad))
        ae = cx + int((orbit - node_w // 2 - 14) * math.sin(rad))
        af = cy - int((orbit - node_w // 2 - 14) * math.cos(rad))
        _dashed_line(d, ex, ey, ae, af, steps=22)
        d.ellipse([ae - 4, af - 4, ae + 4, af + 4], fill=_ARROW)

        # Блок узла
        label   = node["label"]
        wrapped = _wrap(node.get("body", ""), width=20)
        lbb     = d.textbbox((0, 0), label, font=f_lbl)
        lh      = lbb[3] - lbb[1]
        box_h   = lh + 14 + len(wrapped) * line_h + 16
        bx      = nx - node_w // 2
        by      = ny - box_h // 2

        d.rounded_rectangle([bx + 4, by + 4, bx + node_w + 4, by + box_h + 4],
                             radius=8, fill=(0, 0, 0, 90))
        d.rounded_rectangle([bx, by, bx + node_w, by + box_h],
                             radius=8, fill=_NODE_BG, outline=_NODE_LINE, width=1)
        # Цветная полоска сверху
        r8 = 8
        d.rounded_rectangle([bx, by, bx + node_w, by + 4 + r8], radius=r8, fill=accent)
        d.rectangle([bx, by + r8, bx + node_w, by + 4 + r8], fill=accent)

        lw = d.textbbox((0, 0), label, font=f_lbl)[2]
        d.text((bx + (node_w - lw) // 2, by + 10), label, font=f_lbl, fill=accent)
        for j, bl in enumerate(wrapped):
            d.text((bx + 10, by + lh + 20 + j * line_h), bl, font=f_body, fill="#cccccc")

    img.save(output)
    return output


def _nodes_from_plan_pinterest(plan: dict) -> tuple[str, str, list[dict]]:
    p          = plan["pinterest"]
    topic      = plan.get("topic", "Тема")
    paragraphs = [x.strip() for x in plan["telegram"]["text"].split("\n\n") if x.strip()][:4]
    nodes      = []
    for para in paragraphs:
        clean      = re.sub(r"[✨💛🌿☕🌸🍂📚🧘‍♀️🌊🪞📵💆‍♀️🌅]", "", para).strip()
        first_line = clean.split("\n")[0]
        rest       = " ".join(clean.split("\n")[1:])[:80]
        nodes.append({"label": first_line[:28], "body": rest})
    if not nodes:
        nodes = [{"label": "Ключевая мысль", "body": p.get("description", "")[:80]}]
    return p.get("title", topic), topic, nodes[:6]


def _nodes_from_plan_telegram(plan: dict) -> tuple[str, str, list[dict]]:
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


def generate_pinterest_card(plan: dict, output: str = "pinterest_pin.png") -> str:
    title, subtitle, nodes = _nodes_from_plan_pinterest(plan)
    return _make_mindmap(title, subtitle, nodes, 1000, 1500, output)


def generate_telegram_card(plan: dict, output: str = "telegram_post.png") -> str:
    title, subtitle, nodes = _nodes_from_plan_telegram(plan)
    return _make_mindmap(title, subtitle, nodes, 1080, 1080, output)


# ══════════════════════════════════════════════════════════════
#  CONTENT POOL  (fallback без Gemini)
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
                "🧘‍♀️ Тревога врёт.\n\n"
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
#  PLAN GENERATION
# ══════════════════════════════════════════════════════════════
_TIKTOK_STYLE = (
    "vertical cinematic shot, moody atmospheric lighting, "
    "aesthetic vibe, warm golden hour colors, dreamy soft focus, "
    "lifestyle photography style, ultra realistic, "
    "no text, no watermark, no letters"
)


def _get_todays_plan() -> dict:
    day   = datetime.now().timetuple().tm_yday
    plan  = CONTENT_POOL[day % len(CONTENT_POOL)]
    print(f"Pool topic: '{plan['topic']}' (day {day}, idx {day % len(CONTENT_POOL)})")
    return plan


def _generate_plan_gemini() -> dict | None:
    if not GEMINI_KEY:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        print(f"Gemini init error: {e}")
        return None

    topic  = random.choice([p["topic"] for p in CONTENT_POOL])
    prompt = (
        "Ты профессиональный SMM-стратег. Создай эмоциональный цепляющий контент-план. "
        "Верни ТОЛЬКО валидный JSON без markdown и пояснений.\n\n"
        f"Тема: {topic}\n\n"
        "Структура JSON:\n"
        '{\n  "topic": "тема",\n'
        '  "pinterest": {\n'
        '    "title": "заголовок на русском 3-6 слов",\n'
        '    "description": "описание 2-3 предложения"\n  },\n'
        '  "telegram": {\n'
        '    "text": "пост 3-4 абзаца с эмодзи",\n'
        '    "cta": "вовлекающий вопрос"\n  },\n'
        '  "tiktok": {\n'
        '    "script": ["крючок", "основная мысль", "вывод"],\n'
        '    "image_prompt": "английский промпт для вертикального фона 9:16"\n  }\n}\n'
        "Текст на русском, image_prompt на английском. Только JSON."
    )
    try:
        print("Requesting plan from Gemini...")
        raw = model.generate_content(prompt).text.strip()
        if "```" in raw:
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1).strip()
        plan = json.loads(raw)
        for s in ("pinterest", "telegram", "tiktok"):
            if s not in plan:
                return None
        print(f"Gemini OK: topic='{plan.get('topic', '?')}'")
        return plan
    except Exception as e:
        print(f"Gemini ERROR ({type(e).__name__}): {e}")
        return None


def generate_plan() -> dict:
    return _generate_plan_gemini() or (_get_todays_plan() if not print("Using pool fallback") else None)


# ══════════════════════════════════════════════════════════════
#  TIKTOK BACKGROUND  (Pollinations FLUX)
# ══════════════════════════════════════════════════════════════
def generate_tiktok_bg(prompt: str, output: str = "tiktok_bg.png") -> str:
    encoded = urllib.parse.quote(f"{prompt}, {_TIKTOK_STYLE}")
    seed    = random.randint(1, 999999)
    for model_name in ["flux", "flux-realism", "flux-cablyai"]:
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width=1080&height=1920&model={model_name}"
            f"&seed={seed}&nologo=true&enhance=true&nofeed=true"
        )
        print(f"TikTok BG via {model_name}...")
        for attempt in range(2):
            try:
                if attempt:
                    time.sleep(8)
                r = requests.get(url, timeout=180)
                if r.status_code == 200 and len(r.content) > 15000:
                    with open(output, "wb") as f:
                        f.write(r.content)
                    print(f"  Saved {output} ({len(r.content)//1024}KB)")
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
def create_tiktok_video(bg_path: str, script: list[str], output: str = "tiktok_video.mp4") -> str:
    print("Rendering TikTok video...")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("WARNING: ffmpeg not found")
        open(output, "a").close()
        return output

    has_bg  = os.path.exists(bg_path) and os.path.getsize(bg_path) > 15000
    filters = []

    for i, txt in enumerate(script):
        safe  = txt.replace("'","").replace('"',"").replace(":"," ").replace("="," ").replace("\\","").replace("%"," процентов")
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
        vf = "loop=loop=-1:size=1:start=0,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
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
            print(f"Video ready: {output} ({os.path.getsize(output)/1024/1024:.1f}MB)")
        else:
            print(f"ffmpeg error: {res.stderr[-300:]}")
            open(output, "a").close()
    except Exception as e:
        print(f"Video ERROR: {e}")
        open(output, "a").close()
    return output


# ══════════════════════════════════════════════════════════════
#  EMAIL
# ══════════════════════════════════════════════════════════════
def send_email(subject: str, body: str, attachments: list[str] | None = None) -> None:
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASS]):
        print(f"WARNING: email creds missing (FROM={'SET' if EMAIL_FROM else 'EMPTY'}, "
              f"TO={'SET' if EMAIL_TO else 'EMPTY'}, PASS={'SET' if EMAIL_PASS else 'EMPTY'})")
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
        print("Email sent OK!")
    except smtplib.SMTPAuthenticationError as e:
        print(f"AUTH FAILED: {e}\nmail.ru → Настройки → Безопасность → Пароли для внешних приложений")
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
    today = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"=== START: {today} ===")
    check_secrets()

    plan = generate_plan()

    # Инфографика (Pillow, стиль mind-map)
    pin_img = generate_pinterest_card(plan, "pinterest_pin.png")
    tg_img  = generate_telegram_card(plan,  "telegram_post.png")

    # TikTok фон (FLUX) + видео (ffmpeg)
    tiktok_bg = generate_tiktok_bg(plan["tiktok"]["image_prompt"], "tiktok_bg.png")
    video     = create_tiktok_video(tiktok_bg, plan["tiktok"]["script"])

    tiktok_script = "\n".join(f"  Сцена {i+1}: {s}" for i, s in enumerate(plan["tiktok"]["script"]))

    body = (
        f"📅 Дата: {today}\n"
        f"🎯 Тема: {plan.get('topic','—')}\n\n"
        f"{'='*45}\n"
        f"📌 PINTEREST\n{'='*45}\n"
        f"Заголовок: {plan['pinterest']['title']}\n"
        f"Описание:  {plan['pinterest'].get('description','')}\n\n"
        f"{'='*45}\n"
        f"✈️  TELEGRAM POST\n{'='*45}\n"
        f"{plan['telegram']['text']}\n\n"
        f"CTA: {plan['telegram']['cta']}\n\n"
        f"{'='*45}\n"
        f"🎵 TIKTOK СЦЕНАРИЙ\n{'='*45}\n"
        f"{tiktok_script}\n\n"
        f"{'='*45}\n"
        f"📎 Вложения:\n"
        f"  • pinterest_pin.png  — инфографика 1000x1500\n"
        f"  • telegram_post.png  — инфографика 1080x1080\n"
        f"  • tiktok_bg.png      — фон видео 1080x1920\n"
        f"  • tiktok_video.mp4   — видео 45 сек\n"
    )

    send_email(
        subject=f"🎨 Контент {today} | {plan.get('topic','')}",
        body=body,
        attachments=[pin_img, tg_img, tiktok_bg, video],
    )

    print("=== ALL DONE ===")


if __name__ == "__main__":
    main()
