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
import time
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.base import MIMEBase
from email import encoders

warnings.filterwarnings("ignore", category=FutureWarning)

# ==================== ENV VARS ====================
EMAIL_FROM  = os.environ.get("EMAIL_FROM", "")
EMAIL_TO    = os.environ.get("EMAIL_TO", "")
EMAIL_PASS  = os.environ.get("EMAIL_PASSWORD", "")
GEMINI_KEY  = os.environ.get("GEMINI_API_KEY", "")

SMTP_SERVER = "smtp.mail.ru"
SMTP_PORT   = 465

# ==================== СТИЛИ ДЛЯ КАРТИНОК ====================
PINTEREST_STYLE = (
    "ultra detailed digital art, trending on pinterest, soft dreamy aesthetic, "
    "muted warm tones, cinematic lighting, bokeh background, "
    "cozy hygge atmosphere, professional photography style, "
    "8k resolution, beautiful composition, no text, no watermark, no letters"
)
TELEGRAM_STYLE = (
    "editorial illustration, modern graphic design, bold composition, "
    "warm color palette, professional digital art, eye-catching visual, "
    "social media ready, clean aesthetic, high contrast, "
    "no text, no watermark, no letters"
)
TIKTOK_STYLE = (
    "vertical cinematic shot, moody atmospheric lighting, "
    "aesthetic vibe, warm golden hour colors, dreamy soft focus, "
    "lifestyle photography style, ultra realistic, "
    "no text, no watermark, no letters"
)

