"""OpenAI Realtime voice catalog and TTS voice-test synthesis for the dashboard.

Replaces the Hume voice-library module: OpenAI's realtime voices are a small
fixed set, so the "library" is a static list. The voice-test endpoint
synthesizes a short MP3 sample with the OpenAI TTS API (``gpt-4o-mini-tts``).
TTS voices approximate but do not perfectly match the realtime voices, and the
newest realtime-only voices (marin, cedar) are not available on the TTS
endpoint at all — those previews fall back to a documented stand-in.
"""

from openai import AsyncOpenAI

from insurance_agent.core.config import configuration
from insurance_agent.core.utils.logger import logger_config

logger = logger_config(__name__)

TTS_MODEL = "gpt-4o-mini-tts"

# Voices accepted by the OpenAI Realtime API (session.voice).
# https://platform.openai.com/docs/guides/realtime
REALTIME_VOICES: list[dict] = [
    {"id": "marin", "name": "Marin", "description": "Natural, expressive female voice (recommended)"},
    {"id": "cedar", "name": "Cedar", "description": "Natural, expressive male voice (recommended)"},
    {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced"},
    {"id": "ash", "name": "Ash", "description": "Warm male voice"},
    {"id": "ballad", "name": "Ballad", "description": "Calm, melodic male voice"},
    {"id": "coral", "name": "Coral", "description": "Bright, friendly female voice"},
    {"id": "echo", "name": "Echo", "description": "Clear male voice"},
    {"id": "sage", "name": "Sage", "description": "Soft, gentle female voice"},
    {"id": "shimmer", "name": "Shimmer", "description": "Energetic female voice"},
    {"id": "verse", "name": "Verse", "description": "Expressive male voice"},
]

_VOICE_IDS = {v["id"] for v in REALTIME_VOICES}

# Realtime-only voices are rejected by the TTS endpoint; preview them with the
# closest TTS voice instead. The dashboard labels tests as approximate.
_TTS_FALLBACK = {
    "marin": "sage",
    "cedar": "ash",
}

# Short sample spoken by the voice-test endpoint, rendered in the selected
# language so the admin hears the voice as callers would. Keys must cover
# settings_store.SUPPORTED_LANGUAGES.
SAMPLE_UTTERANCES = {
    "English": "Hi, my name is Emma, I'm a product specialist. I'm calling to help you look at Final Expense life insurance options. Is now a good time?",
    "Spanish": "Hola, me llamo Emma y soy especialista en productos. Le llamo para ayudarle a ver opciones de seguro de vida para gastos finales. ¿Es un buen momento?",
    "French": "Bonjour, je m'appelle Emma, je suis spécialiste produits. Je vous appelle pour vous présenter des options d'assurance vie frais funéraires. Est-ce un bon moment ?",
    "German": "Hallo, mein Name ist Emma, ich bin Produktspezialistin. Ich rufe an, um Ihnen Optionen für eine Sterbegeldversicherung vorzustellen. Passt es Ihnen gerade?",
    "Italian": "Salve, mi chiamo Emma e sono una specialista di prodotto. La chiamo per aiutarla a valutare opzioni di assicurazione vita per le spese funerarie. È un buon momento?",
    "Portuguese": "Olá, meu nome é Emma, sou especialista de produtos. Estou ligando para ajudar você a conhecer opções de seguro de vida para despesas finais. É um bom momento?",
    "Hindi": "नमस्ते, मेरा नाम एम्मा है, मैं एक प्रोडक्ट स्पेशलिस्ट हूँ। मैं आपको फ़ाइनल एक्सपेंस जीवन बीमा के विकल्प दिखाने के लिए कॉल कर रही हूँ। क्या यह सही समय है?",
    "Arabic": "مرحباً، اسمي إيما، أنا أخصائية منتجات. أتصل لمساعدتك في الاطلاع على خيارات تأمين الحياة لتغطية النفقات النهائية. هل هذا وقت مناسب؟",
    "Japanese": "こんにちは、商品担当のエマと申します。葬儀費用に備える終身保険のご案内でお電話しました。今お時間よろしいでしょうか？",
    "Korean": "안녕하세요, 상품 전문가 엠마입니다. 장례 비용을 대비하는 종신보험 옵션을 안내해 드리려고 연락드렸습니다. 지금 통화 괜찮으신가요?",
    "Russian": "Здравствуйте, меня зовут Эмма, я специалист по продуктам. Я звоню, чтобы рассказать вам о вариантах страхования жизни на покрытие ритуальных расходов. Вам удобно сейчас говорить?",
    "Bengali": "নমস্কার, আমার নাম এমা, আমি একজন প্রোডাক্ট স্পেশালিস্ট। আমি আপনাকে ফাইনাল এক্সপেন্স জীবন বীমার বিকল্পগুলো দেখাতে ফোন করেছি। এখন কি কথা বলা সুবিধাজনক?",
    "Chinese": "您好，我叫Emma，是产品专员。我打电话是想帮您了解身后事费用人寿保险的方案。现在方便吗？",
    "Indonesian": "Halo, nama saya Emma, saya spesialis produk. Saya menelepon untuk membantu Anda melihat pilihan asuransi jiwa biaya pemakaman. Apakah sekarang waktu yang tepat?",
    "Turkish": "Merhaba, adım Emma, ürün uzmanıyım. Cenaze masraflarını karşılayan hayat sigortası seçeneklerini size anlatmak için arıyorum. Şu an uygun bir zaman mı?",
    "Urdu": "السلام علیکم، میرا نام ایما ہے، میں پروڈکٹ اسپیشلسٹ ہوں۔ میں آپ کو فائنل ایکسپینس لائف انشورنس کے آپشنز دکھانے کے لیے کال کر رہی ہوں۔ کیا ابھی بات کرنا مناسب ہے؟",
}

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not configuration.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        _client = AsyncOpenAI(api_key=configuration.OPENAI_API_KEY)
    return _client


def is_known_voice(voice_id: str) -> bool:
    return voice_id in _VOICE_IDS


def list_voices() -> list[dict]:
    """The realtime voice catalog (static; shape mirrors the old Hume endpoint)."""
    return REALTIME_VOICES


async def synthesize_voice_sample(voice_id: str, language: str) -> bytes:
    """Synthesize a short MP3 sample of the given voice speaking the given language."""
    if not is_known_voice(voice_id):
        raise ValueError(f"Unknown voice id: {voice_id}")

    tts_voice = _TTS_FALLBACK.get(voice_id, voice_id)
    if tts_voice != voice_id:
        logger.info(
            f"Voice '{voice_id}' is realtime-only; previewing with TTS voice '{tts_voice}'."
        )
    text = SAMPLE_UTTERANCES.get(language) or SAMPLE_UTTERANCES["English"]

    response = await _get_client().audio.speech.create(
        model=TTS_MODEL,
        voice=tts_voice,
        input=text,
        response_format="mp3",
    )
    return response.content
