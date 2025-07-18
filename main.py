import os
from pathlib import Path
import re
import natsort

import zipfile
import shutil

import shutil

# === ルビ変換関数 ===
def convert_ruby(text: str) -> str:
	text = re.sub(r'[｜|]([^\s《｜|()]{1,50})《(.+?)》', r'<ruby>\1<rt>\2</rt></ruby>', text)
	text = re.sub(r'(?<![｜|])([一-龯々〆ヵヶ]{1,20})《([ぁ-ゖ゛゜ーァ-ヾ]{1,20})》', r'<ruby>\1<rt>\2</rt></ruby>', text)
	text = re.sub(r'(?<![｜|])([一-龯々〆ヵヶ]{1,20})\(([ぁ-ゖ゛゜ーァ-ヾ]{1,20})\)', r'<ruby>\1<rt>\2</rt></ruby>', text)
	return text

# === 段落変換関数（EPUB3向け） ===
def convert_to_paragraphs(text: str) -> str:
	lines = text.splitlines()
	result = []
	buffer = []
	empty_count = 0

	for line in lines:
		line_raw = line.rstrip('\r\n')  # 改行のみ除去
		only_spaces = line_raw.strip()

		# 空行系処理
		if not only_spaces:
			empty_count += 1
			if empty_count >= 3:
				if buffer:
					result.append(f"<p>{''.join(buffer)}</p>")
					buffer = []
				result.append('<hr class="page-break" />')
				empty_count = 0
			else:
				if buffer:
					result.append(f"<p>{''.join(buffer)}</p>")
					buffer = []
				result.append('<p></p>')
			continue

		empty_count = 0

		# 字送り判定（ただしスペースは保持）
		if re.match(r'^(　|\s{2,})', line_raw):
			if buffer:
				result.append(f"<p>{''.join(buffer)}</p>")
				buffer = []
			buffer.append(line_raw)
		else:
			buffer.append(line_raw)

	# 最後の段落
	if buffer:
		result.append(f"<p>{''.join(buffer)}</p>")

	return "\n".join(result)


# === パス設定 ===
base_dir = Path(__file__).parent
text_root = base_dir / "text"
output_root = base_dir / "epub-output" / "OEBPS"
output_root.mkdir(parents=True, exist_ok=True)

# 作品フォルダの取得
subdirs = [d for d in text_root.iterdir() if d.is_dir()]
if not subdirs:
	print("エラー: text/ 配下に作品フォルダがありません。")
	exit(1)

if len(subdirs) > 1:
	print("警告: text/ 配下に複数の作品フォルダがあります。最初の1つだけを使用します。")

work_dir = subdirs[0]
work_name = work_dir.name
txt_files = natsort.natsorted(list(work_dir.glob("*.txt")), alg=natsort.IC)

# ファイル名表示
print(f"処理対象作品: {work_name}")
print(f"出力ファイル名: {work_name}.epub")
print(f"読み込みファイル（{len(txt_files)}件）:")
for f in txt_files:
	print(" -", f.name)

# === XHTML出力 ===
for i, txt_file in enumerate(txt_files):
	filename = txt_file.stem
	lines = txt_file.read_text(encoding='utf-8').splitlines()
	if not lines:
		continue

	h2 = lines[0].strip()
	body_text = "\n".join(lines[1:])
	body_converted = convert_ruby(body_text)
	body_paragraphs = convert_to_paragraphs(body_converted)

	chapter_id = f"chapter{str(i+1).zfill(2)}"
	next_link = ""
	if i + 1 < len(txt_files):
		next_chapter = f"chapter{str(i + 2).zfill(2)}.xhtml"
		next_link = f'<p class="next-link"><a href="{next_chapter}">次の章へ進む</a></p>'

	xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>{filename}</title>
