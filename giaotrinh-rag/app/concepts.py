"""A small, auditable domain vocabulary, not LLM-invented facts."""
import re
import unicodedata


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


VOCABULARY = {
    'software-process': ('Tiến trình phần mềm', ['tiến trình phần mềm', 'software process']),
    'lifecycle': ('Vòng đời phần mềm', ['vòng đời phần mềm', 'software life cycle']),
    'requirements': ('Xác định yêu cầu', ['xác định yêu cầu', 'pha yêu cầu', 'requirements']),
    'specification': ('Đặc tả', ['đặc tả', 'specification']),
    'analysis': ('Phân tích hướng đối tượng', ['phân tích hướng đối tượng', 'object oriented analysis']),
    'design': ('Thiết kế phần mềm', ['pha thiết kế', 'thiết kế phần mềm', 'software design']),
    'implementation': ('Cài đặt', ['pha cài đặt', 'luồng công việc cài đặt', 'implementation']),
    'integration': ('Tích hợp', ['tích hợp', 'integration']),
    'maintenance': ('Bảo trì', ['bảo trì', 'maintenance']),
    'testing': ('Kiểm thử', ['kiểm thử', 'kiểm tra phần mềm', 'testing']),
    'sqa': ('Đảm bảo chất lượng (SQA)', ['sqa', 'đảm bảo chất lượng', 'quality assurance']),
    'verification': ('Xác minh', ['xác minh', 'verification']),
    'validation': ('Thẩm định', ['thẩm định', 'validation']),
    'walkthrough': ('Rà soát lướt qua', ['rà soát lướt qua', 'walkthrough']),
    'inspection': ('Thanh tra mã', ['thanh tra', 'inspection']),
    'static-testing': ('Kiểm thử không thực thi', ['kiểm thử không có sự thực thi', 'kiểm thử tĩnh']),
    'dynamic-testing': ('Kiểm thử có thực thi', ['kiểm thử có dựa trên sự thực thi', 'kiểm thử động']),
    'blackbox': ('Kiểm thử hộp đen', ['hộp đen', 'blackbox', 'black box', 'black-box']),
    'whitebox': ('Kiểm thử hộp trắng', ['hộp trắng', 'whitebox', 'white box', 'white-box']),
    'unit-testing': ('Kiểm thử đơn vị', ['kiểm thử đơn vị', 'unit test', 'junit']),
    'integration-testing': ('Kiểm thử tích hợp', ['kiểm thử tích hợp', 'integration testing']),
    'acceptance-testing': ('Kiểm thử chấp nhận', ['kiểm thử chấp nhận', 'acceptance test']),
    'regression-testing': ('Kiểm thử hồi quy', ['kiểm thử hồi quy', 'regression']),
    'test-case': ('Ca kiểm thử', ['ca kiểm thử', 'test case', 'testcase', 'trường hợp kiểm thử']),
    'waterfall': ('Mô hình thác nước', ['thác nước', 'waterfall']),
    'build-fix': ('Mô hình xây sửa', ['xây sửa', 'xây - sửa', 'build and fix']),
    'evolution': ('Mô hình tiến hóa', ['mô hình tiến hóa', 'mô hình tiến hoá']),
    'prototype': ('Bản mẫu nhanh', ['bản mẫu', 'prototype', 'prototyping']),
    'iterative': ('Lặp và tăng dần', ['lặp và tăng', 'iterative', 'incremental']),
    'up': ('Quy trình hợp nhất (UP)', ['mô hình up', 'quy trình hợp nhất', 'unified process', 'rup']),
    'spiral': ('Mô hình xoắn ốc', ['xoắn ốc', 'spiral']),
    'open-source': ('Mã nguồn mở', ['mã nguồn mở', 'open source']),
    'use-case': ('Use case', ['use case', 'use-case', 'ca sử dụng']),
    'actor': ('Tác nhân', ['tác nhân', 'actor']),
    'scenario': ('Kịch bản', ['kịch bản', 'scenario']),
    'business-model': ('Mô hình nghiệp vụ', ['mô hình nghiệp vụ', 'business model']),
    'interview': ('Phỏng vấn', ['phỏng vấn', 'interview']),
    'uml': ('UML', ['uml', 'unified modeling language']),
    'entity-class': ('Lớp thực thể', ['lớp thực thể', 'entity class']),
    'class-types': ('Các kiểu lớp', ['loại lớp', 'kiểu lớp', 'ba kiểu lớp']),
    'boundary-class': ('Lớp biên', ['lớp biên', 'boundary class']),
    'control-class': ('Lớp điều khiển', ['lớp điều khiển', 'control class']),
    'class-diagram': ('Biểu đồ lớp', ['biểu đồ lớp', 'sơ đồ lớp', 'class diagram']),
    'state-diagram': ('Biểu đồ trạng thái', ['biểu đồ trạng thái', 'sơ đồ trạng thái', 'state diagram']),
    'sequence-diagram': ('Biểu đồ tuần tự', ['biểu đồ tuần tự', 'biểu đồ trình tự', 'sequence diagram']),
    'crc': ('Thẻ CRC', ['crc', 'class responsibility collaboration']),
    'architecture': ('Thiết kế kiến trúc', ['thiết kế kiến trúc', 'architectural design']),
    'detailed-design': ('Thiết kế chi tiết', ['thiết kế chi tiết', 'detailed design']),
    'data-flow': ('Dòng dữ liệu', ['dòng dữ liệu', 'data flow', 'dfd']),
    'cohesion': ('Tính kết dính', ['kết dính', 'cohesion']),
    'coupling': ('Tính kết nối', ['kết nối', 'coupling']),
    'planning': ('Lập kế hoạch', ['lập kế hoạch', 'planning', 'spmp']),
    'estimation': ('Ước lượng', ['ước lượng', 'estimation']),
    'cocomo': ('COCOMO', ['cocomo']),
    'function-point': ('Điểm chức năng', ['điểm chức năng', 'function point']),
    'risk': ('Rủi ro', ['rủi ro', 'risk']),
    'case': ('Công cụ CASE', ['công cụ case', 'computer aided software']),
    'reverse-engineering': ('Kỹ nghệ ngược', ['kỹ nghệ ngược', 'reverse engineering']),
    'inheritance': ('Kế thừa', ['kế thừa', 'inheritance']),
    'polymorphism': ('Đa hình', ['đa hình', 'polymorphism']),
    'encapsulation': ('Đóng gói', ['đóng gói', 'encapsulation']),
    'database': ('Cơ sở dữ liệu', ['cơ sở dữ liệu', 'database']),
}

