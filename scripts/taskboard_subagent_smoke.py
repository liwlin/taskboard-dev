#!/usr/bin/env python3
"""Smoke-test T0 native-subagent fallback dispatch bookkeeping."""

from argparse import ArgumentParser
from pathlib import Path
import json
import shutil
import sys
import tempfile
from typing import Optional

from taskboard_loop import build_subagent_fallback, write_subagent_fallback_packet
from taskboard_subagents import (
    subagent_ack_payload,
    subagent_next_payload,
    subagent_result_payload,
    subagent_retry_payload,
    subagent_status_payload,
)
from taskboard_t0 import dispatch


GOAL = "Ship a demo feature through T0-managed native subagent fallback."


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def prepare_root(root: Path, force: bool) -> None:
    docs = root / "docs"
    if docs.exists() and not force:
        raise RuntimeError(f"{docs} already exists; pass --force or choose an empty smoke root")
    if docs.exists():
        shutil.rmtree(docs)
    (docs / "taskboard").mkdir(parents=True, exist_ok=True)


def dispatch_role(root: Path, role: str, agent_id: str, summary: str) -> dict[str, object]:
    next_item = subagent_next_payload(root)
    require(next_item.get("state") == "pending", f"expected pending subagent role before {role}")
    require(next_item.get("role") == role, f"expected next subagent role {role}, got {next_item.get('role')}")
    ack = subagent_ack_payload(root, role, agent_id, f"subagent smoke dispatched {role}")
    done = subagent_result_payload(root, role, "completed", summary)
    return {
        "next": {
            "state": next_item.get("state"),
            "role": next_item.get("role"),
            "dispatch_order": next_item.get("dispatch_order"),
        },
        "ack": {
            "role": ack["record"].get("role"),
            "agent_id": ack["record"].get("agent_id"),
            "status": ack["record"].get("status"),
        },
        "done": {
            "role": done["record"].get("role"),
            "status": done["record"].get("status"),
            "summary": done["record"].get("summary"),
        },
    }


