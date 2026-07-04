from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
TESTS = APP / "tests"

SCENARIO_HASHES = {
    "peds_ward_allergy_academy_initial.json": (
        "ea4b0602126b2d9d93c4a9eb56b7bf95d4b52b6caea3d67acc0b372687adebee"
    ),
    "peds_ward_allergy_academy_variant.json": (
        "694d19aa42be2ca3151bf730d9eb9836031e4adc578a4a7359948c68b1b4e475"
    ),
    "peds_ward_anaphylaxis_iv_initial.json": (
        "6d181f88c8b6c3820927c58e98faa8464d8ac89501e0f67f4c5b108b511c7113"
    ),
    "peds_ward_anaphylaxis_iv_variantA.json": (
        "add6094c640b995958c213ae179b3424797e6434cd0fa676a91230c5643b402d"
    ),
}
GOLDEN_HASH = "034a984dd39aa0e596bada899dad14b2ee109ce362d5fcd42b461be75f359cd6"


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_files() -> list[Path]:
    return sorted(
        path
        for path in TESTS.iterdir()
        if path.is_file()
        and (
            path.name.endswith("_tests.py")
            or path.name == "full_workflow_validation.py"
        )
    )


def parse_test_count(output: str, filename: str) -> int:
    matches = re.findall(r"Ran\s+(\d+)\s+tests?", output)
    if matches:
        return int(matches[-1])
    if filename == "smoke_tests.py":
        return len(re.findall(r"^PASS\s+", output, flags=re.MULTILINE))
    return 0


def parse_failure_names(output: str) -> list[str]:
    names = []
    for pattern in (
        r"^(?:FAIL|ERROR):\s+([^\r\n]+)",
        r"^FAILED\s+([^\r\n]+)",
    ):
        names.extend(re.findall(pattern, output, flags=re.MULTILINE))
    return list(dict.fromkeys(names))


def run_all_tests() -> tuple[int, int, list[str]]:
    total = 0
    passed = 0
    failures: list[str] = []
    print("\n[自动化测试]")
    with tempfile.TemporaryDirectory(
        prefix="competition-candidate-verify-",
        dir=ROOT,
    ) as temporary:
        temporary_path = Path(temporary)
        environment = os.environ.copy()
        environment.update(
            {
                "PEDSIM_AUTOMATED_TEST": "1",
                "PEDSIM_RESULTS_DIR": str(temporary_path / "production"),
                "PEDSIM_DRAFTS_DIR": str(temporary_path / "drafts"),
                "PEDSIM_COMPETITION_RESULTS_DIR": str(
                    temporary_path / "competition"
                ),
            }
        )
        for path in test_files():
            result = run([sys.executable, str(path)], env=environment)
            combined = "\n".join((result.stdout, result.stderr))
            count = parse_test_count(combined, path.name)
            total += count
            if result.returncode == 0:
                passed += count
                print(f"PASS {path.name}: {count}")
            else:
                names = parse_failure_names(combined)
                failures.extend(names or [path.name])
                print(f"FAIL {path.name}: {count}")
                print(combined[-4000:])
    return total, passed, failures


def verify_hashes() -> list[str]:
    failures = []
    scenario_dir = APP / "peds_anaphylaxis_sim" / "scenarios"
    print("\n[情景与黄金快照]")
    for filename, expected in SCENARIO_HASHES.items():
        actual = sha256(scenario_dir / filename)
        status = "PASS" if actual == expected else "FAIL"
        print(f"{status} {filename}: {actual}")
        if actual != expected:
            failures.append(f"scenario hash: {filename}")
    golden = TESTS / "golden" / "v1_3_8_behavior_baseline.json"
    actual_golden = sha256(golden)
    status = "PASS" if actual_golden == GOLDEN_HASH else "FAIL"
    print(f"{status} golden snapshot: {actual_golden}")
    if actual_golden != GOLDEN_HASH:
        failures.append("golden snapshot hash")
    return failures


