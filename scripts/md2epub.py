import re, html as H, zipfile, os

def build_epub(md_path, out_path):
    md = open(md_path, encoding="utf-8").read()
    title = channel = date = ""
    fm = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md, flags=re.DOTALL)
    if fm:
        fm_text = fm.group(1)
        def getf(key):
            m = re.search(rf"^{key}:\s*[\"']?(.*?)[\"']?\s*$", fm_text, flags=re.MULTILINE)
            return m.group(1).strip() if m else ""
        title = getf("title"); channel = getf("channel"); date = getf("date")
        md = md[fm.end():]
    if not title:
        m = re.search(r"^#\s+(.*)$", md, flags=re.MULTILINE)
        title = m.group(1).strip() if m else os.path.basename(md_path)

    def inline(s):
        s = H.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
        return s

    def block_to_html(text):
        out = []
        lines = text.strip().split("\n")
        i = 0
        while i < len(lines):
            t = lines[i].strip()
            if t == "":
                i += 1; continue
            if re.match(r"^-{3,}$", t):
                out.append("<hr/>"); i += 1; continue
            if t.startswith("|"):
                rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append(lines[i].strip()); i += 1
                cellrows = [[c.strip() for c in r.split("|")[1:-1]] for r in rows]
                data_rows = [r for r in cellrows if not all(re.match(r"^:?-{3,}:?$", c) for c in r)]
                hr = []
                for idx, r in enumerate(data_rows):
                    tag = "th" if idx == 0 else "td"
                    hr.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in r) + "</tr>")
                out.append("<table>" + "".join(hr) + "</table>")
                continue
            if re.match(r"^[-*]\s+", t):
                items = []
                while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                    items.append("<li>" + inline(re.sub(r"^[-*]\s+", "", lines[i].strip())) + "</li>")
                    i += 1
                out.append("<ul>" + "".join(items) + "</ul>")
                continue
            out.append("<p>" + inline(t) + "</p>")
            i += 1
        return "\n".join(out)

    segments = re.split(r"(?m)^(#{1,2})[ \t]+(.*?)[ \t]*$", md)
    chapters = []
    idx = 1
    while idx < len(segments):
        level = segments[idx]; heading = segments[idx+1].strip()
        content = segments[idx+2] if idx+2 < len(segments) else ""
        chapters.append((level, heading, content)); idx += 3

    content_chapters = []
    for level, heading, content in chapters:
        html = block_to_html(content)
        if level == "#":
            title = heading
        else:
            content_chapters.append((heading, html))

    title_page_body = ""
    if content_chapters and content_chapters[0][0].startswith("视频信息"):
        _, info_html = content_chapters.pop(0)
        title_page_body = info_html

    title_page = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="zh">
<head><meta charset="utf-8"/><title>{H.escape(title)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body><h1 class="book-title">{H.escape(title)}</h1>{title_page_body}</body></html>"""

    spine = [("title", title, title_page)]
    nav_items = [("title", "封面")]
    for i, (heading, html) in enumerate(content_chapters, start=1):
        cid = f"ch{i}"
        cxhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="zh">
<head><meta charset="utf-8"/><title>{H.escape(heading)}</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body><h1>{H.escape(heading)}</h1>{html}</body></html>"""
        spine.append((cid, heading, cxhtml))
        nav_items.append((cid, heading))

    css = """body { font-family: "PingFang SC", "Songti SC", serif; line-height: 1.7; margin: 0; padding: 0 1em 1em 1em; }
h1.book-title { font-size: 1.6em; margin: 1em 0 0.8em; }
h1 { font-size: 1.35em; margin: 1.2em 0 0.7em; }
p { margin: 0.6em 0; text-align: justify; }
table { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
th, td { border: 1px solid #bbb; padding: 0.4em 0.6em; font-size: 0.9em; text-align: left; }
th { background: #f0f0f0; }
hr { border: none; border-top: 1px solid #ccc; margin: 1em 0; }
ul { margin: 0.6em 0; padding-left: 1.4em; }
li { margin: 0.3em 0; }
a { color: #06c; }
"""
    uid = "urn:uuid:2e9a1f8c-4b6d-4c7e-9a3b-5f1c2d3e4a5f"
    nav_body = "\n".join(f'<li><a href="{cid}.xhtml">{H.escape(t)}</a></li>' for cid, t in nav_items)
    nav_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh">
<head><meta charset="utf-8"/><title>目录</title></head>
<body><nav epub:type="toc" id="toc"><h1>目录</h1><ol>{nav_body}</ol></nav></body></html>"""
    navPoints = "\n".join(
        f'<navPoint id="np_{cid}" playOrder="{i}"><navLabel><text>{H.escape(t)}</text></navLabel><content src="{cid}.xhtml"/></navPoint>'
        for i, (cid, t) in enumerate(nav_items, start=1))
    ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="{uid}"/></head>
<docTitle><text>{H.escape(title)}</text></docTitle>
<navMap>{navPoints}</navMap></ncx>"""
    manifest_items = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                      '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                      '<item id="css" href="style.css" media-type="text/css"/>']
    for cid, t, _ in spine:
        manifest_items.append(f'<item id="{cid}" href="{cid}.xhtml" media-type="application/xhtml+xml"/>')
    spine_items = ['<itemref idref="nav" linear="no"/>'] + [f'<itemref idref="{cid}"/>' for cid, t, _ in spine]
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">{uid}</dc:identifier>
<dc:title>{H.escape(title)}</dc:title>
<dc:creator>{H.escape(channel)}</dc:creator>
<dc:language>zh-Hans</dc:language>
<dc:date>{date}</dc:date>
<meta property="dcterms:modified">2026-09-30T00:00:00Z</meta>
</metadata>
<manifest>{chr(10).join(manifest_items)}</manifest>
<spine>{chr(10).join(spine_items)}</spine>
</package>"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container)
        z.writestr("OEBPS/content.opf", opf)
        z.writestr("OEBPS/nav.xhtml", nav_xhtml)
        z.writestr("OEBPS/toc.ncx", ncx)
        z.writestr("OEBPS/style.css", css)
        for cid, t, x in spine:
            z.writestr(f"OEBPS/{cid}.xhtml", x)
    print(f"已生成: {out_path} ({os.path.getsize(out_path)} 字节, {len(spine)-1} 章)")

if __name__ == "__main__":
    import sys
    build_epub(sys.argv[1], sys.argv[2])
