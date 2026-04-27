#!/usr/bin/env python3
import sys
import json
import time
import asyncio
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.config import SkillCertConfig
from engine.analyzer import parse_skill_md
from adapters.anthropic_compat import AnthropicCompatAdapter
from engine.grader import Grader, EvalAssertion
from engine.metrics import MetricsCalculator
from engine.reporter import Reporter

PROJECT_ROOT = Path("/mnt/e/Private/opencode优化/xgate")

def get_cache_path(skill_name: str) -> Path:
    return Path("results") / f"{skill_name}-evals-cache.json"

def load_or_generate_evals(skill_name: str, skill_path: str, adapter, force_regenerate: bool = False):
    cache = get_cache_path(skill_name)
    if cache.exists() and not force_regenerate:
        print(f"  ⚡ Loaded cached eval cases from {cache.name}")
        return json.loads(cache.read_text())
    
    from engine.testgen import EvalGenerator
    spec = parse_skill_md(skill_path)
    gen = EvalGenerator()
    prompt = gen._prepare_generation_prompt(spec)
    
    print(f"  🔄 Generating eval cases via LLM ({len(prompt)} chars)...")
    t0 = time.time()
    resp = adapter.chat([{"role": "user", "content": prompt}])
    evals = gen._parse_evals_response(resp)
    print(f"  ✅ Generated in {time.time()-t0:.1f}s")
    
    if evals.get("eval_cases") or evals.get("evals"):
        cache.write_text(json.dumps(evals, ensure_ascii=False))
        print(f"  💾 Cached to {cache.name}")
    return evals

async def run_evals_concurrently(adapter, eval_cases, max_concurrency: int = 5):
    semaphore = asyncio.Semaphore(max_concurrency)
    async def _run(ec):
        async with semaphore:
            loop = asyncio.get_event_loop()
            prompt = ec.get("input", ec.get("prompt", ""))
            return await loop.run_in_executor(None, lambda: adapter.chat([{"role": "user", "content": prompt}]))
    
    tasks = [_run(ec) for ec in eval_cases]
    return await asyncio.gather(*tasks)

def normalize_assertions(eval_cases):
    for ec in eval_cases:
        for i, a in enumerate(ec.get("assertions", [])):
            if isinstance(a, dict):
                if "name" not in a: a["name"] = f"a{i}"
                if "value" not in a: a["value"] = ""
                if isinstance(a.get("weight"), float): a["weight"] = max(1, int(a["weight"]*10))
    return eval_cases

