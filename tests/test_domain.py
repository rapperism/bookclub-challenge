"""도메인 단위 테스트 (SDD 명세 §4 검증).

실행: cd challenge-app && python3 -m unittest discover -s tests -v
"""

import unittest

from jsbridge import Domain

MISSION_WATER = {"id": "ms1", "icon": "💧", "name": "물 1.5L 마시기", "desc": "텀블러 3잔", "short": "물"}
MISSION_BOOK = {"id": "ms2", "icon": "📖", "name": "하루 30분 책 읽기", "desc": "자유 도서", "short": "독서"}
MEMBERS = [
    {"id": "m1", "name": "강은영"},
    {"id": "m2", "name": "이지수"},
    {"id": "m3", "name": "박민선"},
]
TOKEN_A = "device-token-a"
TOKEN_B = "device-token-b"
TODAY = "2026-11-05"  # DAY 5 / 14


def make_config(**over):
    cfg = {
        "version": 1,
        "title": "매일 물마시기 & 30분 독서",
        "subtitle": "몸과 마음을 채우는 14일간의 건강 습관",
        "startDate": "2026-11-01",
        "durationDays": 14,
        "members": [dict(m) for m in MEMBERS],
        "missions": [dict(MISSION_WATER), dict(MISSION_BOOK)],
        "adminPin": "1234",
        "noticeUrl": "",
    }
    cfg.update(over)
    return cfg


def make_state(config=None, claims=None, checkins=None):
    return {
        "config": config or make_config(),
        "claims": claims or {},
        "checkins": checkins or {},
    }


def claimed(member_id, token, at=1000):
    return {member_id: {"token": token, "claimedAt": at}}


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = Domain()

    def ok(self, result):
        self.assertTrue(result["ok"], msg=f"실패 사유: {result}")


# ---------------------------------------------------------------- 기기 바인딩
class TestDeviceBinding(Base):
    def test_등록_전에는_인증할_수_없다(self):
        state = make_state()
        res = self.d.call("toggleCheckin", state, {
            "memberId": "m1", "missionId": "ms1",
            "dateKey": TODAY, "todayKey": TODAY, "deviceToken": TOKEN_A,
        }, 2000)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_claimed")
        self.assertEqual(res["state"]["checkins"], {})  # 상태 불변

    def test_등록하면_본인_기기에서_인증된다(self):
        state = make_state()
        claimed_state = self.d.call("claimDevice", state, "m1", TOKEN_A, 1500)["state"]
        res = self.d.call("toggleCheckin", claimed_state, {
            "memberId": "m1", "missionId": "ms1",
            "dateKey": TODAY, "todayKey": TODAY, "deviceToken": TOKEN_A,
        }, 2000)
        self.ok(res)
        self.assertTrue(res["completed"])
        self.assertIn("m1|2026-11-05|ms1", res["state"]["checkins"])

    def test_다른_기기에서는_남의_도장을_찍을_수_없다(self):
        state = make_state(claims=claimed("m1", TOKEN_A))
        res = self.d.call("toggleCheckin", state, {
            "memberId": "m1", "missionId": "ms1",
            "dateKey": TODAY, "todayKey": TODAY, "deviceToken": TOKEN_B,
        }, 2000)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "not_owner")
        self.assertEqual(res["state"]["checkins"], {})

    def test_이미_등록된_이름은_다른_토큰으로_등록할_수_없다(self):
        state = make_state(claims=claimed("m1", TOKEN_A))
        res = self.d.call("claimDevice", state, "m1", TOKEN_B, 1500)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "already_claimed")
        self.assertEqual(res["state"]["claims"]["m1"]["token"], TOKEN_A)

    def test_같은_토큰으로_다시_등록해도_성공한다_멱등(self):
        state = make_state(claims=claimed("m1", TOKEN_A))
        res = self.d.call("claimDevice", state, "m1", TOKEN_A, 1700)
        self.ok(res)
        self.assertEqual(res["state"]["claims"]["m1"]["claimedAt"], 1700)

    def test_한_기기가_두_명을_등록할_수_없다(self):
        state = make_state(claims=claimed("m1", TOKEN_A))
        res = self.d.call("claimDevice", state, "m2", TOKEN_A, 1500)
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "device_busy")
        self.assertNotIn("m2", res["state"]["claims"])

    def test_존재하지_않는_멤버는_등록_불가(self):
        res = self.d.call("claimDevice", make_state(), "nope", TOKEN_A, 1500)
        self.assertEqual(res["reason"], "unknown_member")

    def test_모임장이_해제하면_다른_기기에서_재등록_가능하다(self):
        state = make_state(claims=claimed("m1", TOKEN_A))
        released = self.d.call("releaseDevice", state, "m1")["state"]
        self.assertNotIn("m1", released["claims"])
        self.ok(self.d.call("claimDevice", released, "m1", TOKEN_B, 3000))


