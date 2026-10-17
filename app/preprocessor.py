"""
Предобработка адресных строк ПЕРЕД парсером.
Исправляет опечатки, слитное написание, латиницу, невидимые символы.
"""

import re
import unicodedata


TYPO_CORRECTIONS = {
    r'\bподьезд\b': 'подъезд',
    r'\bподьезда\b': 'подъезда',
    r'\bподьезду\b': 'подъезду',
    r'\bподьезде\b': 'подъезде',
    r'\bподьездом\b': 'подъездом',
    r'\bквртира\b': 'квартира',
    r'\bкваритра\b': 'квартира',
    r'\bквратира\b': 'квартира',
    r'\bмикрорайн\b': 'микрорайон',
    r'\bмикрорайнн\b': 'микрорайон',
    r'\bмикроайон\b': 'микрорайон',
    r'\bпроспкет\b': 'проспект',
    r'\bпрсопект\b': 'проспект',
    r'\bпереулокк\b': 'переулок',
    r'\bбульварр\b': 'бульвар',
    # «дом» и «этаж» тоже пишут с опечатками — иначе слово прилипает к улице
    r'\bдомм+\b': 'дом',
    r'\bдоом\b': 'дом',
    r'\bдмм\b': 'дом',
    r'\bеттаж\b': 'этаж',
    r'\bетаж\b': 'этаж',
    r'\bэтажж\b': 'этаж',
    r'\bподъезж\b': 'подъезд',
    r'\bквартр\b': 'квартира',
    r'\bквapтира\b': 'квартира',
}

LATIN_SYNONYMS = {
    r'\bflat\b': 'кв',
    r'\bapt\b': 'кв',
    r'\bapartment\b': 'кв',
    r'\bappartment\b': 'кв',
    r'\bkv\b': 'кв',
    r'\bkvartira\b': 'квартира',
    r'\bdom\b': 'дом',
    r'\bhouse\b': 'дом',
    r'\bbuilding\b': 'дом',
    r'\bbldg\b': 'дом',
    r'\bfloor\b': 'этаж',
    r'\bfl\b': 'этаж',
    r'\bentrance\b': 'подъезд',
    r'\bent\b': 'подъезд',
    r'\bporch\b': 'подъезд',
    r'\bstr\b': 'ул',
    r'\bstreet\b': 'ул',
    r'\bave\b': 'пр',
    r'\bavenue\b': 'пр',
    r'\bdistrict\b': 'район',
    r'\bcity\b': 'город',
    r'\bgorod\b': 'город',
}


def clean_invisible_chars(text: str) -> str:
    cleaned = []
    for ch in text:
        if ch == '\xa0':
            cleaned.append(' ')
        elif ch in ('\u200b', '\u200c', '\u200d', '\ufeff', '\u2060'):
            continue
        elif unicodedata.category(ch).startswith('C') and ch not in ('\n', '\t'):
            continue
        else:
            cleaned.append(ch)
    return ''.join(cleaned)


def fix_spacing_around_punctuation(text: str) -> str:
    text = re.sub(r'(\w)\s+\.', r'\1.', text)
    text = re.sub(r'\.([А-Яа-яЁёA-Za-z])', r'. \1', text)
    # «st.12», «д.5» — точка перед цифрой тоже разделяет
    text = re.sub(r'\.(\d)', r'. \1', text)
    # «Алматыул.Абая» — город слипся с сокращением типа улицы
    text = re.sub(r'(?<=[а-яё])(ул|көш|кош|даңғ|данғ|пр|пер|пл)\.', r', \1. ', text)
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r',([^\s])', r', \1', text)
    return text


def split_glued_tokens(text: str) -> str:
    text = re.sub(r'(\d)([а-яёА-ЯЁ]{2,})', r'\1 \2', text)
    text = re.sub(r'([а-яёА-ЯЁ])(\d)', r'\1 \2', text)
    # латиница: «Abai12» -> «Abai 12» (в отличие от «12а», где буква — литера дома)
    text = re.sub(r'([A-Za-z])(\d)', r'\1 \2', text)
    return text


def fix_typos(text: str) -> str:
    for pattern, replacement in TYPO_CORRECTIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def normalize_latin(text: str) -> str:
    for pattern, replacement in LATIN_SYNONYMS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def preprocess_address(raw: str) -> str:
    text = raw
    text = clean_invisible_chars(text)
    text = normalize_latin(text)
    text = fix_spacing_around_punctuation(text)
    text = split_glued_tokens(text)
    text = fix_typos(text)
    text = normalize_whitespace(text)
    return text
