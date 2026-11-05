# SPEC — 책모임 듀얼 챌린지 (bookclub-challenge)

> SDD(Spec-Driven Development) 명세서. 이 문서가 구현의 유일한 기준이며, `tests/`의
> 테스트는 이 명세의 "핵심 비즈니스 로직" 항목을 그대로 검증한다.
> 구현: `index.html` 내 `// ==DOMAIN-START==` ~ `// ==DOMAIN-END==` 블록 (순수 함수, DOM/브라우저 API 미사용)

---

## 1. 제품 개요

| 항목 | 내용 |
|---|---|
| 대상 | 책모임 멤버 6명 (강은영, 이지수, 박민선, 정혜진, 김유정, 한소영) |
| 기간 | 14일 (기본 시작일 2026-11-01 ~ 2026-11-14) |
| 미션 | 복수 미션 (기본 2개: 💧 물 1.5L 마시기 / 📖 하루 30분 책 읽기) |
| 배포 | GitHub Pages 정적 단일 파일 (`index.html`) |
| 저장 | 브라우저 LocalStorage (서버 없음) |
| 화면 | 일반 멤버 URL `/` · 모임장 전용 URL `/#admin` |

### URL / 권한 규칙
- `https://rapperism.github.io/bookclub-challenge/` → **일반 모드**. 관리실 탭은 DOM에 아예 생성되지 않는다.
- `https://rapperism.github.io/bookclub-challenge/#admin` → **모임장 모드**. 4자리 PIN 통과 후 관리실 사용 가능.
- 해시 판정: `#admin`, `#/admin`, `#admin/...` (대소문자 무시) → 관리 모드. 그 외 → 일반 모드.

---

## 2. 데이터 스키마

### 2.1 ChallengeConfig
```ts
type Mission = {
  id: string;        // 'ms_water' 등, 생성 후 불변
  icon: string;      // 이모지 1자 ('💧')
  name: string;      // '물 1.5L 마시기'
  desc: string;      // '텀블러 3잔 촉촉하게 비우기'
  short: string;     // '물' — 필터 칩/카톡 문구용 약칭
};

type Member = { id: string; name: string };   // id 는 이름 변경에도 유지

type ChallengeConfig = {
  version: 1;
  title: string;          // '매일 물마시기 & 30분 독서'
  subtitle: string;       // '몸과 마음을 채우는 14일간의 건강 습관'
  startDate: string;      // 'YYYY-MM-DD'
  durationDays: number;   // 1 ~ 60
  members: Member[];      // 최소 1명
  missions: Mission[];    // 최소 1개
  adminPin: string;       // 숫자 4자리, 기본 '1234'
  noticeUrl: string;      // 카톡 문구에 붙는 인증 링크 (빈 값이면 현재 페이지 URL)
};
```

### 2.2 CheckinState
```ts
type CheckinCell = { at: number };                 // epoch ms
type CheckinState = {
  // key = `${memberId}|${YYYY-MM-DD}|${missionId}`, 존재하면 '완료'
  [cellKey: string]: CheckinCell;
};
```

### 2.3 DeviceBinding / Claim
```ts
type Claim = { token: string; claimedAt: number };  // claims[memberId] = Claim
type DeviceBinding = { memberId: string; token: string; claimedAt: number };
// token: 브라우저당 1회 발급되는 UUID (crypto.randomUUID)
// 한 기기(토큰)는 오직 한 명의 멤버에만 바인딩된다.
```

### 2.4 AppState (도메인 함수가 받는 순수 상태)
```ts
type AppState = {
  config: ChallengeConfig;
  claims: { [memberId: string]: Claim };
  checkins: CheckinState;
};
```

### 2.5 LocalStorage 키
| 키 | 내용 | 수명 |
|---|---|---|
| `bcc.config.v1` | ChallengeConfig JSON | 영구 (관리실 저장 시 갱신) |
| `bcc.checkins.v1` | CheckinState JSON | 영구 |
| `bcc.claims.v1` | 이 기기에서 등록한 Claim 맵 | 영구 |
| `bcc.device.v1` | 이 브라우저의 DeviceBinding | 영구 (관리실에서 초기화) |
| `bcc.admin.v1` (sessionStorage) | `'1'` = 이번 세션 PIN 통과 | 탭 세션 |