# ---------------------------------------------------------------- 인증 / 날짜
class TestCheckinRules(Base):
    def setUp(self):
        self.state = make_state(claims=claimed("m1", TOKEN_A))

    def toggle(self, mission="ms1", date=TODAY, today=TODAY, token=TOKEN_A, member="m1", state=None):
        return self.d.call("toggleCheckin", state or self.state, {
            "memberId": member, "missionId": mission,
            "dateKey": date, "todayKey": today, "deviceToken": token,
        }, 5000)

    def test_과거_날짜는_소급_인증할_수_없다(self):
        res = self.toggle(date="2026-11-04")
        self.assertEqual(res["reason"], "date_locked")
        self.assertEqual(res["state"]["checkins"], {})

    def test_미래_날짜도_인증할_수_없다(self):
        res = self.toggle(date="2026-11-06")
        self.assertEqual(res["reason"], "date_locked")

    def test_챌린지_기간_밖이면_인증_불가(self):
        res = self.toggle(date="2026-11-20", today="2026-11-20")
        self.assertEqual(res["reason"], "out_of_range")

    def test_미션_두_개를_모두_찍으면_올클리어(self):
        s1 = self.toggle("ms1")["state"]
        s2 = self.toggle("ms2", state=s1)["state"]
        status = self.d.call("memberDayStatus", s2, "m1", TODAY)
        self.assertEqual(status["done"], 2)
        self.assertEqual(status["total"], 2)
        self.assertTrue(status["allClear"])

    def test_하나만_찍으면_부분완료(self):
        s1 = self.toggle("ms1")["state"]
        status = self.d.call("memberDayStatus", s1, "m1", TODAY)
        self.assertEqual(status["done"], 1)
        self.assertFalse(status["allClear"])
        self.assertEqual(status["completedMissionIds"], ["ms1"])

    def test_다시_누르면_취소된다(self):
        s1 = self.toggle("ms1")["state"]
        res = self.toggle("ms1", state=s1)
        self.assertTrue(res["ok"])
        self.assertFalse(res["completed"])
        self.assertEqual(res["state"]["checkins"], {})

    def test_없는_미션은_인증_불가(self):
        self.assertEqual(self.toggle("nope")["reason"], "unknown_mission")


