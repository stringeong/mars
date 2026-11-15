from copy import deepcopy
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


SOURCE = Path('/home/sangin/.codex/attachments/28afb382-78ba-47f2-a891-0ede822af19b/2026-MARS-Doc-D06_스프린트개발명세서.docx')
OUTPUT = Path('/home/sangin/mars/docs/2026-MARS-Doc-D06_스프린트개발명세서_수정본.docx')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W}


def qn(name: str) -> str:
    return f'{{{W}}}{name}'


def paragraph_text(paragraph: ET.Element) -> str:
    return ''.join(node.text or '' for node in paragraph.findall('.//w:t', NS))


def set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    text_nodes = paragraph.findall('.//w:t', NS)
    if not text_nodes:
        run = ET.SubElement(paragraph, qn('r'))
        text_nodes = [ET.SubElement(run, qn('t'))]
    text_nodes[0].text = text
    for node in text_nodes[1:]:
        node.text = ''


def replace_paragraph(paragraph: ET.Element, replacements: dict[str, str]) -> None:
    current = paragraph_text(paragraph)
    if current in replacements:
        set_paragraph_text(paragraph, replacements[current])


def transform_text(paragraph: ET.Element) -> None:
    current = paragraph_text(paragraph)
    updated = re.sub(
        r'TK-(\d{3})',
        lambda match: f"TK-{int(match.group(1)) + 4:03d}"
        if 64 <= int(match.group(1)) <= 274 else match.group(0),
        current,
    )
    updated = re.sub(
        r'표\s*(\d+)',
        lambda match: f"표 {int(match.group(1)) + 1}"
        if int(match.group(1)) >= 10 else match.group(0),
        updated,
    )
    if updated != current:
        set_paragraph_text(paragraph, updated)


def clear_vertical_merge(cell: ET.Element) -> None:
    properties = cell.find('./w:tcPr', NS)
    if properties is not None:
        for node in list(properties):
            if node.tag == qn('vMerge'):
                properties.remove(node)


def set_cell_text(cell: ET.Element, text: str) -> None:
    paragraphs = cell.findall('./w:p', NS)
    if not paragraphs:
        paragraphs = [ET.SubElement(cell, qn('p'))]
    set_paragraph_text(paragraphs[0], text)
    for paragraph in paragraphs[1:]:
        set_paragraph_text(paragraph, '')


def append_row(table: ET.Element, template: ET.Element, values: list[str]) -> None:
    row = deepcopy(template)
    cells = row.findall('./w:tc', NS)
    if len(cells) != len(values):
        raise ValueError(f'Expected {len(values)} cells, got {len(cells)}')
    for cell, value in zip(cells, values):
        clear_vertical_merge(cell)
        set_cell_text(cell, value)
    table.append(row)


with ZipFile(SOURCE) as source_zip:
    contents = {name: source_zip.read(name) for name in source_zip.namelist()}

document = ET.fromstring(contents['word/document.xml'])
body = document.find('.//w:body', NS)
if body is None:
    raise RuntimeError('Word document body was not found.')

# Preserve all existing formatting while updating text held in paragraphs and tables.
for paragraph in body.findall('.//w:p', NS):
    transform_text(paragraph)

for paragraph in body.findall('.//w:p', NS):
    replace_paragraph(paragraph, {
        '[ 1~9 ]차 스프린트 - 개발 명세서': '[ 1~10 ]차 스프린트 - 개발 명세서',
        '2026년 11월 5일': '2026년 11월 12일',
        '6~9차 스프린트(9/1~10/30)에서는 사용자가 명시적으로 선택하고 전송에 동의한 블록에 한해 서버가 외부 LLM(OpenAI·Anthropic·Gemini)을 호출하는 기능, 사용자 Worker의 Ollama로 워크플로우를 생성하는 기능, 실행 타임라인, 커뮤니티 공유와 공개 제품 소개 페이지가 추가되었다.': '6~10차 스프린트(9/1~11/10)에서는 외부 LLM(OpenAI·Anthropic·Gemini) 연동과 전송 동의, 사용자 Worker의 Ollama 기반 워크플로우 생성, 실행 타임라인, 커뮤니티 공유·공개 제품 소개 페이지를 구현했다. 10차에는 공개 화면의 제품 메뉴·커뮤니티 동선, File Vault 폴더 마이그레이션, 외부·로컬 모델의 출력 토큰 상한과 release0.0.4 다운로드 링크를 정비했다.',
        '표 1. 1차 스프린트 태스크 목록 (63건)': '표 1. 1차 스프린트 태스크 목록 (67건)',
    })

