import io
import stat
import zipfile
from pathlib import PurePosixPath

MAX_FILE = 10 * 1024 * 1024
MAX_TOTAL = 30 * 1024 * 1024
ALLOWED = {'.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.html', '.css', '.json', '.java', '.md', '.pdf', '.docx'}

def valid_name(name):
    if not name or '\\' in name or ':' in name or '\x00' in name:
        raise ValueError('Недопустимое имя файла')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or any(part.startswith('.') for part in path.parts):
        raise ValueError('Небезопасный путь файла')
    if len(name) > 200 or any(ord(c) < 32 for c in name):
        raise ValueError('Недопустимое имя файла')
    return path

def validate(name, content):
    path = valid_name(name)
    suffix = path.suffix.lower()
    if suffix not in ALLOWED or len(content) > MAX_FILE or not content:
        raise ValueError('Допустимы Python, JS/TS, HTML/CSS/JSON, Java и документы MD/PDF/DOCX до 10 МБ')
    if suffix == '.pdf':
        if not content.startswith(b'%PDF-'):
            raise ValueError('Некорректный PDF')
    elif suffix == '.docx':
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if 'word/document.xml' not in z.namelist() or sum(i.file_size for i in z.infolist()) > MAX_TOTAL:
                raise ValueError('Некорректный или слишком большой DOCX')
    else:
        text = content.decode('utf-8-sig')
        if '\x00' in text:
            raise ValueError('Ожидается текст UTF-8')
    return suffix

def unpack(name, content):
    if not name.lower().endswith('.zip'):
        validate(name, content)
        return [(name, content)]
    result = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        entries = z.infolist()
        if len(entries) > 100 or sum(i.file_size for i in entries) > MAX_TOTAL:
            raise ValueError('Архив превышает лимит 100 файлов / 30 МБ')
        for item in entries:
            valid_name(item.filename.rstrip('/'))
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('Символические ссылки запрещены')
            if item.is_dir():
                continue
            if item.file_size > MAX_FILE:
                raise ValueError('Слишком большой файл в архиве')
            payload = z.read(item)
            validate(item.filename, payload)
            result.append((item.filename, payload))
    if not result:
        raise ValueError('Пустой архив')
    return result

def extract_text(name, content):
    suffix = PurePosixPath(name).suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        return '\n'.join((page.extract_text() or '') for page in PdfReader(io.BytesIO(content)).pages)[:100000]
    if suffix == '.docx':
        from docx import Document
        return '\n'.join(p.text for p in Document(io.BytesIO(content)).paragraphs)[:100000]
    return content.decode('utf-8-sig')[:100000]