# ---------------------------------------------------------------- 집계 / 매트릭스
class TestProgress(Base):
    def build(self, rows):
        """rows: {memberId: {dateKey: [missionIds]}}"""
        checkins = {}
        for member_id, days in rows.items():
            for date_key, missions in days.items():
                for mission_id in missions:
                    checkins[f"{member_id}|{date_key}|{mission_id}"] = {"at": 1}
        return make_state(claims={m: {"token": TOKEN_A, "claimedAt": 1} for m in rows}, checkins=checkins)

    def test_챌린지_창_계산(self):
        win = self.d.call("challengeWindow", make_config(), TODAY)
        self.assertEqual(win["day"], 5)
        self.assertEqual(win["total"], 14)
        self.assertEqual(win["elapsed"], 5)
        self.assertFalse(win["ended"])
        self.assertEqual(win["progressPct"], 36)  # round(5/14*100)=36
        self.assertEqual(win["daysLeft"], 9)       # 오늘 제외 남은 일수
        self.assertEqual(win["endDate"], "2026-11-14")

    def test_시작_전과_종료_후(self):
        before = self.d.call("challengeWindow", make_config(), "2026-10-28")
        self.assertEqual(before["day"], 0)
        self.assertEqual(before["elapsed"], 0)
        self.assertFalse(before["started"])
        after = self.d.call("challengeWindow", make_config(), "2026-11-20")
        self.assertTrue(after["ended"])
        self.assertEqual(after["elapsed"], 14)
        self.assertEqual(after["daysLeft"], 0)

    def test_경과일_달성률(self):
        # DAY 5: 4일 완전(8칸) + 오늘 1칸 = 9 / 10 = 90%
        rows = {
            "m1": {
                "2026-11-01": ["ms1", "ms2"],
                "2026-11-02": ["ms1", "ms2"],
                "2026-11-03": ["ms1", "ms2"],
                "2026-11-04": ["ms1", "ms2"],
                "2026-11-05": ["ms1"],
            },
            "m2": {"2026-11-05": ["ms2"]},
        }
        state = self.build(rows)
        self.assertEqual(self.d.call("memberProgressRate", state["config"], state, "m1", TODAY), 90)
        self.assertEqual(self.d.call("memberProgressRate", state["config"], state, "m2", TODAY), 10)

    def test_오늘_3그룹_분류(self):
        rows = {
            "m1": {"2026-11-05": ["ms1", "ms2"]},
            "m2": {"2026-11-05": ["ms1"]},
            "m3": {},
        }
        state = self.build(rows)
        groups = self.d.call("todayGroups", state["config"], state, TODAY)
        self.assertEqual([x["id"] for x in groups["allClear"]], ["m1"])
        self.assertEqual([x["id"] for x in groups["partial"]], ["m2"])
        self.assertEqual([x["id"] for x in groups["none"]], ["m3"])

    def test_완주_달성률은_전체_기간_기준(self):
        # 1~4일 완전(8칸) + 오늘 1칸 = 9칸 → 경과일 9/10 = 90%, 완주 9/28 = 32%
        rows = {"m1": {f"2026-11-0{d}": ["ms1", "ms2"] for d in range(1, 5)} | {"2026-11-05": ["ms1"]}}
        state = self.build(rows)
        self.assertEqual(self.d.call("memberProgressRate", state["config"], state, "m1", TODAY), 90)
        self.assertEqual(self.d.call("memberFinalRate", state["config"], state, "m1"), 32)

    def test_동적_미션_수도_올클리어_계산에_반영된다(self):
        third = {"id": "ms3", "icon": "🚶", "name": "만보 걷기", "desc": "", "short": "걷기"}
        cfg = make_config(missions=[MISSION_WATER, MISSION_BOOK, third])
        checkins = {f"m1|{TODAY}|ms1": {"at": 1}, f"m1|{TODAY}|ms2": {"at": 1}}
        state = make_state(config=cfg, claims=claimed("m1", TOKEN_A), checkins=checkins)
        status = self.d.call("memberDayStatus", state, "m1", TODAY)
        self.assertEqual(status["total"], 3)
        self.assertFalse(status["allClear"])

    def test_매트릭스_셀과_필터(self):
        rows = {"m1": {"2026-11-01": ["ms1"], "2026-11-05": ["ms1", "ms2"]}}
        state = self.build(rows)
        mx = self.d.call("matrix", state["config"], state, TODAY, "all")
        self.assertEqual(len(mx["days"]), 14)
        self.assertTrue(mx["days"][4]["isToday"])
        row = mx["rows"][0]
        self.assertEqual(row["memberId"], "m1")
        self.assertEqual([s["on"] for s in row["cells"][0]["stamps"]], [True, False])
        self.assertTrue(row["cells"][4]["allClear"])
        self.assertTrue(row["cells"][6]["isFuture"])  # 7일차는 미래
        water = self.d.call("matrix", state["config"], state, TODAY, "ms1")
        self.assertEqual([s["missionId"] for s in water["rows"][0]["cells"][4]["stamps"]], ["ms1"])


