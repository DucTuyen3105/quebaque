import re
import unicodedata


def normalize(text):
    text = unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in text if unicodedata.category(c) != 'Mn')).strip()


STOPWORDS = set('la va cua cac nhung mot trong cho voi duoc ve khi thi co de nhu tu nay nao gi tai sao the hay ban toi theo biet khong o do den tren khac nhau cach lam hom bao nhieu ai dau nam ngay'.split())


def tokens(text):
    return [word for word in normalize(text).split() if word not in STOPWORDS and len(word) > 1]


def detect(text, entities):
    text = ' ' + normalize(text) + ' '
    return [e['id'] for e in entities if any(' ' + normalize(alias) + ' ' in text for alias in e['aliases'])]


def prepare_query(question):
    value = normalize(question)
    for before, after in [('mung', 'mong'), ('an tet som', 'an tet truoc'), ('rut lui', 'lui quan'), ('dai thang', 'chien thang'), ('giac thanh', 'quan thanh')]:
        value = re.sub(r'\b' + re.escape(before) + r'\b', after, value)
    if re.search(r'\bbao nhieu (?:quan|linh)\b', value):
        value += ' quan so'
    return value