# ==================== ГОТОВЫЕ ПЛАНЫ (FALLBACK ПУЛ) ====================
# 7 разных тем — каждый день будет новая тема по порядку
CONTENT_POOL = [
    {
        "topic": "цифровое выгорание",
        "pinterest": {
            "image_prompt": "cozy woman sitting by window with warm tea cup, soft morning light streaming in, plants around, dreamy bokeh background, muted warm tones, peaceful serene atmosphere",
            "title": "Разреши себе просто быть",
            "description": "Твой мозг устал не от работы — он устал от бесконечного шума. Иногда лучшее что ты можешь сделать — это ничего.",
        },
        "telegram": {
            "image_prompt": "minimalist flat lay with coffee cup, open journal and fresh flowers, warm morning light from window, aesthetic lifestyle, soft shadows",
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
            "image_prompt": "peaceful morning bedroom scene, soft sunlight through sheer curtains, white linen bedding, cup of tea on nightstand, plants, cozy hygge aesthetic, dreamy atmosphere",
            "title": "Утро которое принадлежит тебе",
            "description": "Первый час утра — это твоё время. До уведомлений, до чужих ожиданий. Только ты и тишина.",
        },
        "telegram": {
            "image_prompt": "serene morning coffee ritual, hands holding warm ceramic mug, soft natural light, cozy wooden table, minimalist aesthetic",
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
            "image_prompt": "slow living aesthetic, woman reading book in cozy armchair, autumn light, warm blanket, candles, botanical surroundings, hygge mood, film photography style",
            "title": "Медленно — это тоже движение",
            "description": "Мир кричит: быстрее, больше, продуктивнее. А что если твоя суперсила — это уметь замедлиться?",
        },
        "telegram": {
            "image_prompt": "cozy reading nook with books, warm lamp light, soft textiles, botanical prints on wall, aesthetic slow living interior",
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
            "image_prompt": "woman relaxing in bath with flowers and candles, spa aesthetic, rose petals, soft pink tones, luxury self-care, dreamy soft light, no face shown",
            "title": "Отдых — это не награда",
            "description": "Ты не должна заслуживать отдых. Он не выдаётся за хорошее поведение. Он просто нужен тебе.",
        },
        "telegram": {
            "image_prompt": "self care flatlay, bath salts, flowers, candles, journal, face mask, soft pink and white tones, spa aesthetic",
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
            "image_prompt": "person meditating by calm lake at sunset, silhouette, golden reflections on water, mountains in background, peaceful nature, spiritual atmosphere",
            "title": "Отпусти то что не твоё",
            "description": "Тревога часто живёт в будущем которое ещё не случилось. Возвращайся в сейчас — здесь безопаснее.",
        },
        "telegram": {
            "image_prompt": "calm meditation scene, candles and incense, person in peaceful pose, warm amber light, mindfulness aesthetic, zen atmosphere",
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
            "image_prompt": "confident woman looking at mirror with self-love, soft warm light, flowers on dresser, empowering feminine aesthetic, golden tones, beautiful composition",
            "title": "Ты не соревнуешься ни с кем",
            "description": "Лента создана чтобы ты сравнивала себя с другими. Не давай алгоритму решать как ты себя чувствуешь.",
        },
        "telegram": {
            "image_prompt": "woman smiling at her reflection in mirror surrounded by flowers, self love concept, warm golden light, empowering aesthetic",
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
            "image_prompt": "phone placed face down on wooden table with cup of tea and open book beside it, digital detox concept, warm natural light, cozy minimalist aesthetic",
            "title": "Что если выключить всё это",
            "description": "День без соцсетей кажется страшным только первые два часа. Потом начинается что-то настоящее.",
        },
        "telegram": {
            "image_prompt": "peaceful nature scene, person sitting on rock by forest stream, no phone, present moment, green lush surroundings, natural light",
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


# ==================== ДИАГНОСТИКА ====================
def check_secrets():
    print("--- SECRETS CHECK ---")
    print(f"GEMINI_API_KEY:    {'OK len=' + str(len(GEMINI_KEY)) if GEMINI_KEY else 'MISSING (will use fallback)'}")
    print(f"EMAIL_FROM:        {'SET' if EMAIL_FROM else 'MISSING!'}")
    print(f"EMAIL_TO:          {'SET' if EMAIL_TO else 'MISSING!'}")
    print(f"EMAIL_PASSWORD:    {'OK len=' + str(len(EMAIL_PASS)) if EMAIL_PASS else 'MISSING!'}")
    print(f"SMTP:              {SMTP_SERVER}:{SMTP_PORT} (hardcoded)")
    print("---------------------")


# ==================== ГЕНЕРАЦИЯ ПЛАНА ====================
def get_todays_plan():
    """Берёт план на сегодня из пула — каждый день новая тема."""
    day_index = datetime.now().timetuple().tm_yday  # день года 1-365
    plan = CONTENT_POOL[day_index % len(CONTENT_POOL)]
    print(f"Using content pool topic: '{plan['topic']}' (day {day_index}, index {day_index % len(CONTENT_POOL)})")
    return plan


def generate_plan_gemini():
    """Пробует сгенерировать план через Gemini. При ошибке — None."""
    if not GEMINI_KEY:
        return None

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
    except Exception as e:
        print(f"Gemini init error: {e}")
        return None

    topic = random.choice([p["topic"] for p in CONTENT_POOL])
    prompt = (
        "Ты профессиональный SMM-стратег. Создай эмоциональный цепляющий контент-план. "
        "Верни ТОЛЬКО валидный JSON без markdown и пояснений.\n\n"
        f"Тема: {topic}\n\n"
        "Структура JSON:\n"
        "{\n"
        '  "topic": "тема",\n'
        '  "pinterest": {\n'
        '    "image_prompt": "подробный английский промпт для красивого вертикального фото 2:3",\n'
        '    "title": "цепляющий заголовок на русском 3-6 слов",\n'
        '    "description": "описание на русском 2-3 предложения, эмоциональное"\n'
        "  },\n"
        '  "telegram": {\n'
        '    "image_prompt": "подробный английский промпт для квадратного фото 1:1",\n'
        '    "text": "текст поста на русском, 3-4 абзаца, честно и эмоционально, с эмодзи",\n'
        '    "cta": "вовлекающий вопрос для комментариев"\n'
        "  },\n"
        '  "tiktok": {\n'
        '    "script": ["сцена 1 — крючок", "сцена 2 — основная мысль", "сцена 3 — вывод"],\n'
        '    "image_prompt": "подробный английский промпт для вертикального фона 9:16"\n'
        "  }\n"
        "}\n"
        "Текст на русском, промпты на английском. Только JSON."
    )

    try:
        print("Requesting plan from Gemini...")
        response = model.generate_content(prompt)
        raw = response.text.strip()

        if "```" in raw:
            m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
            if m:
                raw = m.group(1).strip()

        plan = json.loads(raw)

        # Нормализуем — принимаем и "prompt" и "image_prompt"
        for section in ("pinterest", "telegram", "tiktok"):
            if section not in plan:
                return None
            if "prompt" in plan[section] and "image_prompt" not in plan[section]:
                plan[section]["image_prompt"] = plan[section].pop("prompt")
            if "image_prompt" not in plan[section]:
                return None

        print(f"Gemini plan OK: topic='{plan.get('topic', '?')}'")
        return plan

    except Exception as e:
        print(f"Gemini plan ERROR ({type(e).__name__}): {e}")
        return None


def generate_plan():
    """Пробует Gemini, при неудаче — берёт из пула."""
    plan = generate_plan_gemini()
    if plan:
        return plan
    print("Using content pool fallback")
    return get_todays_plan()


# ==================== КАРТИНКИ ====================
def generate_image_flux(prompt, width, height, filename, style):
    """Генерирует через Pollinations FLUX — лучшая бесплатная модель."""
    full_prompt = f"{prompt}, {style}"
    encoded = urllib.parse.quote(full_prompt)
    seed = random.randint(1, 999999)

    models_to_try = ["flux", "flux-realism", "flux-cablyai"]

    for model_name in models_to_try:
        url = (
            f"https://image.pollinations.ai/prompt/{encoded}"
            f"?width={width}&height={height}"
            f"&model={model_name}"
            f"&seed={seed}"
            f"&nologo=true"
            f"&enhance=true"
            f"&nofeed=true"
        )
        print(f"Generating '{filename}' via {model_name} ({width}x{height})...")

        for attempt in range(2):
            try:
                if attempt > 0:
                    time.sleep(8)
                r = requests.get(url, timeout=180)
                if r.status_code == 200 and len(r.content) > 15000:
                    with open(filename, "wb") as f:
                        f.write(r.content)
                    print(f"  Saved: {filename} ({len(r.content)//1024}KB) via {model_name}")
                    return filename
                else:
                    print(f"  {model_name} attempt {attempt+1}: status={r.status_code} size={len(r.content)}")
            except Exception as e:
                print(f"  {model_name} attempt {attempt+1} error: {e}")

        time.sleep(3)

    print(f"  All models failed for {filename}, creating stub")
    open(filename, "a").close()
    return filename


# ==================== ВИДЕО ====================
def create_tiktok_video(bg_path, script, output="tiktok_video.mp4"):
    print("Rendering TikTok video...")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        print("WARNING: ffmpeg not found")
        open(output, "a").close()
        return output

    has_bg = os.path.exists(bg_path) and os.path.getsize(bg_path) > 15000

    drawtext_filters = []
    for i, txt in enumerate(script):
        start = i * 15
        end = (i + 1) * 15
        safe = (txt
            .replace("'", "").replace('"', "")
            .replace(":", " ").replace("=", " ")
            .replace("\\", "").replace("%", " процентов")
        )
        lines = textwrap.fill(safe, width=24).split("\n")
        total = len(lines)
        for j, line in enumerate(lines):
            y = 1480 - (total * 80 // 2) + j * 80
            drawtext_filters.append(
                f"drawtext=text='{line}'"
                f":fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                f":fontsize=52:fontcolor=white"
                f":x=(w-text_w)/2:y={y}"
                f":enable='between(t,{start},{end})'"
                f":box=1:boxcolor=black@0.5:boxborderw=28"
                f":shadowcolor=black@0.9:shadowx=2:shadowy=2"
            )

    vf_text = ",".join(drawtext_filters) if drawtext_filters else "null"

    if has_bg:
        full_vf = (
            "loop=loop=-1:size=1:start=0,"
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )
        if drawtext_filters:
            full_vf += f",{vf_text}"
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", bg_path,
            "-vf", full_vf,
            "-c:v", "libx264", "-t", "45",
            "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "22",
            output,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=#1a0a2e:s=1080x1920:d=45",
            "-vf", vf_text,
            "-c:v", "libx264", "-t", "45",
            "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "22",
            output,
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            size_mb = os.path.getsize(output) / 1024 / 1024
            print(f"Video ready: {output} ({size_mb:.1f}MB)")
        else:
            print(f"ffmpeg error: {result.stderr[-300:]}")
            open(output, "a").close()
    except Exception as e:
        print(f"Video ERROR: {e}")
        open(output, "a").close()
    return output


# ==================== EMAIL ====================
def send_email(subject, body, attachments=None):
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASS]):
        print("WARNING: Email credentials missing")
        print(f"  FROM={'SET' if EMAIL_FROM else 'EMPTY'}, TO={'SET' if EMAIL_TO else 'EMPTY'}, PASS={'SET' if EMAIL_PASS else 'EMPTY'}")
        return

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
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
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ctx) as s:
            s.login(EMAIL_FROM, EMAIL_PASS)
            s.send_message(msg)
        print("Email sent OK!")
    except smtplib.SMTPAuthenticationError as e:
        print(f"AUTH FAILED: {e}")
        print("mail.ru: Настройки -> Безопасность -> Пароли для внешних приложений")
    except Exception as e:
        print(f"send_email ERROR: {e}")


# ==================== MAIN ====================
def main():
    today = datetime.now().strftime("%d.%m.%Y %H:%M")
    print(f"=== START: {today} ===")
    check_secrets()

    plan      = generate_plan()
    pin_img   = generate_image_flux(plan["pinterest"]["image_prompt"], 1000, 1500, "pinterest_pin.png",   PINTEREST_STYLE)
    tg_img    = generate_image_flux(plan["telegram"]["image_prompt"],  1080, 1080, "telegram_post.png",   TELEGRAM_STYLE)
    tiktok_bg = generate_image_flux(plan["tiktok"]["image_prompt"],    1080, 1920, "tiktok_bg.png",       TIKTOK_STYLE)
    video     = create_tiktok_video(tiktok_bg, plan["tiktok"]["script"])

    tiktok_script = "\n".join(
        f"  Сцена {i+1}: {s}" for i, s in enumerate(plan["tiktok"]["script"])
    )
    body = (
        f"📅 Дата: {today}\n"
        f"🎯 Тема: {plan.get('topic', '—')}\n\n"
        f"{'='*45}\n"
        f"📌 PINTEREST\n{'='*45}\n"
        f"Заголовок: {plan['pinterest']['title']}\n"
        f"Описание:  {plan['pinterest']['description']}\n\n"
        f"{'='*45}\n"
        f"✈️  TELEGRAM POST\n{'='*45}\n"
        f"{plan['telegram']['text']}\n\n"
        f"CTA: {plan['telegram']['cta']}\n\n"
        f"{'='*45}\n"
        f"🎵 TIKTOK СЦЕНАРИЙ\n{'='*45}\n"
        f"{tiktok_script}\n\n"
        f"{'='*45}\n"
        f"📎 Вложения:\n"
        f"  • pinterest_pin.png  — вертикальное 1000x1500\n"
        f"  • telegram_post.png  — квадратное 1080x1080\n"
        f"  • tiktok_bg.png      — фон видео 1080x1920\n"
        f"  • tiktok_video.mp4   — видео 45 сек\n"
    )

    send_email(
        subject=f"🎨 Контент {today} | {plan.get('topic', '')}",
        body=body,
        attachments=[pin_img, tg_img, tiktok_bg, video],
    )

    print("=== ALL DONE ===")


if __name__ == "__main__":
    main()
