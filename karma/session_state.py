"""跨 hook 共享的 session 状态 — Read 历史 / Bash 测试结果 / Edit 累积。

post_tool_use 写入，pre_tool_use / post_response 读取。
存到 ~/.claude/karma/session-state/{session_id}.json。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DIR = Path.home() / ".claude" / "karma" / "session-state"
MAX_RECENT_BASH = 15  # 保留最近 N 条 Bash 摘要

# Claude Code 真实 background tool_response 是 dict {stdout, stderr, backgroundTaskId, ...}
# 老 marker regex（扫字面 "Command running in background..."）只在文档/示例字面里出现，
# 真实 hook payload 用不上。改成从 dict 提取 backgroundTaskId + 从 command 解析 > 重定向。

# shell stdout 重定向 — `cmd > /path` / `cmd >> /path` 提取目标
# 要求 `>` 前是开头或空白，避开 `2>` `3>` fd 重定向；后面是路径字符
_REDIRECT_RE = re.compile(r"(?:^|\s)>{1,2}\s*([/.\w][^\s|;&]*)")


def _parse_redirect_target(command: str) -> str | None:
    """从 shell 命令解析最后一个 stdout 重定向路径。

    `cmd > /tmp/x.log 2>&1` → /tmp/x.log
    没重定向返回 None。
    """
    matches = _REDIRECT_RE.findall(command)
    paths = [m for m in matches if not m.startswith("&")]
    return paths[-1] if paths else None

# 测试通过信号 — 出现 N passed / all green / 全绿勾
_PASS_RE = re.compile(
    r"\b\d+\s+passed\b|\ball\s+tests?\s+pass(?:ed)?\b|\ball\s+green\b|✓",
    re.IGNORECASE,
)

# 测试失败信号 — 精确匹配（不要单独的 'error' / 'traceback' 子串，假阳性高）
# - "N failed" (N>=0) pytest 风格计数
# - "FAILED test_x" pytest 单测失败行（行首或空白后）
# - "FAILURES" 章节标题
# - "Traceback (most recent call last)" 真 Python traceback
# - AssertionError / RuntimeError / ImportError 等明确失败异常
# - 行首 "ERROR:" / "FATAL:" 前缀（go test / cargo / 自家测试常见）
# - "N error(s)" 计数 N>=1（明确区分 "0 errors"）
_FAIL_RE = re.compile(
    r"\b\d+\s+failed\b"
    r"|(?:^|\n)FAILED\s"
    r"|\bFAILURES?\b"
    r"|Traceback\s*\(most\s+recent\s+call\s+last\)"
    r"|\b(?:AssertionError|RuntimeError|ImportError)\b"
    r"|(?:^|\n)\s*(?:ERROR|FATAL)\s*:"
    r"|\b[1-9]\d*\s+errors?\b",
    re.IGNORECASE | re.MULTILINE,
)

_TEST_CMD_RE = re.compile(
    r"\b(pytest|jest|cargo test|go test|npm test|tox|mocha|vitest|rspec|phpunit)\b",
    re.IGNORECASE,
)


@dataclass
class BashSnapshot:
    """单次 Bash 调用的摘要 — 只记关键信号，不存全文。"""

    ts: float
    command_summary: str  # command 前 100 字
    is_test_cmd: bool      # 命令是否含 pytest/jest 等测试 runner
    output_passed: bool    # 输出含 PASS 信号
    output_failed: bool    # 输出含 FAIL 信号


@dataclass
class SessionState:
    session_id: str
    read_files: set[str] = field(default_factory=set)         # 本 session Read 过的 file_path
    edit_files: list[str] = field(default_factory=list)        # Edit/Write 顺序记录（重复也保留）
    recent_bash: list[BashSnapshot] = field(default_factory=list)
    last_test_pass_ts: float = 0.0   # 最近一次测试通过的时间戳（0 = 从未通过）
    last_edit_ts: float = 0.0        # 最近一次代码 Edit/Write 的时间戳（0 = 本 session 未改代码）
    # background 任务 pending list — 启动时无真实输出，等下次 hook 触发 catchup 读 output file
    pending_bg_tasks: list[dict] = field(default_factory=list)

    def has_read(self, file_path: str) -> bool:
        return file_path in self.read_files

    def has_recent_test_pass(self) -> bool:
        """本 session 是否「自最近一次代码改动以来跑过测试且通过」。

        语义：last_test_pass_ts >= last_edit_ts（含相等防同时刻边界）。
        从未测试通过 → False。代码改了之后没重测 → False。
        """
        if self.last_test_pass_ts <= 0:
            return False
        return self.last_test_pass_ts >= self.last_edit_ts

    def record_read(self, file_path: str) -> None:
        if file_path:
            self.read_files.add(file_path)

    def _next_ts(self) -> float:
        """生成严格大于已有 last_*_ts 的时间戳。

        time.time() 在同微秒连续调用会返回相同值，无法区分先后；
        强制比已记录的最大 ts 大 1 微秒，保证 has_recent_test_pass 顺序判定正确。
        """
        ts = time.time()
        floor = max(self.last_test_pass_ts, self.last_edit_ts)
        if ts <= floor:
            ts = floor + 1e-6
        return ts

    def record_edit(self, file_path: str) -> None:
        if file_path:
            self.edit_files.append(file_path)
            self.last_edit_ts = self._next_ts()

    def record_bash(self, command: str, output, run_in_background: bool = False) -> None:
        if not command:
            return
        is_test = bool(_TEST_CMD_RE.search(command))

        # Claude Code 真实 tool_response 是 dict {stdout, stderr, backgroundTaskId, ...}
        # 老协议 / 同步直传 string 也要兼容
        if isinstance(output, dict):
            stdout = str(output.get("stdout", "") or "")
            stderr = str(output.get("stderr", "") or "")
            out_str = stdout if not stderr else (stdout + "\n" + stderr)
        else:
            out_str = str(output or "")

        # background 任务启动 — stdout/stderr 是空的，真实输出在用户重定向文件
        # 推 pending 等 catchup 读重定向目标文件
        if run_in_background:
            redirect_target = _parse_redirect_target(command)
            if redirect_target:
                self.pending_bg_tasks.append({
                    "cmd": command[:200],
                    "output_file": redirect_target,
                    "started_ts": time.time(),
                })
                self.recent_bash.append(BashSnapshot(
                    ts=time.time(),
                    command_summary=command[:100],
                    is_test_cmd=is_test,
                    output_passed=False,
                    output_failed=False,
                ))
                self.recent_bash = self.recent_bash[-MAX_RECENT_BASH:]
                return

        passed = bool(_PASS_RE.search(out_str))
        failed = bool(_FAIL_RE.search(out_str))
        self.recent_bash.append(BashSnapshot(
            ts=time.time(),
            command_summary=command[:100],
            is_test_cmd=is_test,
            output_passed=passed,
            output_failed=failed,
        ))
        # 测试通过 → 推进 last_test_pass_ts（严格大于 last_edit_ts，分清先后）
        if is_test and passed and not failed:
            self.last_test_pass_ts = self._next_ts()
        # 保留最近 N 条
        self.recent_bash = self.recent_bash[-MAX_RECENT_BASH:]

    def catchup_pending_bg(self) -> int:
        """扫 pending_bg_tasks — 文件存在且非空就读取并 record_bash。

        返回成功 catch-up 的任务数。文件还没出现的保留在 pending。
        """
        if not self.pending_bg_tasks:
            return 0
        caught_up = 0
        still_pending: list[dict] = []
        for task in self.pending_bg_tasks:
            output_file = task.get("output_file", "")
            cmd = task.get("cmd", "")
            if not output_file:
                continue
            try:
                p = Path(output_file)
                if not p.exists() or p.stat().st_size == 0:
                    still_pending.append(task)
                    continue
                output = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                still_pending.append(task)
                continue
            # 用普通 record_bash 路径处理（已读到真实输出，不会再命中 bg marker）
            self.record_bash(cmd, output)
            caught_up += 1
        self.pending_bg_tasks = still_pending
        return caught_up


def _state_path(session_id: str, base_dir: Path | None = None) -> Path:
    base = base_dir or DEFAULT_DIR
    # session_id 可能含 /，简单清洗成单文件名
    safe_id = re.sub(r"[^\w.-]", "_", session_id) or "default"
    return base / f"{safe_id}.json"


def load(session_id: str, base_dir: Path | None = None) -> SessionState:
    """加载 session 状态。文件不存在 → 返回空 state。"""
    p = _state_path(session_id, base_dir)
    if not p.exists():
        return SessionState(session_id=session_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return SessionState(session_id=session_id)
    state = SessionState(
        session_id=session_id,
        read_files=set(d.get("read_files", [])),
        edit_files=list(d.get("edit_files", [])),
        recent_bash=[
            BashSnapshot(
                ts=float(b.get("ts", 0)),
                command_summary=b.get("command_summary", ""),
                is_test_cmd=bool(b.get("is_test_cmd", False)),
                output_passed=bool(b.get("output_passed", False)),
                output_failed=bool(b.get("output_failed", False)),
            )
            for b in d.get("recent_bash", [])
        ],
        last_test_pass_ts=float(d.get("last_test_pass_ts", 0.0) or 0.0),
        last_edit_ts=float(d.get("last_edit_ts", 0.0) or 0.0),
        pending_bg_tasks=list(d.get("pending_bg_tasks", []) or []),
    )
    return state


def save(state: SessionState, base_dir: Path | None = None) -> None:
    """保存 session 状态（atomic rewrite）。"""
    p = _state_path(state.session_id, base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": state.session_id,
        "read_files": sorted(state.read_files),
        "edit_files": state.edit_files,
        "recent_bash": [
            {
                "ts": b.ts,
                "command_summary": b.command_summary,
                "is_test_cmd": b.is_test_cmd,
                "output_passed": b.output_passed,
                "output_failed": b.output_failed,
            }
            for b in state.recent_bash
        ],
        "last_test_pass_ts": state.last_test_pass_ts,
        "last_edit_ts": state.last_edit_ts,
        "pending_bg_tasks": state.pending_bg_tasks,
    }
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    import os
    os.replace(tmp, p)