</head>
<body>
<h1>{filename}</h1>
<h2>{h2}</h2>
{body_paragraphs}
{next_link}
</body>
</html>
'''
	out_path = output_root / f"{chapter_id}.xhtml"
	out_path.write_text(xhtml, encoding="utf-8")
	print(f"{out_path.name} を出力しました。")

# === nav.xhtml（EPUB3目次）を出力 ===
nav_path = output_root / "nav.xhtml"

nav_items = []
for i, txt_file in enumerate(txt_files):
	chapter_num = str(i + 1).zfill(2)
	chapter_id = f"chapter{chapter_num}.xhtml"
	title = txt_file.stem  # ファイル名をタイトルに
	nav_items.append(f'<li><a href="{chapter_id}">{title}</a></li>')

nav_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"
	  xmlns:epub="http://www.idpf.org/2007/ops">
<head>
	<title>目次</title>
</head>
<body>
<nav epub:type="toc" id="toc">
	<h1>目次</h1>
	<ol>
{chr(10).join(nav_items)}
	</ol>
</nav>
</body>
</html>
'''

nav_path.write_text(nav_xhtml, encoding="utf-8")
print("nav.xhtml（EPUB3目次）を出力しました。")


# === content.opf（EPUB3用パッケージ）を出力 ===
opf_path = output_root / "content.opf"

# 各章の item と spine を生成
manifest_items = []
spine_items = []

for i, txt_file in enumerate(txt_files):
	chapter_num = str(i + 1).zfill(2)
	chapter_id = f"chapter{chapter_num}"
	xhtml_file = f"{chapter_id}.xhtml"
	manifest_items.append(f'<item id="{chapter_id}" href="{xhtml_file}" media-type="application/xhtml+xml"/>')
	spine_items.append(f'<itemref idref="{chapter_id}" />')

# nav.xhtml の manifest entry（EPUB3では必須）
manifest_items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')

# 1つの content.opf にまとめる
content_opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:txt2epub</dc:identifier>
    <dc:title>{work_name}</dc:title>
    <dc:language>ja</dc:language>
    <meta property="dcterms:modified">2025-07-18T00:00:00Z</meta>
  </metadata>
  <manifest>
    {chr(10).join(manifest_items)}
  </manifest>
  <spine>
    {chr(10).join(spine_items)}
  </spine>
</package>
'''

# 書き出し
opf_path.write_text(content_opf, encoding="utf-8")
print("content.opf（EPUB3）を出力しました。")

# === EPUB3 構成ファイルの出力とパッケージング ===
epub_root = base_dir / "epub-output"
meta_inf_dir = epub_root / "META-INF"
meta_inf_dir.mkdir(parents=True, exist_ok=True)

# --- mimetype を出力（非圧縮・先頭に必要） ---
mimetype_path = epub_root / "mimetype"
mimetype_path.write_text("application/epub+zip", encoding="utf-8")

# --- META-INF/container.xml を出力 ---
container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0"
  xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
      media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
'''
(meta_inf_dir / "container.xml").write_text(container_xml, encoding="utf-8")

# --- EPUB出力ファイルパス ---
epub_output_path = epub_root / f"{work_name}.epub"

# --- ZIP (EPUB) の書き込み ---
with zipfile.ZipFile(epub_output_path, "w", compression=zipfile.ZIP_STORED) as epub:
	# mimetype（非圧縮・先頭）
	epub.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

# 追記モードで他ファイルを追加
with zipfile.ZipFile(epub_output_path, "a", compression=zipfile.ZIP_DEFLATED) as epub:
	# META-INF/
	for file in meta_inf_dir.glob("*"):
		epub.write(file, f"META-INF/{file.name}")

	# OEBPS/
	for file in output_root.glob("*"):
		epub.write(file, f"OEBPS/{file.name}")

print(f"{epub_output_path.name} を出力しました。")


# === スタイルシートテンプレートを OEBPS にコピー ===
css_source = base_dir / "css-template" / "base.css"
css_dest = output_root / "stylesheet.css"

if css_source.exists():
	shutil.copy(css_source, css_dest)
	print("スタイルシート（stylesheet.css）をコピーしました。")
else:
	print("警告: css-template/base.css が見つかりません。")

