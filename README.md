# 📚 bookclub-challenge

책모임 멤버들을 위한 듀얼 챌린지(💧 물마시기 + 📖 30분 독서) 원페이지 웹앱.
SDD(Spec-Driven Development) + TDD(Test-Driven Development)로 개발했습니다.

## 🔗 접속 주소

| 대상 | URL |
|---|---|
| 일반 멤버 (단톡방 공유용) | https://rapperism.github.io/bookclub-challenge/ |
| 모임장 관리실 (은영 전용) | https://rapperism.github.io/bookclub-challenge/#admin |
| 기본 관리자 PIN | `1234` |

- 관리실 탭은 `#admin` 링크로 접속한 화면에만 존재하고, 일반 링크에서는 아예 렌더링되지 않습니다.
- 관리실은 4자리 PIN 잠금이 있고, 관리실에서 PIN을 바꿀 수 있습니다.

## 📱 사용 방법

1. **첫 방문(기기 등록)** — 멤버가 공유 링크로 접속해 자기 이름을 누르면 이 폰이 전용 인증기로 등록됩니다.
   한 번 등록된 이름은 다른 기기에서 선택할 수 없어 대리 인증이 불가능합니다.
2. **원탭 인증** — 등록된 본인 기기에서만, 오늘 날짜에만, 미션별로 각각 원탭 인증합니다.
   2개 미션을 모두 완료하면 올클리어 배너가 뜹니다.
3. **전체 스탬프판** — 14일 매트릭스에 모든 멤버의 듀얼 도장이 표시되고, 내 행은 하이라이트됩니다.
4. **모임장 관리실** — 카톡 공유 문구 생성(3종), 미션 추가/수정/삭제, 시작일/기간/멤버 수정,
   기기 등록 해제, PIN 변경, 테스트 초기화.

## 🛠 개발 (SDD + TDD)

- `SPEC.md` — 데이터 스키마, 저장 키, 라우팅/권한 규칙, 핵심 비즈니스 로직 명세
- `src/domain.js` — 순수 도메인 로직 (DOM 미의존)
- `src/index.template.html` — UI 템플릿 (도메인 블록이 `index.html`로 인라인 빌드됨)
- `index.html` — 배포용 단일 파일 (바닐라 JS/CSS, 외부 의존성 0)
- `tests/` — 도메인 단위 테스트: index.html에 실제로 들어간 코드를 추출해 실행

```bash
# 빌드 (템플릿 + 도메인 → index.html)
python3 -c "import pathlib; tpl=pathlib.Path('src/index.template.html').read_text(); dom=pathlib.Path('src/domain.js').read_text(); pathlib.Path('index.html').write_text(tpl.replace('__DOMAIN_SOURCE__', dom))"

# 테스트 (Python 3.12 + quickjs)
pip install quickjs
python3 -m unittest discover -s tests -v
```

데이터는 브라우저 LocalStorage에만 저장됩니다(서버 없음). 기기·브라우저별로 기록이 유지됩니다.
