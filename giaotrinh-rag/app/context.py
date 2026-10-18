"""Select complete, topic-aligned evidence for the small local language model."""
import re
import math
from collections import Counter

from .concepts import prepare_query, tokens


def section_passages(text):
    headings = []
    for match in re.finditer(r'\b\d+\.\d+(?:\.\d+)*\.?\s+', text):
        words = []
        for word in text[match.end():].split():
            if not any(c.isalpha() for c in word) or not word.isupper():
                break
            words.append(word)
        if len(words) >= 2:
            headings.append((match.start(), ' '.join(words)))
    for index, (start, title) in enumerate(headings):
        end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        yield title, text[start:end].strip()


def select_context(question, sources, limit):
    if not sources:
        return []
    canonical, _ = prepare_query(question)
    # For questions about an ordered procedure, a similarly named neighboring
    # method can be misleading. Prefer the section whose title matches the
    # question, keeping its heading and steps together.
    if re.search(r'\b(?:dau tien|buoc dau|thu tu|cac buoc|nhung buoc)\b', canonical):
        query_tokens = tokens(canonical)
        query_pairs = set(zip(query_tokens, query_tokens[1:]))
        passages = []
        for source in sources:
            for title, passage in section_passages(source['text']):
                title_tokens = tokens(title)
                pairs = set(zip(title_tokens, title_tokens[1:]))
                passages.append((source, passage, pairs))
        frequencies = Counter(pair for _, _, pairs in passages for pair in pairs)
        focused = []
        for source, passage, pairs in passages:
            overlap = query_pairs.intersection(pairs)
            if len(overlap) >= 2:
                # Specific procedure names should outweigh generic wording
                # such as "pha phân tích" repeated across neighboring topics.
                weight = sum(math.log(1 + len(passages) / (1 + frequencies[pair])) for pair in overlap)
                focused.append((weight, source['score'], {**source, 'context_text': passage}))
        if focused:
            maximum = max(item[0] for item in focused)
            focused.sort(key=lambda item: (-item[0], -item[1]))
            selected, seen = [], set()
            for overlap, _, source in focused:
                if abs(overlap - maximum) < 1e-8 and source['id'] not in seen:
                    selected.append(source)
                    seen.add(source['id'])
                if len(selected) >= limit:
                    break
            return selected
    return [s for s in sources if s['score'] >= sources[0]['score'] * 0.70][:limit]