### 2.6 상태 관리 라이프사이클
1. **부팅** — `loadConfig()`: 저장값 파싱 → `sanitizeConfig()`로 보정 → 실패 시 `DEFAULT_CONFIG`.
   `loadCheckins()` → 위생화(알 수 없는 멤버/미션/날짜 셀 제거).
2. **렌더** — `route()`: 해시 확인 → 관리 모드(잠금) / 일반 모드 결정 → 뷰 렌더.
3. **변이** — 모든 변이는 도메인 함수가 돌려준 **새 상태**로 교체 후 즉시 저장(`save*`).
   DOM을 진실원으로 두지 않는다.
4. **초기화** — 관리실에서 (a) 대회 기록만 초기화 (b) 이 기기 등록 해제 (c) 전체 초기화.

---

## 3. 라우팅 및 권한

```
hash = location.hash
adminRoute(hash) = /^#\/?admin(\/|$)/i.test(hash)

if adminRoute:  PIN 세션 없음 → 게이트 화면(핀패드), 통과 후 관리 탭(모임 현황 / 관리실)
else:           일반 모드. 관리실 DOM 생성 안 함, PIN 게이트 접근 불가
```
- PIN 검증: `checkPin(input, config.adminPin)` — 문자열 4자리 숫자 완전 일치.
- PIN 변경도 관리실(잠금 해제 상태)에서만 가능하며, 새 PIN도 4자리 숫자여야 한다.
- 일반 모드에서 `#admin`을 지우면 즉시 일반 모드로 복귀하고 관리 세션은 유지된다(같은 탭).

---

## 4. 핵심 비즈니스 로직

### 4.1 기기 바인딩 (Claim) — 대리 조작 방지
- `canClaim(state, memberId, token)` 결과
  | 조건 | reason |
  |---|---|
  | 존재하지 않는 멤버 | `unknown_member` |
  | 토큰 없음 | `no_device` |
  | 해당 멤버가 **다른** 토큰으로 이미 등록됨 | `already_claimed` |
  | 이 토큰이 **다른** 멤버에 이미 바인딩됨 | `device_busy` |
  | 그 외 | `ok` |
- `claimDevice()`: 통과 시 `claims[memberId] = {token, claimedAt}`. 같은 토큰의 재요청은 멱등(성공).
- `releaseDevice()`: 모임장 전용. `claims[memberId]` 삭제 → 다른 기기에서 재등록 가능.
- 등록 전에는 **어떤 인증도 불가**(`not_claimed`).

### 4.2 인증 토글 규칙 (`canToggle` / `toggleCheckin`)
| 검사 | reason |
|---|---|
| 미션 없음 / 멤버 없음 | `unknown_mission` / `unknown_member` |
| 내 기기 미등록 | `not_claimed` |
| 다른 사람 명의 (토큰 불일치) | `not_owner` |
| 대상 날짜 ≠ 오늘 | `date_locked` |
| 챌린지 기간 밖 | `out_of_range` |

→ 통과 시 해당 셀 토글(있으면 삭제, 없으면 `{at: now}`). 셀 키는 `memberId|date|missionId`.

### 4.3 진행도
- `challengeWindow(config, today)` = `{ day, total, elapsed, started, ended, daysLeft, progressPct }`
  - `day = clamp(today - start + 1, 1..total)` (시작 전이면 0)
  - `elapsed = clamp(today - start + 1, 0..total)` → **오늘 포함 경과일**
  - `progressPct = round(elapsed / total * 100)`
- `memberDayStatus(state, memberId, date)` = `{ done, total, allClear, completedMissionIds }`
- `todayGroups(config, state, today)` = `{ allClear: [], partial: [], none: [] }`
  - `allClear`: 완료 수 = 미션 수 (미션 0개면 아님)
  - `partial`: `0 < 완료 수 < 미션 수`
  - `none`: 완료 0
- `memberProgressRate()` = `round(완료 셀 수 / (elapsed × 미션 수) × 100)`, 상한 100. `elapsed=0`이면 0.
- `memberFinalRate()` = `round(완료 셀 수 / (total × 미션 수) × 100)` — 완주 결과용.