def candidate_scan_files() -> Iterable[Path]:
    roots = (APP, ROOT / "docs")
    excluded_parts = {
        ".runtime",
        "runs_web",
        "competition_runtime",
        "__pycache__",
    }
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if (
                path.is_file()
                and path.name != "secrets.toml"
                and not excluded_parts.intersection(path.parts)
                and path.suffix.lower()
                in {".py", ".md", ".toml", ".json", ".jsonl", ".txt"}
            ):
                yield path


def sensitive_scan() -> list[str]:
    failures = []
    supabase = re.compile(r"https://[a-z0-9-]+\.supabase\.co", re.IGNORECASE)
    email = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
    phone = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    secret_assignment = re.compile(
        r"(?im)^(APP_ACCESS_CODE|ADMIN_PASSWORD|COMPETITION_REVIEW_CODE|"
        r"COMPETITION_ADMIN_CODE|AUTH_CONTEXT_SIGNING_KEY|SUPABASE_(?:URL|KEY|"
        r"ANON_KEY|SERVICE_ROLE_KEY))\s*=\s*[\"']([^\"']+)[\"']\s*$"
    )
    print("\n[敏感信息扫描]")
    for path in candidate_scan_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(ROOT)
        for label, pattern in (
            ("Supabase地址", supabase),
            ("邮箱", email),
            ("手机号", phone),
        ):
            if pattern.search(text):
                failures.append(f"{label}: {relative}")
        for match in secret_assignment.finditer(text):
            value = match.group(2).strip()
            if value and value.lower() not in {
                "production",
                "training_records",
            } and not value.startswith("<"):
                failures.append(f"凭据赋值: {relative}:{match.group(1)}")

    tracked_secret = run(
        ["git", "ls-files", "--error-unmatch", "app/.streamlit/secrets.toml"]
    )
    if tracked_secret.returncode == 0:
        failures.append("app/.streamlit/secrets.toml is tracked")
    else:
        print("PASS secrets.toml 未被Git跟踪")

    example = APP / ".streamlit" / "secrets.example.toml"
    example_text = example.read_text(encoding="utf-8")
    if secret_assignment.search(example_text):
        failures.append("secrets.example.toml contains a non-empty sensitive value")
    else:
        print("PASS secrets.example.toml 使用空值或安全非敏感配置")

    if not failures:
        print("PASS 未发现真实凭据、Supabase地址、邮箱或手机号")
    return failures


def repository_info() -> tuple[str, str, str]:
    branch = run(["git", "branch", "--show-current"]).stdout.strip()
    remote = run(["git", "remote", "get-url", "origin"]).stdout.strip()
    status = run(["git", "status", "--short"]).stdout.rstrip()
    print("[仓库]")
    print(f"目录: {ROOT}")
    print(f"分支: {branch}")
    print(f"远程: {remote}")
    print("git status --short:")
    print(status or "(clean)")
    return branch, remote, status


def main() -> int:
    branch, remote, _ = repository_info()
    failures: list[str] = []
    if branch != "feature/competition-review-mode":
        failures.append(f"unexpected branch: {branch}")
    if remote.rstrip("/") != "https://github.com/gundamexia028/virtual-engine.git":
        failures.append(f"unexpected remote: {remote}")

    total, passed, test_failures = run_all_tests()
    failures.extend(test_failures)
    failures.extend(verify_hashes())
    failures.extend(sensitive_scan())

    print("\n[候选版汇总]")
    print(f"测试总数: {total}")
    print(f"通过数: {passed}")
    print(f"失败数: {total - passed if test_failures else 0}")
    if failures:
        print("失败项目:")
        for item in failures:
            print(f"- {item}")
        print("验证结论: 未通过")
        return 1
    print("失败测试名称: 无")
    print("competition隔离、production回归、12条黄金路径和敏感信息检查均通过。")
    print("验证结论: 通过；脚本未执行git add、commit或push。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
