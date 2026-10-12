#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Letra em Vídeo
--------------
Áudio + letra  ->  sincroniza (.lrc)  ->  .srt  ->  .ass animado  ->  vídeo .mp4

Só usa a biblioteca padrão do Python (3.8+). O ffmpeg vem da pasta "ffmpeg".

Pastas (criadas automaticamente, ao lado deste arquivo):
    ffmpeg/   binários do ffmpeg (ffmpeg.exe ou ffmpeg)
    vídeos/   resultado final: <nome do áudio>.mp4  (+ .lrc e .srt)
    fontes/   (opcional) arquivos .ttf/.otf para usar como fonte
    temp/     arquivos temporários (limpa ao iniciar)
"""

import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
FFMPEG_DIR = APP_DIR / "ffmpeg"
OUT_DIR = APP_DIR / "vídeos"
FONTS_DIR = APP_DIR / "fontes"
TEMP_DIR = APP_DIR / "temp"
INDEX = APP_DIR / "index.html"
PORT = 8765

JOBS = {}


# --------------------------------------------------------------------------
# ffmpeg
# --------------------------------------------------------------------------
def find_ffmpeg():
    names = ["ffmpeg.exe", "ffmpeg"]
    for base in (FFMPEG_DIR, FFMPEG_DIR / "bin"):
        for n in names:
            p = base / n
            if p.is_file():
                return str(p)
    if FFMPEG_DIR.is_dir():
        for n in names:
            for p in FFMPEG_DIR.rglob(n):
                if p.is_file():
                    return str(p)
    return shutil.which("ffmpeg")


def ffmpeg_version(path):
    try:
        out = subprocess.run([path, "-version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=10).stdout
        return out.splitlines()[0] if out else ""
    except Exception:
        return ""


# --------------------------------------------------------------------------
# Fontes (.ttf/.otf da pasta "fontes")
# --------------------------------------------------------------------------
def read_font_names(path):
    """Devolve (família, subfamília) lendo a tabela 'name' do arquivo."""
    data = path.read_bytes()
    off0 = 0
    if data[:4] == b"ttcf":
        off0 = struct.unpack(">I", data[12:16])[0]
    num = struct.unpack(">H", data[off0 + 4:off0 + 6])[0]
    for i in range(num):
        rec = off0 + 12 + i * 16
        if data[rec:rec + 4] != b"name":
            continue
        off, length = struct.unpack(">II", data[rec + 8:rec + 16])
        tbl = data[off:off + length]
        count, str_off = struct.unpack(">HH", tbl[2:6])
        found = {}
        for j in range(count):
            p = 6 + j * 12
            pid, eid, lid, nid, ln, so = struct.unpack(">HHHHHH", tbl[p:p + 12])
            if nid not in (1, 2):
                continue
            raw = tbl[str_off + so:str_off + so + ln]
            s = raw.decode("utf-16-be", "ignore") if pid in (0, 3) else raw.decode("latin-1", "ignore")
            score = 2 if (pid == 3 and lid == 0x409) else 1
            if nid not in found or score > found[nid][0]:
                found[nid] = (score, s)
        fam = found.get(1, (0, ""))[1]
        sub = found.get(2, (0, "Regular"))[1]
        return fam, sub
    return "", "Regular"


def list_fonts():
    fonts = []
    if FONTS_DIR.is_dir():
        for p in sorted(FONTS_DIR.iterdir()):
            if p.suffix.lower() not in (".ttf", ".otf"):
                continue
            try:
                fam, sub = read_font_names(p)
            except Exception:
                fam, sub = "", "Regular"
            fonts.append({"file": p.name, "family": fam or p.stem, "style": sub or "Regular"})
    return fonts


# --------------------------------------------------------------------------
# SRT -> ASS (com animações de entrada e saída)
# --------------------------------------------------------------------------
def parse_srt(text):
    cues = []
    pat = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")

    def sec(h, m, s, ms):
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000.0

    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        lines = block.splitlines()
        for k, line in enumerate(lines):
            m = pat.search(line)
            if m:
                g = m.groups()
                body = "\n".join(lines[k + 1:]).strip()
                if body:
                    cues.append((sec(*g[0:4]), sec(*g[4:8]), body))
                break
    return cues


def ass_time(t):
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, c = divmod(cs, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, c)


def hex_to_ass(hexcolor):
    h = (hexcolor or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    return "&H00%s%s%s" % (h[4:6].upper(), h[2:4].upper(), h[0:2].upper())


def build_ass(cues, st, W, H):
    k = min(W, H) / 1080.0                      # tamanhos "de referência" Full HD
    font = str(st.get("font", "Arial")).replace(",", " ").strip() or "Arial"
    fsize = max(8, int(round(float(st.get("size", 64)) * k)))
    outline = round(float(st.get("outline", 3)) * k, 2)
    bold = -1 if st.get("bold", True) else 0
    mh = int(round(W * 0.06))
    mv = int(round(H * float(st.get("margin_v", 10)) / 100.0))
    pos = st.get("pos", "bottom")
    x = W // 2
    if pos == "top":
        an, y = 8, mv
    elif pos == "center":
        an, y = 5, H // 2
    else:
        an, y = 2, H - mv
    off = int(round(H * 0.07))
    anim_in = st.get("anim_in", "fade")
    anim_out = st.get("anim_out", "fade")
    in_ms = int(st.get("in_ms", 400))
    out_ms = int(st.get("out_ms", 400))

    AN = "\\an%d" % an
    POS = "\\pos(%d,%d)" % (x, y)

    def move(y1, y2, d):
        return "\\move(%d,%d,%d,%d,0,%d)" % (x, y1, x, y2, d)

    def entry(d):
        if anim_in == "fade":
            return AN + POS + "\\fad(%d,0)" % d
        if anim_in == "up":
            return AN + move(y + off, y, d) + "\\fad(%d,0)" % d
        if anim_in == "down":
            return AN + move(y - off, y, d) + "\\fad(%d,0)" % d
        if anim_in == "zoom":
            return AN + POS + "\\fscx60\\fscy60\\t(0,%d,0.5,\\fscx100\\fscy100)\\fad(%d,0)" % (d, d)
        if anim_in == "pop":
            a = int(d * 0.65)
            return AN + POS + "\\fscx0\\fscy0\\t(0,%d,\\fscx112\\fscy112)\\t(%d,%d,\\fscx100\\fscy100)" % (a, a, d)
        return AN + POS

    def exit_(d):
        if anim_out == "fade":
            return AN + POS + "\\fad(0,%d)" % d
        if anim_out == "up":
            return AN + move(y, y - off, d) + "\\fad(0,%d)" % d
        if anim_out == "down":
            return AN + move(y, y + off, d) + "\\fad(0,%d)" % d
        if anim_out == "zoom":
            return AN + POS + "\\t(0,%d,\\fscx60\\fscy60)\\fad(0,%d)" % (d, d)
        return AN + POS

    head = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: %d\nPlayResY: %d\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\nYCbCr Matrix: None\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,%s,%d,%s,%s,%s,&H64000000,%d,0,0,0,100,100,0,0,1,%s,0,%d,%d,%d,%d,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    ) % (W, H, font, fsize, hex_to_ass(st.get("color")), hex_to_ass(st.get("color")),
         hex_to_ass(st.get("outline_color", "#000000")), bold, outline, an, mh, mh, mv)

    events = []
    for (start, end, text) in cues:
        text = text.replace("{", "(").replace("}", ")").replace("\r", "")
        text = "\\N".join(s.strip() for s in text.split("\n") if s.strip())
        dur_ms = int(round((end - start) * 1000))
        if dur_ms < 50:
            continue
        in_d = min(in_ms, int(dur_ms * 0.4)) if anim_in != "none" else 0
        out_d = min(out_ms, int(dur_ms * 0.4)) if anim_out != "none" else 0
        t_in_end = start + in_d / 1000.0
        t_out_start = end - out_d / 1000.0
        segs = []
        if in_d > 0:
            segs.append((start, t_in_end, entry(in_d)))
        if t_out_start - t_in_end > 0.005:
            segs.append((t_in_end, t_out_start, AN + POS))
        if out_d > 0:
            segs.append((t_out_start, end, exit_(out_d)))
        if not segs:
            segs.append((start, end, AN + POS))
        for (a, b, tg) in segs:
            events.append("Dialogue: 0,%s,%s,Default,,0,0,0,,{%s}%s" % (ass_time(a), ass_time(b), tg, text))
    return head + "\n".join(events) + "\n"


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------
def safe_name(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")


def run_job(jid, req):
    job = JOBS[jid]
    ass_path = None
    try:
        ff = find_ffmpeg()
        if not ff:
            raise RuntimeError("ffmpeg não encontrado. Coloque os binários na pasta 'ffmpeg'.")
        audio = TEMP_DIR / Path(req["audio"]).name
        if not audio.is_file():
            raise RuntimeError("O áudio não está mais no servidor. Selecione o arquivo novamente.")
        W = int(req["width"]); H = int(req["height"])
        W -= W % 2; H -= H % 2
        fps = int(req.get("fps", 30))
        stem = safe_name(Path(req.get("audio_name") or "video").stem) or "video"

        OUT_DIR.mkdir(exist_ok=True)
        out = OUT_DIR / (stem + ".mp4")
        (OUT_DIR / (stem + ".lrc")).write_text(req.get("lrc", ""), encoding="utf-8")
        srt = req.get("srt", "")
        (OUT_DIR / (stem + ".srt")).write_text(srt, encoding="utf-8")

        cues = parse_srt(srt)
        shift = float(req.get("sub_offset_ms") or 0) / 1000.0
        if shift:
            cues = [(max(0.0, a + shift), max(0.05, b + shift), t) for (a, b, t) in cues]
        if not cues:
            raise RuntimeError("Nenhuma legenda para gravar. Sincronize ao menos uma linha.")
        total = float(req.get("duration") or 0) or max(c[1] for c in cues)

        ass_name = "_legenda_%s.ass" % jid
        ass_path = APP_DIR / ass_name
        ass_path.write_text(build_ass(cues, req.get("style", {}), W, H), encoding="utf-8")

        bg = req.get("bg", {})
        col = "0x" + (bg.get("color") or "#000000").lstrip("#")
        if bg.get("type") == "image" and bg.get("image"):
            img = TEMP_DIR / Path(bg["image"]).name
            if not img.is_file():
                raise RuntimeError("A imagem de fundo não está mais no servidor. Selecione-a novamente.")
            inp = ["-loop", "1", "-framerate", str(fps), "-i", str(img)]
            if bg.get("fit") == "contain":
                base = ("scale=%d:%d:force_original_aspect_ratio=decrease,"
                        "pad=%d:%d:(ow-iw)/2:(oh-ih)/2:color=%s,setsar=1") % (W, H, W, H, col)
            else:
                base = ("scale=%d:%d:force_original_aspect_ratio=increase,"
                        "crop=%d:%d,setsar=1") % (W, H, W, H)
        else:
            inp = ["-f", "lavfi", "-i", "color=c=%s:s=%dx%d:r=%d" % (col, W, H, fps)]
            base = "setsar=1"
        vf = "%s,ass=%s:fontsdir=fontes,format=yuv420p" % (base, ass_name)

        cmd = [ff, "-y", "-hide_banner", "-loglevel", "warning", "-progress", "pipe:1", "-nostats"]
        cmd += inp + ["-i", str(audio)]
        cmd += ["-vf", vf, "-map", "0:v", "-map", "1:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(fps),
                "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)]

        flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
        proc = subprocess.Popen(cmd, cwd=str(APP_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1,
                                creationflags=flags)
        job["proc"] = proc
        for line in proc.stdout:
            line = line.strip()
            m = re.match(r"out_time_(?:us|ms)=(\d+)", line)
            if m:
                job["progress"] = min(0.99, (int(m.group(1)) / 1e6) / total) if total else 0
            elif line and not re.match(r"^[a-z_]+=", line):
                job["log"].append(line)
                job["log"] = job["log"][-30:]
        proc.wait()

        if job.get("cancel"):
            job["status"] = "cancelled"
            if out.exists():
                out.unlink()
        elif proc.returncode == 0 and out.is_file():
            job.update(status="done", progress=1.0, output=str(out), folder=str(OUT_DIR))
        else:
            raise RuntimeError("O ffmpeg terminou com erro:\n" + "\n".join(job["log"][-12:]))
    except Exception as e:
        job.update(status="error", message=str(e))
    finally:
        if ass_path and ass_path.exists():
            try:
                ass_path.unlink()
            except OSError:
                pass


def convert_to_wav(src):
    """Converte o áudio enviado para WAV PCM. O navegador toca ESTE arquivo e o ffmpeg
    usa ESTE arquivo, então o tempo marcado na sincronização é idêntico ao do vídeo
    (MP3 VBR/atraso de encoder fazem navegador e ffmpeg divergirem)."""
    ff = find_ffmpeg()
    if not ff:
        return src
    dst = TEMP_DIR / (uuid.uuid4().hex[:12] + ".wav")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    r = subprocess.run([ff, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "2", "-ar", "48000",
                        "-c:a", "pcm_s16le", str(dst)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=flags)
    if r.returncode != 0 or not dst.is_file():
        raise RuntimeError(r.stderr.strip()[-400:] or "ffmpeg não conseguiu ler o áudio")
    try:
        src.unlink()
    except OSError:
        pass
    return dst


def open_folder(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "LetraEmVideo/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        p = u.path
        if p in ("/", "/index.html"):
            if not INDEX.is_file():
                return self._send(500, "index.html não encontrado ao lado do app.py", "text/plain; charset=utf-8")
            return self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        if p == "/api/info":
            ff = find_ffmpeg()
            return self._send(200, {"ffmpeg": ff, "version": ffmpeg_version(ff) if ff else "",
                                    "out_dir": str(OUT_DIR)})
        if p == "/api/fonts":
            return self._send(200, list_fonts())
        if p.startswith("/fonts/"):
            f = FONTS_DIR / Path(urllib.parse.unquote(p[7:])).name
            if f.is_file():
                ct = "font/otf" if f.suffix.lower() == ".otf" else "font/ttf"
                return self._send(200, f.read_bytes(), ct)
            return self._send(404, {"error": "fonte não encontrada"})
        if p.startswith("/media/"):
            f = TEMP_DIR / Path(urllib.parse.unquote(p[7:])).name
            if not f.is_file():
                return self._send(404, {"error": "arquivo não encontrado"})
            size = f.stat().st_size
            start, end, code = 0, size - 1, 200
            m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                else:
                    start = max(0, size - int(m.group(2)))
                code = 206
            ct = "audio/wav" if f.suffix.lower() == ".wav" else "application/octet-stream"
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if code == 206:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.end_headers()
            try:
                with open(f, "rb") as fh:
                    fh.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = fh.read(min(1 << 20, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        if p == "/api/job":
            job = JOBS.get((q.get("id") or [""])[0])
            if not job:
                return self._send(404, {"error": "job não encontrado"})
            return self._send(200, {k: v for k, v in job.items() if k != "proc"})
        return self._send(404, {"error": "não encontrado"})

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        p = u.path
        length = int(self.headers.get("Content-Length") or 0)

        if p == "/api/upload":
            name = (q.get("name") or ["arquivo"])[0]
            ext = re.sub(r"[^a-z0-9]", "", Path(name).suffix.lower())[:8]
            fname = uuid.uuid4().hex[:12] + ("." + ext if ext else "")
            TEMP_DIR.mkdir(exist_ok=True)
            with open(TEMP_DIR / fname, "wb") as f:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            if (q.get("kind") or [""])[0] == "audio":
                try:
                    fname = convert_to_wav(TEMP_DIR / fname).name
                except Exception as e:
                    return self._send(500, {"error": "Não consegui ler esse áudio: %s" % e})
            return self._send(200, {"file": fname})

        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            return self._send(400, {"error": "JSON inválido"})

        if p == "/api/render":
            jid = uuid.uuid4().hex[:10]
            JOBS[jid] = {"id": jid, "status": "running", "progress": 0.0, "message": "",
                         "output": None, "folder": None, "log": [], "proc": None}
            threading.Thread(target=run_job, args=(jid, data), daemon=True).start()
            return self._send(200, {"id": jid})

        if p == "/api/cancel":
            job = JOBS.get(data.get("id", ""))
            if job and job.get("proc") and job["status"] == "running":
                job["cancel"] = True
                try:
                    job["proc"].terminate()
                except Exception:
                    pass
            return self._send(200, {"ok": True})

        if p == "/api/open-folder":
            OUT_DIR.mkdir(exist_ok=True)
            try:
                open_folder(str(OUT_DIR))
                return self._send(200, {"ok": True})
            except Exception as e:
                return self._send(500, {"error": str(e)})

        return self._send(404, {"error": "não encontrado"})


def main():
    for d in (FFMPEG_DIR, OUT_DIR, FONTS_DIR, TEMP_DIR):
        d.mkdir(exist_ok=True)
    for f in TEMP_DIR.iterdir():
        try:
            f.unlink()
        except OSError:
            pass

    port = PORT
    while True:
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            port += 1
            if port > PORT + 20:
                raise
    url = "http://127.0.0.1:%d/" % port

    ff = find_ffmpeg()
    print("=" * 58)
    print(" Letra em Vídeo rodando em", url)
    print(" ffmpeg:", ff or "NÃO ENCONTRADO (coloque os binários na pasta 'ffmpeg')")
    print(" Vídeos salvos em:", OUT_DIR)
    print(" Feche esta janela para encerrar.")
    print("=" * 58)
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
