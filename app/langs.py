"""Language tables: translation targets + OCR script mapping."""

# deep-translator / Google codes -> display name
TARGET_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "uk": "Ukrainian",
    "pl": "Polish",
    "tr": "Turkish",
    "ar": "Arabic",
    "fa": "Persian",
    "he": "Hebrew",
    "ur": "Urdu",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "ja": "Japanese",
    "ko": "Korean",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "ms": "Malay",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "el": "Greek",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "cs": "Czech",
    "sk": "Slovak",
    "hu": "Hungarian",
    "ro": "Romanian",
    "bg": "Bulgarian",
    "sr": "Serbian",
    "hr": "Croatian",
    "sl": "Slovenian",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "et": "Estonian",
    "sw": "Swahili",
    "af": "Afrikaans",
    "fil": "Filipino",
    "ne": "Nepali",
    "si": "Sinhala",
    "my": "Burmese",
    "km": "Khmer",
    "lo": "Lao",
    "ka": "Georgian",
    "hy": "Armenian",
    "az": "Azerbaijani",
    "kk": "Kazakh",
    "uz": "Uzbek",
    "mn": "Mongolian",
    "is": "Icelandic",
    "ga": "Irish",
    "cy": "Welsh",
    "ca": "Catalan",
    "eu": "Basque",
    "gl": "Galician",
    "sq": "Albanian",
    "mk": "Macedonian",
    "bs": "Bosnian",
    "am": "Amharic",
    "yo": "Yoruba",
    "zu": "Zulu",
}

# Sorted (code, name) pairs for UI dropdowns, English first.
def target_choices():
    items = sorted(TARGET_LANGUAGES.items(), key=lambda kv: kv[1].lower())
    items.sort(key=lambda kv: kv[0] != "en")
    return items


def name_for(code):
    return TARGET_LANGUAGES.get(code, code)


def code_for_name(name):
    for code, label in TARGET_LANGUAGES.items():
        if label == name:
            return code
    return "en"


# Tesseract's OSD detector reports a *script*, and Tesseract ships a single
# unified model per script. Those beat stacking per-language packs: one model
# instead of four (faster) and the full accent repertoire (correct). German
# umlauts, Spanish tildes, Portuguese cedillas all survive; a language stack
# quietly drops whichever language it wasn't given.
#
# Each entry lists the script model first and per-language packs as fallbacks
# for anyone who only has those installed. The translator works out the actual
# language from the text afterwards, so OCR only has to get the script right.
SCRIPT_MODELS = {
    "Arabic", "Armenian", "Bengali", "Canadian_Aboriginal", "Cherokee",
    "Cyrillic", "Devanagari", "Ethiopic", "Fraktur", "Georgian", "Greek",
    "Gujarati", "Gurmukhi", "HanS", "HanS_vert", "HanT", "HanT_vert",
    "Hangul", "Hangul_vert", "Hebrew", "Japanese", "Japanese_vert",
    "Kannada", "Khmer", "Lao", "Latin", "Malayalam", "Myanmar", "Oriya",
    "Sinhala", "Syriac", "Tamil", "Telugu", "Thaana", "Thai", "Tibetan",
    "Vietnamese",
}

SCRIPT_TO_TESS = {
    "Latin": ["Latin", "eng", "deu", "fra", "spa"],
    "Fraktur": ["Fraktur", "Latin", "deu"],
    "Cyrillic": ["Cyrillic", "rus", "ukr", "bul"],
    "Greek": ["Greek", "ell"],
    "Han": ["HanS", "chi_sim"],
    "HanS": ["HanS", "chi_sim"],
    "HanT": ["HanT", "chi_tra"],
    "HanS_vert": ["HanS_vert", "HanS", "chi_sim"],
    "HanT_vert": ["HanT_vert", "HanT", "chi_tra"],
    "Japanese": ["Japanese", "jpn"],
    "Japanese_vert": ["Japanese_vert", "Japanese", "jpn"],
    "Korean": ["Hangul", "kor"],
    "Korean_vert": ["Hangul_vert", "Hangul", "kor"],
    "Hangul": ["Hangul", "kor"],
    "Arabic": ["Arabic", "ara", "fas", "urd"],
    "Hebrew": ["Hebrew", "heb"],
    "Devanagari": ["Devanagari", "hin", "mar", "san"],
    "Bengali": ["Bengali", "ben"],
    "Tamil": ["Tamil", "tam"],
    "Telugu": ["Telugu", "tel"],
    "Kannada": ["Kannada", "kan"],
    "Malayalam": ["Malayalam", "mal"],
    "Gujarati": ["Gujarati", "guj"],
    "Gurmukhi": ["Gurmukhi", "pan"],
    "Oriya": ["Oriya", "ori"],
    "Sinhala": ["Sinhala", "sin"],
    "Thai": ["Thai", "tha"],
    "Khmer": ["Khmer", "khm"],
    "Myanmar": ["Myanmar", "mya"],
    "Lao": ["Lao", "lao"],
    "Georgian": ["Georgian", "kat"],
    "Armenian": ["Armenian", "hye"],
    "Ethiopic": ["Ethiopic", "amh"],
    "Vietnamese": ["Vietnamese", "vie"],
    "Thaana": ["Thaana", "div"],
    "Tibetan": ["Tibetan", "bod"],
    "Syriac": ["Syriac", "syr"],
    "Cherokee": ["Cherokee", "chr"],
    "Canadian_Aboriginal": ["Canadian_Aboriginal", "iku"],
}

# Bundled by build.bat: the sizing model, the orientation detector, and the
# script models covering the scripts people actually run into. ~45 MB total.
DEFAULT_TESSDATA = [
    "osd", "eng", "Latin", "Cyrillic", "HanS", "Japanese", "Hangul",
    "Arabic", "Devanagari",
]

# Anything the app may fetch on demand from tessdata_fast.
KNOWN_TESSDATA = sorted(set(
    DEFAULT_TESSDATA
    + sorted(SCRIPT_MODELS)
    + [p for packs in SCRIPT_TO_TESS.values() for p in packs]
    + ["ukr", "bul", "ell", "chi_sim", "chi_tra", "jpn", "kor", "fas", "urd",
       "heb", "hin", "mar", "san", "ben", "tam", "tel", "kan", "mal", "guj",
       "pan", "ori", "sin", "tha", "khm", "mya", "lao", "kat", "hye", "amh",
       "vie", "div", "bod", "syr", "chr", "iku", "ara", "rus", "deu", "fra",
       "spa", "ita", "por", "nld", "pol", "tur", "swe", "dan", "nor", "fin",
       "ces", "slk", "hun", "ron", "hrv", "slv", "lit", "lav", "est", "ind",
       "msa", "srp", "sqi", "mkd", "aze", "kaz", "uzb", "cat", "eus", "glg",
       "isl", "gle", "cym", "afr", "swa", "nep", "equ"]
))


def tessdata_path(pack):
    """Repo-relative path in tessdata_fast: script models live in script/."""
    return ("script/%s" % pack) if pack in SCRIPT_MODELS else pack