def run_smoke(root: Path, goal: str, force: bool) -> dict[str, object]:
    root = root.resolve()
    prepare_root(root, force)

    plan = dispatch(root, goal, "subagent", launcher="none")
    require(plan.get("state") == "dispatch", "T0 did not produce a dispatch plan")
    require(plan.get("mode") == "subagent", "T0 dispatch plan is not in subagent mode")
    require(plan.get("launch_commands") == [], "subagent mode must not emit launcher commands")
    prompts = plan.get("subagent_prompts", [])
    require(isinstance(prompts, list) and len(prompts) == 3, "T0 did not produce three subagent prompts")

    fallback = build_subagent_fallback(plan, [], "subagent-smoke")
    packet = write_subagent_fallback_packet(root, goal, fallback)
    require(packet.get("prompt_count") == 3, "subagent fallback packet did not record three prompts")

    initial = subagent_status_payload(root)
    require(initial.get("pending_roles") == ["T1", "T2", "T3"], "initial subagent pending roles mismatch")

    t1 = dispatch_role(root, "T1", "smoke-agent-t1", "T1 created TASK files")

    next_t2 = subagent_next_payload(root)
    require(next_t2.get("role") == "T2", "T2 should be next after T1 completion")
    t2_ack = subagent_ack_payload(root, "T2", "smoke-agent-t2a", "subagent smoke dispatched T2")
    t2_fail = subagent_result_payload(root, "T2", "failed", "review tool timed out")
    retry = subagent_retry_payload(root, "T2", "retry review after timeout")
    retry_next = subagent_next_payload(root)
    require(retry_next.get("role") == "T2", "retry should return T2 to the front of pending roles")
    t2_retry_ack = subagent_ack_payload(root, "T2", "smoke-agent-t2b", "subagent smoke retried T2")
    t2_done = subagent_result_payload(root, "T2", "completed", "T2 approved retry result")

    t3 = dispatch_role(root, "T3", "smoke-agent-t3", "T3 completed implementation slice")

    final_status = subagent_status_payload(root)
    final_next = subagent_next_payload(root)
    require(final_status.get("pending_roles") == [], "subagent pending roles should be empty")
    require(final_status.get("active_roles") == [], "subagent active roles should be empty")
    require(final_status.get("failed_roles") == [], "subagent failed roles should be empty after retry")
    require(final_status.get("completed_roles") == ["T1", "T2", "T3"], "completed subagent roles mismatch")
    require(final_next.get("state") == "complete", "subagent next should report complete")

    t2_record = final_status["records"]["T2"]
    attempts = t2_record.get("attempts", []) if isinstance(t2_record, dict) else []
    require(isinstance(attempts, list) and len(attempts) == 1, "T2 retry attempt history missing")

    return {
        "kind": "taskboard-subagent-smoke",
        "state": "passed",
        "root": str(root),
        "goal": goal,
        "plan": {
            "state": plan.get("state"),
            "mode": plan.get("mode"),
            "command": plan.get("command"),
            "launch_command_count": len(plan.get("launch_commands", [])),
            "subagent_prompt_roles": [item.get("role") for item in prompts if isinstance(item, dict)],
        },
        "packet": packet,
        "initial": {
            "pending_roles": initial.get("pending_roles"),
            "completed_roles": initial.get("completed_roles"),
        },
        "dispatches": {
            "T1": t1,
            "T2": {
                "first_ack": {
                    "role": t2_ack["record"].get("role"),
                    "agent_id": t2_ack["record"].get("agent_id"),
                    "status": t2_ack["record"].get("status"),
                },
                "failure": {
                    "status": t2_fail["record"].get("status"),
                    "summary": t2_fail["record"].get("summary"),
                },
                "retry": {
                    "status": retry["record"].get("status"),
                    "attempt_count": len(retry["record"].get("attempts", [])),
                },
                "retry_next_role": retry_next.get("role"),
                "retry_ack": {
                    "role": t2_retry_ack["record"].get("role"),
                    "agent_id": t2_retry_ack["record"].get("agent_id"),
                    "status": t2_retry_ack["record"].get("status"),
                },
                "done": {
                    "status": t2_done["record"].get("status"),
                    "summary": t2_done["record"].get("summary"),
                },
            },
            "T3": t3,
        },
        "final": {
            "pending_roles": final_status.get("pending_roles"),
            "active_roles": final_status.get("active_roles"),
            "completed_roles": final_status.get("completed_roles"),
            "failed_roles": final_status.get("failed_roles"),
            "next_state": final_next.get("state"),
        },
        "evidence": [
            "T0 generated isolated native-subagent prompts without launcher commands",
            "T0 persisted a reusable subagent fallback packet",
            "T0 subagent next/ack/done advanced T1",
            "T0 subagent fail/retry preserved the failed T2 attempt and requeued T2",
            "T0 subagent next reached complete after T1/T2/T3 completed",
        ],
    }


def format_text(payload: dict[str, object]) -> str:
    plan = payload["plan"]
    final = payload["final"]
    return "\n".join(
        [
            f"state={payload['state']}",
            f"root={payload['root']}",
            f"plan_mode={plan['mode']} launch_command_count={plan['launch_command_count']}",
            f"subagent_prompt_roles={','.join(plan['subagent_prompt_roles'])}",
            f"completed_roles={','.join(final['completed_roles'])}",
            f"failed_roles={','.join(final['failed_roles'])}",
            f"next_state={final['next_state']}",
        ]
    )


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Smoke root. Defaults to a temporary directory.")
    parser.add_argument("--goal", default=GOAL)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing docs/ under --root.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.root:
        payload = run_smoke(Path(args.root), args.goal, args.force)
    else:
        with tempfile.TemporaryDirectory(prefix="taskboard-subagent-smoke-") as tmp:
            payload = run_smoke(Path(tmp), args.goal, force=True)
            payload["root"] = "<temporary root removed>"
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