### 4.4 스탬프 매트릭스
`matrix(config, state, today, filter)` →
```ts
{ days: [{day, dateKey, isToday, isFuture}],
  rows: [{ memberId, name, rate,
           cells: [{day, dateKey, isToday, isFuture, doneCount, allClear,
                    stamps: [{missionId, icon, on}]}] }] }
```
- `filter`: `'all'` 또는 missionId. 지정 시 `stamps`는 그 미션만.
- 셀 표기: 완료 `icon`, 미완료 `○`.
- 달성률은 `memberProgressRate`.

### 4.5 카톡 공유 문구
`kakaoMessage(config, state, today, template, url)` — template: `'today' | 'nudge' | 'final'`
- `today`: DAY n 중간현황 + 올클리어/1개 달성/아직 명단 (없는 그룹은 생략)
- `nudge`: 오늘 인증이 하나도 없는 멤버를 `이름님`으로 나열, 전원 완료 시 축하 문구
- `final`: 퍼펙트 완주(100%) / 우수 달성(달성률 순 상위) 요약
- 이름 표기: 3자 이상 한글은 성을 뺀 이름(`강은영` → `은영`), 그 외는 그대로.

### 4.6 설정 저장 (`sanitizeConfig`)
- `title`/`subtitle` 공백 정리, 빈 제목은 기본값 대체
- `startDate`: `YYYY-MM-DD` 유효 형식만 (아니면 오류)
- `durationDays`: 정수 1~60으로 클램프
- `members`: 공백 제거, 빈 줄 제거, 중복 이름 제거, 이름 유지 시 기존 id 보존, 최소 1명
- `missions`: `name` 빈 항목 제거, `icon` 1~2자, `short` 비면 `name` 앞 2자, 최소 1개
- `adminPin`: 주어진 경우 4자리 숫자 검증
- `noticeUrl`: trim

---

## 5. UI 요구사항 (mockup 계승)

1. **첫 방문(미등록)** — 이름 선택 → "이 폰을 내 전용 인증기로 등록하기" 1회. 이미 등록된 이름은 🔒 표시로 선택 불가.
2. **참가자 화면** — 헤더(진행도 바, 시작/종료일), 내 원탭 인증 카드(미션별 분리 버튼), 올클리어 축하 배너, 오늘 멤버 3단 현황, 전체 스탬프 매트릭스(필터 3종·내 행 강조·오늘 열 강조).
3. **관리실** — PIN 게이트 4자리, 카톡 문구 3템플릿 + 원탭 복사, 미션 동적 추가/수정/삭제, 시작일/기간/멤버 수정, 기기 등록 현황 및 해제, PIN 변경, 백업(JSON 내보내기)/복원, 테스트용 초기화.
4. 모바일 우선(max-width 520px), Pretendard/Apple 시스템 폰트, 파스텔 카드 UI, 터치 44px 이상, iOS 입력 확대 방지(16px), 다크모드 미지원(라이트 고정).

---

## 6. 테스트 계획 (TDD)

`tests/test_domain.py` — Python 3.12 `unittest` + quickjs 로 **index.html에 실제로 들어간 도메인 코드**를 추출·실행하여 검증한다(이중 구현 없음).

| 그룹 | 케이스 |
|---|---|
| 바인딩 | 등록 전 인증 차단 / 본인 기기 성공 / 타 기기 `not_owner` / 타 토큰 재등록 `already_claimed` / 멱등 / 한 기기 2명 `device_busy` / 해제 후 재등록 |
| 인증 | 미래·과거 날짜 `date_locked` / 기간 밖 `out_of_range` / 1개 완료 / 올클리어 / 토글 취소 |
| 집계 | 경과일 달성률 / 완주 달성률 / 3그룹 분류 / 동적 미션 수 / 매트릭스 셀·필터·미래 셀 |
| 관리 | PIN 일치·불일치·형식 / `#admin` 라우팅 / 설정 위생화(중복·공백·최소값) / 카톡 3종 문구 |

실행: `python3 -m unittest discover -s tests -v` → **전부 Green** 이어야 배포한다.