# ---------------------------------------------------------------- 관리 / 보안
class TestAdmin(Base):
    def test_핀_일치(self):
        self.assertTrue(self.d.call("checkPin", "1234", "1234"))

    def test_핀_불일치(self):
        self.assertFalse(self.d.call("checkPin", "1235", "1234"))
        self.assertFalse(self.d.call("checkPin", "", "1234"))

    def test_핀은_숫자_4자리만_허용(self):
        self.assertFalse(self.d.call("isValidPin", "123"))
        self.assertFalse(self.d.call("isValidPin", "12345"))
        self.assertFalse(self.d.call("isValidPin", "12a4"))
        self.assertTrue(self.d.call("isValidPin", "0000"))

    def test_관리_라우트_해시_판정(self):
        for h in ["#admin", "#/admin", "#ADMIN", "#admin/settings"]:
            self.assertTrue(self.d.call("isAdminRoute", h), h)
        for h in ["", "#", "#user", "#administration", "#foo-admin"]:
            self.assertFalse(self.d.call("isAdminRoute", h), h)

    def test_설정_위생화_중복과_공백_제거(self):
        draft = make_config(members=[
            {"id": "m1", "name": " 강은영 "},
            {"id": "", "name": "이지수"},
            {"id": "mX", "name": "이지수"},
            {"id": "", "name": "   "},
        ])
        res = self.d.call("sanitizeConfig", draft)
        self.assertTrue(res["ok"], res)
        members = res["config"]["members"]
        self.assertEqual([m["name"] for m in members], ["강은영", "이지수"])
        self.assertEqual(members[0]["id"], "m1")          # 기존 id 보존
        self.assertTrue(members[1]["id"])                  # 새 id 발급
        self.assertEqual(len({m["id"] for m in members}), 2)

    def test_설정_위생화_최소값과_범위(self):
        bad_date = self.d.call("sanitizeConfig", make_config(startDate="2026-13-40"))
        self.assertFalse(bad_date["ok"])
        clamped = self.d.call("sanitizeConfig", make_config(durationDays=120))
        self.assertEqual(clamped["config"]["durationDays"], 60)
        no_mission = self.d.call("sanitizeConfig", make_config(missions=[]))
        self.assertFalse(no_mission["ok"])
        bad_pin = self.d.call("sanitizeConfig", make_config(adminPin="999"))
        self.assertFalse(bad_pin["ok"])

    def test_멤버_텍스트_파싱(self):
        text = "강은영\n이지수\n\n 박민선 \n이지수\n"
        parsed = self.d.call("parseMembersText", text, MEMBERS[:1])
        self.assertEqual([m["name"] for m in parsed], ["강은영", "이지수", "박민선"])


class TestKakaoMessage(Base):
    def setUp(self):
        checkins = {}
        for member, missions in {"m1": ["ms1", "ms2"], "m2": ["ms2"]}.items():
            for mission in missions:
                checkins[f"{member}|{TODAY}|{mission}"] = {"at": 1}
        self.state = make_state(
            claims={m: {"token": TOKEN_A, "claimedAt": 1} for m in ["m1", "m2", "m3"]},
            checkins=checkins,
        )

    def test_오늘_현황_문구(self):
        msg = self.d.call("kakaoMessage", self.state["config"], self.state, TODAY, "today", "https://example.com/")
        self.assertIn("DAY 5", msg)
        self.assertIn("은영", msg)      # 3자 한글은 성 제외
        self.assertIn("지수", msg)
        self.assertIn("민선", msg)
        self.assertIn("https://example.com/", msg)
        self.assertIn("📖", msg)   # 부분 달성자는 미션 아이콘 표기

    def test_독려_문구는_미참여자만_나열(self):
        msg = self.d.call("kakaoMessage", self.state["config"], self.state, TODAY, "nudge", "https://example.com/")
        self.assertIn("민선", msg)      # 성 제외 표기 (SPEC §4.5)
        self.assertNotIn("은영", msg)

    def test_완주_문구(self):
        msg = self.d.call("kakaoMessage", self.state["config"], self.state, TODAY, "final", "https://example.com/")
        self.assertIn("최종", msg)
        self.assertIn("은영", msg)


if __name__ == "__main__":
    unittest.main()