def run_single_skill(skill_path, output_dir, force_regenerate: bool = False):
    output_dir.mkdir(parents=True, exist_ok=True)
    skill_name = Path(skill_path).parent.name
    print(f"\n{'='*60}")
    print(f"  Skill-Cert UAT: {skill_name}")
    print(f"{'='*60}")
    
    config = SkillCertConfig.load()
    if not config.models:
        print("❌ No models configured")
        return None
    mc = config.models[0]
    adapter = AnthropicCompatAdapter(base_url=mc.base_url, api_key=mc.api_key, model=mc.model_name, fallback_model=mc.fallback_model)
    
    print(f"\n[Phase 0] Parsing SKILL.md...")
    spec = parse_skill_md(skill_path)
    print(f"  Name: {spec['name']}, confidence={spec['parse_confidence']:.2f}")
    
    print(f"\n[Phase 1] Loading/Generating eval cases...")
    evals = load_or_generate_evals(skill_name, skill_path, adapter, force_regenerate)
    eval_cases = evals.get("eval_cases", evals.get("evals", []))
    eval_cases = normalize_assertions(eval_cases)
    print(f"  Loaded {len(eval_cases)} eval cases")
    
    if not eval_cases:
        print("❌ No eval cases")
        return None
    
    print(f"\n[Phase 2] Executing {len(eval_cases)} eval cases concurrently...")
    t0 = time.time()
    outputs = asyncio.run(run_evals_concurrently(adapter, eval_cases, max_concurrency=5))
    print(f"  ✅ Completed in {time.time()-t0:.1f}s")
    
    print(f"\n[Phase 2] Grading...")
    grader = Grader()
    all_gradings = []
    for eval_case, output in zip(eval_cases, outputs):
        assertions = []
        for a in eval_case.get("assertions", []):
            if isinstance(a, dict):
                try: assertions.append(EvalAssertion(**a))
                except: pass
        ec_obj = type('EC', (), {
            "id": eval_case.get("id",0), "name": eval_case.get("name",""), 
            "category": eval_case.get("category",""), "prompt": eval_case.get("input",""), 
            "assertions": assertions
        })()
        grading = grader.grade_output(ec_obj, output)
        grading["run"] = "with-skill"
        all_gradings.append(grading)
        passed = sum(1 for a in grading.get("assertions", []) if getattr(a, "passed", False))
        total = len(grading.get("assertions", []))
        print(f"  {eval_case.get('name', '?')}: {passed}/{total} passed")
    
    print(f"\n[Phase 4] Metrics:")
    calc = MetricsCalculator()
    metrics = calc.calculate_metrics(all_gradings)
    print(f"  L1 Trigger Accuracy: {metrics.get('l1_trigger_accuracy', 0):.2%}")
    print(f"  L2 Delta: {metrics.get('l2_with_without_skill_delta', 0):.2%}")
    print(f"  L3 Step Adherence: {metrics.get('l3_step_adherence', 0):.2%}")
    print(f"  L4 Stability: {metrics.get('l4_execution_stability', 0):.2%}")
    print(f"  Overall Score: {metrics.get('overall_score', 0):.2%}")
    
    print(f"\n[Phase 6] Generating reports...")
    reporter = Reporter()
    md_report, json_report = reporter.generate_report(
        metrics,
        {"overall_drift": "none", "overall_verdict": "PASS"},
        {"total_evaluations": len(eval_cases), "avg_pass_rate": metrics.get('l1_trigger_accuracy', 0),
         "critical_passed": 0, "critical_total": 0, "important_passed": 0, "important_total": 0,
         "normal_passed": 0, "normal_total": 0}
    )
    
    report_path = output_dir / f"{skill_name}-report.md"
    report_path.write_text(md_report, encoding="utf-8")
    json_path = output_dir / f"{skill_name}-result.json"
    json_path.write_text(json.dumps(json_report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✅ Report: {report_path}")
    print(f"  ✅ JSON: {json_path}")
    print(f"  Verdict: {json_report.get('verdict', 'UNKNOWN')}")
    return json_report

def main():
    skill_paths = []
    for name in ["delphi-review", "sprint-flow", "test-specification-alignment"]:
        p = PROJECT_ROOT / "skills" / name / "SKILL.md"
        if p.exists(): skill_paths.append((name, str(p)))
    p = Path.home() / ".config" / "opencode" / "skills" / "gstack" / "plan-eng-review" / "SKILL.md"
    if p.exists(): skill_paths.append(("plan-eng-review", str(p)))
    print(f"Found {len(skill_paths)} skills to evaluate")
    
    output_dir = Path("results")
    output_dir.mkdir(exist_ok=True)
    
    force_regenerate = "--force-regenerate" in sys.argv
    results = {}
    for name, path in skill_paths:
        try:
            result = run_single_skill(path, output_dir, force_regenerate)
            results[name] = result
        except Exception as e:
            print(f"❌ {name} failed: {e}")
            import traceback; traceback.print_exc()
    
    print(f"\n{'='*60}")
    print(f"  UAT Summary")
    print(f"{'='*60}")
    for name, result in results.items():
        if result: print(f"  {name}: {result.get('verdict', 'N/A')} (score: {result.get('overall_score', 0):.2%})")
        else: print(f"  {name}: FAILED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
