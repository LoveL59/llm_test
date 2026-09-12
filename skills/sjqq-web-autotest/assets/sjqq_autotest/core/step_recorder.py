"""步骤记录器：让自动化「每一步」对人工可见、可验证。

为什么需要它
------------
非自动化人员（业务/产品）没有代码能力，但需要：
  1) 观看自动化执行过程（看到浏览器里每一步在做什么）；
  2) 确认每一步确实“有效”（而不是脚本跑完了但页面没变化）。

StepRecorder 在每一个操作步（对应 S/G/W/T 用例里的 W 步骤）完成后：
  1. 在控制台打印步骤编号 + 中文描述；
  2. 同时写入 reports/evidence/<case_id>/steps.log（持久化的可读执行轨迹）；
  3. 保存一张证据截图到同一目录，作为可视化留痕；
  4. 可选地执行一段「有效性校验」回调，打印 ✅有效 / ❌无效，便于人工核对；
  5. 把上述信息（含截图文件名、有效性）另写一份结构化 steps.json，
     供「优化报告」直接读取并内嵌截图，免去脆弱的文本解析。

配合 conftest 里的「有头浏览器 + slow_mo」，业务人员即可在屏幕上实时看到
每一步操作与结果；即便不看屏幕，也能通过 steps.log + 截图逐项核验有效性。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from core.paths import EVIDENCE_DIR


def _slug(text: str) -> str:
    """把中文/符号步骤文案转成安全的文件名片段。"""
    text = re.sub(r"[^\w一-鿿]+", "_", text).strip("_")
    return text[:28] or "step"


class StepRecorder:
    """逐步记录器：场景(S)/前提(G)/步骤(W)/预期(T) 全程可见、可核验。"""

    # 当前进程内活跃的记录器（按 case_id 索引），便于失败诊断在 teardown 时
    # 直接读取内存中的步骤有效性，避免依赖 steps.json 落地时序。
    _ACTIVE: dict[str, "StepRecorder"] = {}

    @classmethod
    def get_active(cls, case_id: str) -> "StepRecorder | None":
        return cls._ACTIVE.get(case_id)

    def __init__(self, page, case_id: str, case_title: str) -> None:
        self.page = page
        self.case_id = case_id
        self.case_title = case_title
        StepRecorder._ACTIVE[case_id] = self
        self.step_no = 0
        self.evidence_dir: Path = EVIDENCE_DIR / case_id
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        # 持久化的可读执行轨迹（每次运行覆盖重写）
        self.log_path: Path = self.evidence_dir / "steps.log"
        self._log_fh = self.log_path.open("w", encoding="utf-8")
        self._write(f"# 用例 {case_id}：{case_title} 执行轨迹")
        self._write(f"# 证据目录：{self.evidence_dir}\n")
        # 结构化步骤数据（供「优化报告」内嵌截图使用）
        self.steps: list[dict] = []
        self._flush_json()

    # -- 统一输出（控制台 + 文件）---------------------------------------
    def _write(self, line: str) -> None:
        try:
            self._log_fh.write(line + "\n")
            self._log_fh.flush()
        except Exception:  # noqa: BLE001
            pass
        print(line)

    # -- 用例头 ----------------------------------------------------------
    def scenario(self, text: str) -> None:
        self._write(f"\n{'=' * 66}\n📋 场景 (S): {text}\n{'=' * 66}")

    def given(self, text: str) -> None:
        self._write(f"🔧 前提条件 (G): {text}")

    # -- 步骤 (W) --------------------------------------------------------
    def when(self, text: str, *, do=None, verify=None, screenshot: bool = True, note=None):
        """记录一个操作步（W）。

        参数：
            text: 该步骤的中文描述（对应用例文档里的 W 步骤）。
            do:   执行该步动作的回调（如 lambda: home.search("微信")）；
                  不传则只记录（动作可能已在外部完成，如 fixture 已打开首页）。
            verify: 校验该步「是否有效」的回调，返回 bool；打印 ✅有效/❌无效。
            screenshot: 是否在步骤后保存证据截图（默认 True）。
            note: 该步的执行细节说明（如统计数据、异常信息），会被记入步骤日志
                  与 steps.json，并在优化报告中展示，便于排查失败原因。

        返回 verify 的结果（无 verify 时返回 None）。
        """
        self.step_no += 1
        self._write(f"\n▶ [W{self.step_no}] {text}")
        if do is not None:
            do()
        shot_file = None
        if screenshot:
            shot_name = f"W{self.step_no}_{_slug(text)}"
            self._shot(shot_name)
            shot_file = f"{shot_name}.png"
        ok = None
        if verify is not None:
            ok = bool(verify())
            self._write(f"   有效性校验: {'✅ 有效' if ok else '❌ 无效'}")
        if note:
            self._write(f"   📝 {note}")
        self.steps.append(
            {
                "kind": "W",
                "no": self.step_no,
                "text": text,
                "screenshot": shot_file,
                "effective": ok,
                "note": note,
            }
        )
        self._flush_json()
        return ok

    # -- 预期 (T) --------------------------------------------------------
    def then(self, text: str, *, verify=None):
        """记录一个预期结果（T），并执行断言（verify 不通过则用例失败）。

        参数：
            text: 预期结果的中文描述（对应用例文档里的 T 预期）。
            verify: 校验预期是否达成的回调，返回 bool；为空则仅打印预期文案。
        """
        self._write(f"\n✅ [T] 预期: {text}")
        ok = None
        if verify is not None:
            ok = bool(verify())
            assert ok, f"预期结果未满足: {text}"
            self._write("   结果: ✅ 通过")
        self.steps.append(
            {
                "kind": "T",
                "no": None,
                "text": text,
                "screenshot": None,
                "effective": ok,
            }
        )
        self._flush_json()
        return ok

    # -- 内部：截图 ------------------------------------------------------
    def _shot(self, name: str) -> Path:
        path = self.evidence_dir / f"{name}.png"
        try:
            self.page.screenshot(path=str(path), full_page=False)
            self._write(f"   📸 证据截图: {path.name}")
        except Exception as e:  # noqa: BLE001
            self._write(f"   [warn] 截图失败: {e}")
        return path

    def _flush_json(self) -> None:
        """把结构化步骤数据写入 steps.json，供「优化报告」内嵌截图使用。"""
        payload = {
            "case_id": self.case_id,
            "case_title": self.case_title,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "steps": self.steps,
        }
        try:
            (self.evidence_dir / "steps.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        """关闭日志文件（测试结束时调用）。"""
        try:
            self._log_fh.close()
        except Exception:  # noqa: BLE001
            pass
