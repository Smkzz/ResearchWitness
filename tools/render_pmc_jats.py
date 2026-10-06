"""Render a captured Europe PMC JATS XML article as deterministic Markdown."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import xml.etree.ElementTree as ET


RENDERER_VERSION = 'jats-markdown-v1'


def _name(element: ET.Element) -> str:
    return element.tag.rsplit('}', 1)[-1]


def _plain(element: ET.Element | None) -> str:
    if element is None:
        return ''
    pieces = [element.text or '']
    for child in element:
        pieces.append(_plain(child))
        pieces.append(child.tail or '')
    return re.sub(r'\s+', ' ', ''.join(pieces)).strip()


def render(source: bytes) -> bytes:
    root = ET.fromstring(source)
    title = _plain(next((item for item in root.iter() if _name(item) == 'article-title'), None))
    lines = ['# ' + (title or 'Untitled article'), '']
    abstract = next((item for item in root.iter() if _name(item) == 'abstract'), None)
    if abstract is not None:
        lines.extend(['## Abstract', ''])
        for paragraph in abstract.iter():
            if _name(paragraph) == 'p':
                lines.extend([_plain(paragraph), ''])

    body = next((item for item in root.iter() if _name(item) == 'body'), None)

    def render_block(parent: ET.Element, depth: int) -> list[str]:
        output: list[str] = []
        for child in parent:
            tag = _name(child)
            if tag == 'title':
                continue
            if tag == 'sec':
                heading = _plain(next((item for item in child if _name(item) == 'title'), None))
                if heading:
                    output.extend([('#' * min(6, 3 + depth)) + ' ' + heading, ''])
                output.extend(render_block(child, depth + 1))
            elif tag == 'p':
                value = _plain(child)
                if value:
                    output.extend([value, ''])
            elif tag == 'table-wrap':
                label = _plain(next((item for item in child if _name(item) == 'label'), None))
                caption = _plain(next((item for item in child if _name(item) == 'caption'), None))
                heading = ' '.join(value for value in (label, caption) if value)
                if heading:
                    output.extend(['### ' + heading, ''])
                table = next((item for item in child.iter() if _name(item) == 'table'), None)
                if table is not None:
                    for row in table.iter():
                        if _name(row) != 'tr':
                            continue
                        cells = [
                            _plain(cell).replace('|', r'\|')
                            for cell in row if _name(cell) in ('th', 'td')
                        ]
                        if cells:
                            output.append('| ' + ' | '.join(cells) + ' |')
                    output.append('')
                foot = next((item for item in child if _name(item) == 'table-wrap-foot'), None)
                foot_text = _plain(foot)
                if foot_text:
                    output.extend([foot_text, ''])
            elif tag in ('fig', 'boxed-text', 'disp-formula'):
                value = _plain(child)
                if value:
                    output.extend(['### ' + value if tag == 'fig' else value, ''])
        return output

    if body is not None:
        lines.extend(render_block(body, 0))
    return ('\n'.join(lines).strip() + '\n').encode('utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_bytes(render(args.source.read_bytes()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
