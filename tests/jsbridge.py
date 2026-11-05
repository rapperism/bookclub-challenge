"""TDD 하네스.

index.html 안의 `// ==DOMAIN-START==` ~ `// ==DOMAIN-END==` 블록(순수 도메인 로직)을
그대로 추출해 quickjs 로 실행한다. 즉 테스트는 '배포되는 코드'를 직접 검증하며,
테스트용 이중 구현이 없다.
"""

import json
import pathlib
import re

import quickjs

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "index.html"
DOMAIN_JS = ROOT / "src" / "domain.js"

DOMAIN_RE = re.compile(r"//\s*==DOMAIN-START==(.*?)//\s*==DOMAIN-END==", re.S)


def _extract_domain_block(text: str) -> str:
    m = DOMAIN_RE.search(text)
    if not m:
        raise RuntimeError("// ==DOMAIN-START== ~ // ==DOMAIN-END== 블록을 찾지 못했습니다.")
    return m.group(1)


def domain_source() -> str:
    """index.html 의 도메인 블록을 그대로 가져온다 (빌드/복사 없이 실배포 코드를 검증)."""
    if not INDEX_HTML.exists():
        raise RuntimeError(f"index.html 이 없습니다: {INDEX_HTML}")
    return _extract_domain_block(INDEX_HTML.read_text(encoding="utf-8"))


def domain_source_dev() -> str:
    """개발 중에는 src/domain.js 에서 읽는다."""
    return DOMAIN_JS.read_text(encoding="utf-8")


def _load_source() -> str:
    if INDEX_HTML.exists():
        html = INDEX_HTML.read_text(encoding="utf-8")
        if DOMAIN_RE.search(html):
            return domain_source()
    return domain_source_dev()


class Domain:
    """도메인 함수 호출기. call('matrix', cfg, state, ...) -> 파이썬 값."""

    _source_cache = None

    def __init__(self):
        if Domain._source_cache is None:
            Domain._source_cache = _load_source()
        self.ctx = quickjs.Context()
        self.ctx.eval(Domain._source_cache + "\n;globalThis.__DOMAIN__ = ChallengeDomain;")

    def eval(self, code: str):
        return self.ctx.eval(code)

    def call(self, fn, *args):
        expr = "__DOMAIN__[%s].apply(null, %s)" % (json.dumps(fn), json.dumps(list(args)))
        raw = self.ctx.eval("JSON.stringify(%s)" % expr)
        if raw is None:
            return None
        return json.loads(raw)
