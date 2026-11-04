
"""Bounded, offline text extraction. Invoked in a disposable child process."""
import io
import json
import logging
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

MAX_TEXT = 40000

def limits():
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        return
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [("user", c.c_longlong), ("job", c.c_longlong), ("flags", w.DWORD),
                    ("minimum", c.c_size_t), ("maximum", c.c_size_t), ("active", w.DWORD),
                    ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
    class Extended(c.Structure):
        _fields_ = [("basic", Basic), ("io", c.c_ulonglong*6),
                    ("memory", c.c_size_t), ("job_memory", c.c_size_t),
                    ("peak", c.c_size_t), ("job_peak", c.c_size_t)]
    k = c.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    k.CreateJobObjectW.restype = w.HANDLE
    k.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    k.SetInformationJobObject.restype = w.BOOL
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.AssignProcessToJobObject.restype = w.BOOL
    k.GetCurrentProcess.restype = w.HANDLE
    job = k.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x100 | 0x2
    info.basic.user = 12*10000000
    info.memory = 512*1024*1024
    if not job or not k.SetInformationJobObject(job, 9, c.byref(info), c.sizeof(info)) or not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
        raise RuntimeError("Extractor resource limits unavailable")
    globals()["_job"] = job

def extract(raw, kind):
    if kind == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported. Upload an unlocked copy.")
        if not 1 <= len(reader.pages) <= 20:
            raise ValueError("Use a PDF of 1-20 pages.")
        parts = []
        for number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if len(text) < 5:
                raise ValueError("A PDF page has no readable text. Use a searchable PDF or attach its PNG/JPEG screenshot.")
            parts.append(f"[Page {number}]\n{text}")
            if sum(map(len, parts)) > MAX_TEXT:
                raise ValueError("Document text exceeds 40,000 characters. Attach a smaller section.")
        text = "\n\n".join(parts)
    else:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [x.filename for x in entries]
            if len(entries) > 256 or len(set(names)) != len(names):
                raise ValueError("Word archive has too many or duplicate entries.")
            if sum(x.file_size for x in entries) > 12*1024*1024 or any(x.flag_bits & 1 or x.file_size > 4*1024*1024 or x.file_size > max(1, x.compress_size)*200 for x in entries):
                raise ValueError("Word archive exceeds safe extraction limits.")
            if any(n.lower().endswith(".bin") for n in names):
                raise ValueError("Word files containing macros or embedded objects are not supported.")
            content_type = archive.read("[Content_Types].xml")
            if b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml" not in content_type:
                raise ValueError("Use a standard .docx Word document.")
            xml = archive.read("word/document.xml")
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise ValueError("Word XML declarations are not supported.")
            root = ET.fromstring(xml)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            text = "\n".join("".join(node.text or "" for node in p.iter(ns+"t")) for p in root.iter(ns+"p"))
    text = "".join(c for c in text if c in "\n\t" or ord(c) >= 32).strip()
    if len(text) < 5:
        raise ValueError("No readable body text found. Embedded pictures are not extracted; attach them as PNG/JPEG.")
    if len(text) > MAX_TEXT:
        raise ValueError("Document text exceeds 40,000 characters. Attach a smaller section.")
    return text

if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    try:
        limits()
        raw = sys.stdin.buffer.read(2*1024*1024+1)
        if not raw or len(raw) > 2*1024*1024:
            raise ValueError("Use a nonempty document up to 2 MiB.")
        result = {"text": extract(raw, sys.argv[1])}
    except (ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        result = {"error": str(exc)[:240]}
    except BaseException:
        result = {"error": "Document could not be read within safe limits. Upload a smaller, valid document."}
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=True).encode("ascii"))