tables = body.findall('.//w:tbl', NS)
if len(tables) < 9:
    raise RuntimeError(f'Expected at least 9 task tables, found {len(tables)}.')

# Add the missing branch work from 7/13 to Sprint 1. Existing task IDs from 064
# onward were shifted above so the task sequence stays chronological and unique.
sprint_one = tables[0]
row_template = sprint_one.findall('./w:tr', NS)[-1]
for row_values in [
    ['US-64', '자동 테스트·CI', 'TK-064', 'DAG 검증·오케스트레이터·Worker 샌드박스 pytest 스위트와 GitHub Actions CI 구성', '김현정', '7/13', '100'],
    ['US-65', '통합 테스트 확대', 'TK-065', '인증·JWT·API E2E·생성기 LLM mock·Worker 실행기 테스트 추가', '김현정', '7/13', '100'],
    ['US-66', '테스트 운영 문서', 'TK-066', '테스트 가이드 작성과 커버리지 산출물 gitignore 처리', '김현정', '7/13', '100'],
    ['US-67', 'Docker 개발 환경', 'TK-067', '서버·웹·Worker Dockerfile, Compose, 환경 변수 예시와 시작 스크립트 구성', '박상인', '7/13', '100'],
]:
    append_row(sprint_one, row_template, row_values)

# Create a separate Sprint 10 table from the Sprint 9 table style.
sprint_nine = tables[8]
header = deepcopy(sprint_nine.findall('./w:tr', NS)[0])
template = sprint_nine.findall('./w:tr', NS)[1]
sprint_ten = deepcopy(sprint_nine)
for row in list(sprint_ten.findall('./w:tr', NS)):
    sprint_ten.remove(row)
sprint_ten.append(header)
for row_values in [
    ['US-68', '공개 화면 탐색 개선', 'TK-279', '제품 소개 접이식 메뉴·커뮤니티 우선 노출·추천 예시 접기 등 공개 메뉴 동선 정비', '박상인', '11/10', '100'],
    ['US-69', 'File Vault 폴더', 'TK-280', 'file_folders 테이블과 uploaded_files.folder_id 마이그레이션 추가', '박상인', '11/10', '100'],
    ['US-70', '출력 길이 설정', 'TK-281', 'MARS_MAX_OUTPUT_TOKENS 설정을 OpenAI·Anthropic·Gemini와 로컬 Ollama 실행에 적용', '박상인', '11/10', '100'],
    ['US-71', 'release0.0.4 배포 정보', 'TK-282', 'Worker 다운로드 링크의 릴리스 버전을 release0.0.4로 갱신', '박상인', '11/10', '100'],
]:
    append_row(sprint_ten, template, row_values)

heading_template = None
caption_template = None
for paragraph in body.findall('./w:p', NS):
    if paragraph_text(paragraph) == '2.9 9차 스프린트 — 10/23 ~ 10/30':
        heading_template = paragraph
    if paragraph_text(paragraph) == '표 9. 9차 스프린트 태스크 목록 (26건)':
        caption_template = paragraph
if heading_template is None or caption_template is None:
    raise RuntimeError('Sprint 9 heading or caption was not found.')

heading = deepcopy(heading_template)
set_paragraph_text(heading, '2.10 10차 스프린트 — 10/31 ~ 11/10')
caption = deepcopy(caption_template)
set_paragraph_text(caption, '표 10. 10차 스프린트 태스크 목록 (4건)')

technical_heading = next(
    (paragraph for paragraph in body.findall('./w:p', NS) if paragraph_text(paragraph) == '3. 기술 명세'),
    None,
)
if technical_heading is None:
    raise RuntimeError('Technical specification heading was not found.')
insert_at = list(body).index(technical_heading)
body.insert(insert_at, heading)
body.insert(insert_at + 1, caption)
body.insert(insert_at + 2, sprint_ten)

contents['word/document.xml'] = ET.tostring(document, encoding='utf-8', xml_declaration=True)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(OUTPUT, 'w', ZIP_DEFLATED) as output_zip:
    for name, data in contents.items():
        output_zip.writestr(name, data)

print(OUTPUT)