PATTERNS = {
    key: re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(normalize(a)) for a in aliases) + r')(?!\w)')
    for key, (_, aliases) in VOCABULARY.items()
}


def detect(text: str) -> list[str]:
    value = normalize(text)
    return [key for key, pattern in PATTERNS.items() if pattern.search(value)]


def prepare_query(text: str) -> tuple[str, list[str]]:
    """Link informal query wording without changing the indexed document text."""
    value = normalize(text)
    value = re.sub(r'\b(?:trich xuat|rut trich)\b', 'trich rut', value)
    concepts = set(detect(text))
    aliases = {
        'analysis': r'\b(?:pha|giai doan|luong cong viec) phan tich\b',
        'entity-class': r'\b(?:trich rut|rut|xac dinh|nhan dien|tim)(?: duoc| ra| cac| nhung){0,3} lop\b',
    }
    for concept, pattern in aliases.items():
        if re.search(pattern, value):
            concepts.add(concept)
    return value, [key for key in VOCABULARY if key in concepts]


# Keep "phan": accent folding otherwise drops both "phần" and "phân",
# destroying the meaning of phrases such as "phân tích".
STOPWORDS = set('la va cua cac nhung mot trong cho voi duoc ve khi thi co de nhu tu nay nao gi tai sao the nao hay ban toi theo giao trinh mem chuong muc hay trinh bay cho biet khong o do den tren khac nhau cach lam hom bao nhieu'.split())


def tokens(text: str) -> list[str]:
    return [t for t in normalize(text).split() if t not in STOPWORDS and len(t) > 1]
