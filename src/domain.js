'use strict';
// ==DOMAIN-START==
// 순수 도메인 로직 (브라우저/DOM 미의존). tests/test_domain.py 가 이 블록을 그대로 검증한다.
const ChallengeDomain = (() => {

  // ---------- 유틸 ----------
  function pad2(n) { return String(n).padStart(2, '0'); }
  function dateKeyOf(d) { return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()); }
  function addDays(dateKey, n) {
    const p = String(dateKey).split('-').map(Number);
    const d = new Date(p[0], p[1] - 1, p[2]);
    d.setDate(d.getDate() + n);
    return dateKeyOf(d);
  }
  function daysBetween(a, b) {
    const pa = String(a).split('-').map(Number), pb = String(b).split('-').map(Number);
    const da = new Date(pa[0], pa[1] - 1, pa[2]), db = new Date(pb[0], pb[1] - 1, pb[2]);
    return Math.round((db - da) / 86400000);
  }
  function todayKey() { return dateKeyOf(new Date()); }
  function uid(prefix) {
    const rnd = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID().replace(/-/g, '').slice(0, 10)
      : Math.random().toString(36).slice(2, 12);
    return prefix + '_' + rnd;
  }
  function isValidDateKey(s) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(s || ''))) return false;
    const p = String(s).split('-').map(Number);
    const d = new Date(p[0], p[1] - 1, p[2]);
    return d.getFullYear() === p[0] && d.getMonth() + 1 === p[1] && d.getDate() === p[2];
  }

  // ---------- 라우팅 / PIN ----------
  function isAdminRoute(hash) {
    return /^#\/?admin(\/|$)/i.test(String(hash || ''));
  }
  function isValidPin(pin) { return /^\d{4}$/.test(String(pin || '')); }
  function checkPin(input, pin) { return String(input || '') === String(pin || '') && isValidPin(pin); }

  // ---------- 기기 바인딩 ----------
  function tokenOfMember(claims, memberId) {
    const c = claims[memberId];
    return c ? c.token : null;
  }
  function claimDevice(state, memberId, token, now) {
    if (!state.config.members.some(m => m.id === memberId)) {
      return { ok: false, reason: 'unknown_member', state };
    }
    const existing = state.claims[memberId];
    if (existing && existing.token !== token) {
      return { ok: false, reason: 'already_claimed', state };
    }
    for (const [mid, c] of Object.entries(state.claims)) {
      if (c.token === token && mid !== memberId) {
        return { ok: false, reason: 'device_busy', state };
      }
    }
    const next = JSON.parse(JSON.stringify(state));
    next.claims[memberId] = { token, claimedAt: now };
    return { ok: true, reason: 'ok', state: next };
  }
  function releaseDevice(state, memberId) {
    const next = JSON.parse(JSON.stringify(state));
    delete next.claims[memberId];
    return { ok: true, state: next };
  }

  // ---------- 인증 토글 ----------
  function canToggle(state, req) {
    const cfg = state.config;
    if (!cfg.missions.some(m => m.id === req.missionId)) return { ok: false, reason: 'unknown_mission' };
    if (!cfg.members.some(m => m.id === req.memberId)) return { ok: false, reason: 'unknown_member' };
    const myToken = tokenOfMember(state.claims, req.memberId);
    if (!myToken) return { ok: false, reason: 'not_claimed' };
    if (myToken !== req.deviceToken) return { ok: false, reason: 'not_owner' };
    if (req.dateKey !== req.todayKey) return { ok: false, reason: 'date_locked' };
    const win = challengeWindow(cfg, req.todayKey);
    const off = daysBetween(cfg.startDate, req.dateKey);
    if (off < 0 || off >= cfg.durationDays) return { ok: false, reason: 'out_of_range' };
    return { ok: true, reason: 'ok' };
  }
  function toggleCheckin(state, req, now) {
    const gate = canToggle(state, req);
    if (!gate.ok) return { ok: false, reason: gate.reason, completed: false, state };
    const key = req.memberId + '|' + req.dateKey + '|' + req.missionId;
    const next = JSON.parse(JSON.stringify(state));
    let completed;
    if (next.checkins[key]) { delete next.checkins[key]; completed = false; }
    else { next.checkins[key] = { at: now }; completed = true; }
    return { ok: true, reason: 'ok', completed, state: next };
  }

  // ---------- 진행도 ----------
  function challengeWindow(cfg, todayKeyStr) {
    const total = cfg.durationDays;
    const diff = daysBetween(cfg.startDate, todayKeyStr); // 시작일=0
    const started = diff >= 0;
    const ended = diff > total - 1;
    const day = Math.max(0, Math.min(diff + 1, total));
    const elapsed = Math.max(0, Math.min(diff + 1, total));
    return {
      started, ended, day, elapsed, total,
      daysLeft: Math.max(0, total - elapsed),
      progressPct: Math.round(elapsed / total * 100),
      endDate: addDays(cfg.startDate, total - 1),
    };
  }
  function missionDayCells(state, memberId, dateKey) {
    const done = {};
    for (const m of state.config.missions) {
      done[m.id] = !!state.checkins[memberId + '|' + dateKey + '|' + m.id];
    }
    return done;
  }
  function memberDayStatus(state, memberId, dateKey) {
    const missions = state.config.missions;
    const doneIds = missions.filter(m => state.checkins[memberId + '|' + dateKey + '|' + m.id]).map(m => m.id);
    return {
      done: doneIds.length,
      total: missions.length,
      allClear: missions.length > 0 && doneIds.length === missions.length,
      completedMissionIds: doneIds,
    };
  }
  function todayGroups(cfg, state, todayKeyStr) {
    const groups = { allClear: [], partial: [], none: [] };
    for (const m of cfg.members) {
      const st = memberDayStatus(state, m.id, todayKeyStr);
      if (st.total > 0 && st.done === st.total) groups.allClear.push(m);
      else if (st.done > 0) groups.partial.push(m);
      else groups.none.push(m);
    }
    return groups;
  }
  function countCells(state, memberId) {
    let n = 0;
    const prefix = memberId + '|';
    for (const k of Object.keys(state.checkins)) if (k.indexOf(prefix) === 0) n++;
    return n;
  }
  function memberProgressRate(cfg, state, memberId, todayKeyStr) {
    const win = challengeWindow(cfg, todayKeyStr);
    const denom = win.elapsed * cfg.missions.length;
    if (denom <= 0) return 0;
    return Math.min(100, Math.round(countCells(state, memberId) / denom * 100));
  }
  function memberFinalRate(cfg, state, memberId) {
    const denom = cfg.durationDays * cfg.missions.length;
    if (denom <= 0) return 0;
    return Math.min(100, Math.round(countCells(state, memberId) / denom * 100));
  }

  // ---------- 매트릭스 ----------
  function matrix(cfg, state, todayKeyStr, filter) {
    const days = [];
    for (let i = 0; i < cfg.durationDays; i++) {
      const dk = addDays(cfg.startDate, i);
      days.push({ day: i + 1, dateKey: dk, isToday: dk === todayKeyStr, isFuture: dk > todayKeyStr });
    }
    const rows = cfg.members.map(m => {
      const cells = days.map(d => {
        const done = missionDayCells(state, m.id, d.dateKey);
        let stamps = cfg.missions.map(ms => ({ missionId: ms.id, icon: ms.icon, on: !!done[ms.id] }));
        if (filter && filter !== 'all') stamps = stamps.filter(s => s.missionId === filter);
        const doneCount = cfg.missions.filter(ms => done[ms.id]).length;
        return {
          day: d.day, dateKey: d.dateKey, isToday: d.isToday, isFuture: d.isFuture,
          doneCount, allClear: cfg.missions.length > 0 && doneCount === cfg.missions.length,
          stamps,
        };
      });
      return {
        memberId: m.id, name: m.name,
        rate: memberProgressRate(cfg, state, m.id, todayKeyStr),
        cells,
      };
    });
    return { days, rows };
  }

  // ---------- 카톡 문구 ----------
  function shortName(name) {
    const n = String(name || '').trim();
    if (n.length >= 3 && /[가-힣]$/.test(n)) return n.slice(1);
    return n;
  }
  function kakaoMessage(cfg, state, todayKeyStr, template, url) {
    const win = challengeWindow(cfg, todayKeyStr);
    const link = url || cfg.noticeUrl || '';
    const withLink = (s) => s + (link ? '\n👉 인증 링크: ' + link : '');
    if (template === 'nudge') {
      const pending = cfg.members.filter(m => memberDayStatus(state, m.id, todayKeyStr).done === 0);
      if (pending.length === 0) {
        return withLink('🎉 오늘은 모든 멤버가 인증을 마쳤어요! 대단합니다 👏');
      }
      const names = pending.map(m => shortName(m.name) + '님').join(' ');
      return withLink(
        '⏰ [책모임 챌린지] 오늘 인증 마감 전!\n' +
        names + ' 오늘 미션 인증 원탭 콕 찍어주세요 😆\n' +
        '작은 습관 하나가 모여 완주가 됩니다 🎁'
      );
    }
    if (template === 'final') {
      const rates = cfg.members.map(m => ({ m, rate: memberFinalRate(cfg, state, m.id) }))
        .sort((a, b) => b.rate - a.rate);
      const perfect = rates.filter(r => r.rate === 100).map(r => shortName(r.m.name));
      const others = rates.filter(r => r.rate < 100).map(r => shortName(r.m.name) + '(' + r.rate + '%)');
      let s = '🏁 [책모임 챌린지 최종 완주 결과!]\n모든 멤버 정말 고생 많으셨습니다 👏\n';
      if (perfect.length) s += '👑 퍼펙트 완주: ' + perfect.join(', ') + ' (짝짝짝!)\n';
      if (others.length) s += '🥈 우수 달성: ' + others.join(', ') + '\n';
      s += '모임 때 다 같이 축하 파티해요 ☕️';
      return withLink(s);
    }
    // today
    const g = todayGroups(cfg, state, todayKeyStr);
    const list = (arr) => arr.map(m => shortName(m.name));
    let s = '📚 [책모임 챌린지 DAY ' + win.day + ' 중간현황]\n';
    if (g.allClear.length) s += '👑 오늘 올클리어(' + cfg.missions.length + '/' + cfg.missions.length + ' 완료): ' + list(g.allClear).join(', ') + ' 👏\n';
    const iconsOf = (m) => cfg.missions
      .filter(ms => state.checkins[m.id + '|' + todayKeyStr + '|' + ms.id])
      .map(ms => ms.icon).join('');
    if (g.partial.length) s += '🏃 ' + cfg.missions.length + '개 중 일부 달성 중: ' + g.partial.map(m => shortName(m.name) + '(' + iconsOf(m) + ')').join(', ') + '\n';
    if (g.none.length) s += '⏳ 아직: ' + list(g.none).join(', ') + '!\n';
    s += '\n오늘도 미션 인증하고 하루를 마무리해요 🌙';
    return withLink(s);
  }

  // ---------- 설정 위생화 ----------
  function sanitizeConfig(cfg) {
    if (!cfg || typeof cfg !== 'object') return { ok: false, error: 'invalid_config' };
    const out = JSON.parse(JSON.stringify(cfg));
    out.version = 1;
    out.title = String(out.title || '').trim() || '책모임 챌린지';
    out.subtitle = String(out.subtitle || '').trim();
    if (!isValidDateKey(out.startDate)) return { ok: false, error: 'invalid_start_date' };
    out.durationDays = Math.max(1, Math.min(60, Math.round(Number(out.durationDays) || 0)));
    if (out.adminPin !== undefined && out.adminPin !== null && out.adminPin !== '') {
      if (!isValidPin(out.adminPin)) return { ok: false, error: 'invalid_pin' };
      out.adminPin = String(out.adminPin);
    } else {
      out.adminPin = '1234';
    }
    out.noticeUrl = String(out.noticeUrl || '').trim();

    // 멤버: 공백 정리, 빈 항목 제거, 중복 이름 제거, id 보존/발급
    const seen = new Set();
    const members = [];
    for (const m of (out.members || [])) {
      const name = String(m && m.name || '').trim();
      if (!name || seen.has(name)) continue;
      seen.add(name);
      members.push({ id: (m.id && String(m.id)) || uid('m'), name });
    }
    if (members.length === 0) return { ok: false, error: 'no_members' };
    out.members = members;

    // 미션: 이름 있는 항목만, icon 1~2자, short 기본값
    const missions = [];
    for (const ms of (out.missions || [])) {
      const name = String(ms && ms.name || '').trim();
      if (!name) continue;
      let icon = String(ms.icon || '⭐').trim();
      if ([...icon].length > 2) icon = [...icon][0];
      const short = String(ms.short || '').trim() || [...name].slice(0, 2).join('');
      missions.push({ id: (ms.id && String(ms.id)) || uid('ms'), icon, name, desc: String(ms.desc || '').trim(), short });
    }
    if (missions.length === 0) return { ok: false, error: 'no_missions' };
    out.missions = missions;
    return { ok: true, config: out };
  }
  function parseMembersText(text, existingMembers) {
    const existing = {};
    for (const m of (existingMembers || [])) existing[m.name] = m.id;
    const seen = new Set();
    const out = [];
    for (let name of String(text || '').split('\n')) {
      name = name.trim();
      if (!name || seen.has(name)) continue;
      seen.add(name);
      out.push({ id: existing[name] || uid('m'), name });
    }
    return out;
  }

  // ---------- 기본 설정 ----------
  const DEFAULT_CONFIG = {
    version: 1,
    title: '매일 물마시기 & 30분 독서',
    subtitle: '몸과 마음을 채우는 14일간의 건강 습관',
    startDate: '2026-11-01',
    durationDays: 14,
    members: ['강은영', '이지수', '박민선', '정혜진', '김유정', '한소영'].map(n => ({ id: '', name: n })),
    missions: [
      { id: 'ms_water', icon: '💧', name: '물 1.5L 마시기', desc: '텀블러 3잔 촉촉하게 비우기', short: '물' },
      { id: 'ms_book', icon: '📖', name: '하루 30분 책 읽기', desc: '이달의 선정도서 또는 자유 도서', short: '독서' },
    ],
    adminPin: '1234',
    noticeUrl: '',
  };

  return {
    dateKeyOf, addDays, daysBetween, todayKey, isValidDateKey, uid,
    isAdminRoute, isValidPin, checkPin,
    claimDevice, releaseDevice, canToggle, toggleCheckin,
    challengeWindow, memberDayStatus, todayGroups,
    memberProgressRate, memberFinalRate, countCells,
    matrix, kakaoMessage, shortName,
    sanitizeConfig, parseMembersText, DEFAULT_CONFIG,
  };
})();
// ==DOMAIN-END==
