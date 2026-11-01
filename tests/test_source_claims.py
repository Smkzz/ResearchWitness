"""RW-MATH-02 strict source-bound formalization and mathematical replay tests.

Only synthetic source texts. Historical A020 cases and protected scientific
corpora are not included or counted as new scientific evaluation evidence.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from researchwitness import exact_optimization as eo
from researchwitness import source_claims as sc
from tools import optimization_examples as examples
from tools import source_claim_workflow as workflow

BILINEAR = ("RW-MATH-BEGIN v1\ndomain: bounded_real\n"
            "variables: x[0,1]; y[0,1]; z[0,1]\n"
            "maximize: z\n"
            "constraints: x + y == 1; z == x*y\n"
            "upper_bound: 1/4\n"
            "RW-MATH-END\n").encode("ascii")
LINEAR = ("RW-MATH-BEGIN v1\ndomain: bounded_real\n"
          "variables: x[-1,2]; y[0,3]\n"
          "maximize: 3*x + 2*y + 5\n"
          "constraints: x + y <= 2\n"
          "upper_bound: 11\n"
          "RW-MATH-END\n").encode("ascii")
H_BI = {"schema_version": sc.HINTS_SCHEMA,
        "partition": {"variables": ["x"], "grid": 2},
        "derive": [{"variable": "y", "equality_index": 0}]}
H_LI = {"schema_version": sc.HINTS_SCHEMA,
        "partition": {"variables": ["x", "y"], "grid": 1},
        "derive": []}


def digest(b):
    return hashlib.sha256(b).hexdigest()


def compiled(raw, hint=None, index=0):
    return sc.compile_candidate(raw, block_index=index,
                                expected_source_sha256=digest(raw), hints=hint)


def _proof(fixture):
    # The proof is derived from a distinct existing synthetic fixture and must
    # be accepted against the recompiled model, never silently reinterpreted.
    return eo.canonical_bytes(fixture["header"]) + b"".join(
        eo.canonical_bytes(leaf) for leaf in fixture["leaves"])


def create_chain(tmp_path, raw=BILINEAR, hint=H_BI, fixture=None):
    if fixture is None:
        fixture = examples.bilinear_half()
    s = tmp_path / "source.txt"
    hints = tmp_path / "hints.json"
    model_path = tmp_path / "model.json"
    candidate_path = tmp_path / "candidate.json"
    certificate_path = tmp_path / "proof.jsonl"
    s.write_bytes(raw)
    hints.write_bytes(eo.canonical_bytes(hint))
    args = ["compile", "--source", str(s), "--expected-source-sha256", digest(raw),
            "--block-index", "0", "--hints", str(hints),
            "--expected-hints-sha256", digest(hints.read_bytes()),
            "--output-model", str(model_path), "--output-candidate", str(candidate_path)]
    assert workflow.main(args) == 0
    proof = _proof(fixture)
    certificate_path.write_bytes(proof)
    verify = ["verify", "--source", str(s), "--expected-source-sha256", digest(raw),
              "--block-index", "0", "--hints", str(hints),
              "--expected-hints-sha256", digest(hints.read_bytes()),
              "--model", str(model_path), "--candidate", str(candidate_path),
              "--certificate", str(certificate_path),
              "--expected-model-sha256", digest(model_path.read_bytes()),
              "--expected-candidate-sha256", digest(candidate_path.read_bytes()),
              "--expected-certificate-sha256", digest(proof)]
    return {"source": s, "hints": hints, "model": model_path,
            "candidate": candidate_path, "certificate": certificate_path,
            "compile": args, "verify": verify}


def test_new_bilinear_model_matches_old_math_fixture_without_source_inference():
    cand, model = compiled(BILINEAR, H_BI)
    assert model == examples.bilinear_half()["model"]
    assert cand["source_span"] == {"start": 0, "end": len(BILINEAR)}
    assert cand["source_block_sha256"] == digest(BILINEAR)
    assert cand["source_origin_authenticated"] is False
    assert cand["unmarked_source_context_interpreted"] is False
    assert cand["mathematical_certificate_verified"] is False
    assert cand["model_sha256"] == digest(eo.canonical_bytes(model))


def test_second_structurally_different_model_matches_old_math_fixture():
    candidate, model = compiled(LINEAR, H_LI)
    assert candidate["claimed_upper"] == "11"
    assert model == examples.linear_resource()["model"]
    assert eo.verify_point(eo.compile_model(model), ["2", "0"]) == 11


def test_end_to_end_source_model_exact_proof_replay(tmp_path, capsys):
    paths = create_chain(tmp_path)
    capsys.readouterr()
    assert workflow.main(paths["verify"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source_span_rederived_exactly"]
    assert report["claimed_upper"] == "1/4"
    assert report["mathematical_model_upper_bound"] == "1/4"
    assert report["all_leaf_math_and_coverage_checked"]
    assert report["scientific_claim_correctness_established"] is False
    assert report["source_origin_authenticated"] is False
    assert report["external_actions"] == "NONE"


def test_end_to_end_linear_source_model_proof_replay(tmp_path, capsys):
    paths = create_chain(tmp_path, raw=LINEAR, hint=H_LI,
                         fixture=examples.linear_resource())
    capsys.readouterr()
    assert workflow.main(paths["verify"]) == 0
    assert json.loads(capsys.readouterr().out)["mathematical_model_upper_bound"] == "11"


def test_two_claims_byte_offsets_unicode_intro_and_crlf():
    first = BILINEAR.replace(b"\n", b"\r\n")
    second = LINEAR.replace(b"\n", b"\r\n")
    prefix = "Tutkimuksen merkintä – kehitysesimerkki.\n".encode("utf-8")
    raw = prefix + first + b"Additional text; not interpreted.\n" + second
    a, b = compiled(raw, H_BI, 0), compiled(raw, H_LI, 1)
    assert a[0]["explicit_block_count"] == b[0]["explicit_block_count"] == 2
    assert a[0]["source_span"] == {"start": len(prefix), "end": len(prefix) + len(first)}
    assert b[0]["source_span"]["start"] > a[0]["source_span"]["end"]
    assert a[1] == examples.bilinear_half()["model"]
    assert b[1] == examples.linear_resource()["model"]
    with pytest.raises(sc.UnsupportedClaim, match="CLAIM_INDEX"):
        compiled(raw, index=2)


def test_multiple_blocks_are_explicitly_accounted_for_no_default_silent_new_claim():
    s = BILINEAR + b"Not included by a mathematically complete source parser.\n" + LINEAR
    selected, _ = compiled(s, H_LI, 1)
    assert selected["selected_block_index"] == 1
    assert selected["explicit_block_count"] == 2
    assert selected["source_span"]["start"] == len(BILINEAR) + len(b"Not included by a mathematically complete source parser.\n")


def test_signed_constants_division_greater_than_multiply_and_repeated_operand():
    src = (b"RW-MATH-BEGIN v1\ndomain: bounded_real\n"
           b"variables: x[-1/2,1]; w[0,1]\n"
           b"maximize: -(2*x)/4 + 5/2\n"
           b"constraints: x >= -1/2; w == x*x\n"
           b"upper_bound: 11/4\nRW-MATH-END\n")
    c, m = compiled(src)
    assert m["objective"] == {"coefficients": [[0, "-1/2"]], "constant": "5/2"}
    assert m["inequalities"] == [{"coefficients": [[0, "-1"]], "rhs": "1/2"}]
    assert m["products"] == [[0, 0, 1]]
    assert c["claimed_upper"] == "11/4"


def test_default_hints_partition_single_unfixed_and_not_truth_claim():
    source = (b"RW-MATH-BEGIN v1\ndomain: bounded_real\nvariables: x[0,1]\nmaximize: x\n"
              b"constraints: x <= 1\nupper_bound: 1\nRW-MATH-END\n")
    candidate, model = compiled(source)
    assert model["partition"] == {"variables": [0], "grid": 1}
    assert model["bound_derivations"] == []
    assert candidate["status"] == "source_bound_model_candidate_only"


def test_incompatible_hints_may_not_change_semantic_model():
    corrupted = deepcopy(H_BI)
    corrupted["partition"] = {"variables": ["z", "x"], "grid": 2}
    with pytest.raises(sc.UnsupportedClaim, match="PARTITION_ORDER"):
        compiled(BILINEAR, corrupted)
    corrupted = deepcopy(H_BI)
    corrupted["derive"] = [{"variable": "z", "equality_index": 0}]
    with pytest.raises(eo.CertificateError, match="DERIVATION_ZERO_TARGET"):
        compiled(BILINEAR, corrupted)
    corrupted = deepcopy(H_BI)
    corrupted["objective"] = "something else"
    with pytest.raises(eo.CertificateError, match="SOURCE_HINT_FIELDS"):
        compiled(BILINEAR, corrupted)


@pytest.mark.parametrize("replacement", [
    b"variables: x[0,1]; x[0,1]; z[0,1]",
    b"variables: x[0,1]; y[-1,2]; z[0,1]; z[0,1]",
    b"variables: x[0,1.0]; y[0,1]; z[0,1]",
    b"variables: x[0,1e0]; y[0,1]; z[0,1]",
    b"variables: x[-0,1]; y[0,1]; z[0,1]", # -0 simplifies to zero but admitted only in AST; grammar claims no proof of faithful source semantics
    b"variables: x[0,False]; y[0,1]; z[0,1]",
    b"variables: x[2,1]; y[0,1]; z[0,1]",
    b"variables: x[0,1]; y[0,1]; z[0,1]; v[0,1]; u[0,1]; t[0,1]; a[0,1]; b[0,1]; c[0,1]; d[0,1]; e[0,1]; f[0,1]; g[0,1]",
])
def test_invalid_variable_declarations_fail_closed(replacement):
    src = BILINEAR.replace(b"variables: x[0,1]; y[0,1]; z[0,1]", replacement)
    with pytest.raises((sc.UnsupportedClaim, eo.CertificateError)):
        compiled(src, H_BI)


@pytest.mark.parametrize("bad", [
    "z * y", "z+x*y", "x**2", "len([x])", "__import__('os').system('echo ok')",
    "x[0]", "x if y else z", "not z", "z and x", "x//2", "x%2",
    "x.real", "x != y", "x > y", "y + unknown", "z + 0.1", "z + 1e-2",
    "z + True", "z + False", "z + (1/0)", "z + (1/2)/(x+1)",
    "x + (y*z)", "z**0", "lambda x: x", "(x,y)", "f'{x}'",
])
def test_unsupported_or_nonaffine_objectives_fail_closed(bad):
    src = BILINEAR.replace(b"maximize: z", ("maximize: " + bad).encode())
    with pytest.raises((sc.UnsupportedClaim, eo.CertificateError)):
        compiled(src, H_BI)


@pytest.mark.parametrize("bad", [
    "x + y < 1", "x + y > 1", "x+y == 1 == z", "x+y != 1",
    "z == x * unknown", "z == z*x", "z == x*y + 1", "x*y == z",
    "x < y < z", "(x + y == 1) and (z == x*y)", "not(x+y == 1)",
    "x+y == approx(1)", "weighted x+y == 1", "x+y == 1 # assumptions removed",
    "x+y ~= 1", "x + y = 1", "z == max(x,y)", "z == x/y",
])
def test_unsupported_or_ambiguous_constraints_fail_closed(bad):
    src = BILINEAR.replace(b"constraints: x + y == 1; z == x*y",
                           ("constraints: " + bad).encode())
    with pytest.raises((sc.UnsupportedClaim, eo.CertificateError)):
        compiled(src, H_BI)


@pytest.mark.parametrize("bad", [
    "0.25", "~1/4", "approximately 1/4", "1e-1", "x", "1/0",
    "(1/4) if x else 1/2", "0/0", "sqrt(1/16)", "True", "nan", "Infinity"
])
def test_claimed_upper_must_be_exact_literal_not_inference(bad):
    src = BILINEAR.replace(b"upper_bound: 1/4", ("upper_bound: " + bad).encode())
    with pytest.raises((sc.UnsupportedClaim, eo.CertificateError)):
        compiled(src, H_BI)


@pytest.mark.parametrize("bad", [
    b"", b"RW-MATH-END\n", b"RW-MATH-BEGIN v1\ndomain: bounded_real\n", b"RW-MATH-BEGIN v1\ndomain: bounded_real\nRW-MATH-BEGIN v1\ndomain: bounded_real\nRW-MATH-END\n",
    BILINEAR.replace(b"RW-MATH-END", b"RW-MATH-BEGIN v1"),
    BILINEAR.replace(b"RW-MATH-BEGIN v1", b"Rw-Math-Begin"),
    BILINEAR.replace(b"\n", b"\r"),
    BILINEAR.rstrip(b"\n"),
    BILINEAR + b"RW-MATH-END\n",
])
def test_bad_source_markers_and_newlines_rejected(bad):
    with pytest.raises(sc.UnsupportedClaim):
        compiled(bad)


def test_unknown_line_and_unicode_inside_claim_rejected():
    for mutated in (
        BILINEAR.replace(b"maximize: z", b"maximize: z\nassume: none"),
        BILINEAR.replace(b"maximize: z", "maximize: z – adjusted".encode("utf8")),
        BILINEAR.replace(b"upper_bound: 1/4", b"upper_bound: 1/4; after adjustment"),
        BILINEAR.replace(b"variables:", b"maybe variables:"),
    ):
        with pytest.raises(sc.UnsupportedClaim):
            compiled(mutated, H_BI)


def test_external_source_pin_rejects_stale_or_mismatched_bytes():
    with pytest.raises(sc.UnsupportedClaim, match="EXTERNAL_SOURCE_PIN_MISMATCH"):
        sc.compile_candidate(BILINEAR,block_index=0,expected_source_sha256="0"*64,hints=H_BI)
    with pytest.raises(eo.CertificateError, match="SHA256_LITERAL"):
        sc.compile_candidate(BILINEAR,block_index=0,expected_source_sha256="x",hints=H_BI)


def test_replay_requires_externally_pinned_exact_source_proposal_and_model():
    c,m=compiled(BILINEAR,H_BI)
    cbytes,mbytes=eo.canonical_bytes(c),eo.canonical_bytes(m)
    params=dict(block_index=0,expected_source_sha256=digest(BILINEAR),
                candidate_bytes=cbytes,model_bytes=mbytes,
                expected_candidate_sha256=digest(cbytes),
                expected_model_sha256=digest(mbytes),hints=H_BI)
    assert sc.recheck_candidate(BILINEAR,**params)==(c,m)
    mutated=deepcopy(m)
    mutated["products"]=[[0,0,2]]
    params["model_bytes"]=eo.canonical_bytes(mutated)
    params["expected_model_sha256"]=digest(params["model_bytes"])
    with pytest.raises(sc.UnsupportedClaim, match="REDERIVATION_MISMATCH"):
        sc.recheck_candidate(BILINEAR,**params)
    params["model_bytes"]=mbytes
    params["expected_model_sha256"]=digest(mbytes)
    params["candidate_bytes"]=cbytes+b" "
    params["expected_candidate_sha256"]=digest(params["candidate_bytes"])
    with pytest.raises(sc.UnsupportedClaim, match="NONCANONICAL_BYTES"):
        sc.recheck_candidate(BILINEAR,**params)


def test_verify_rejects_certificate_bound_mismatching_exact_source_claim(tmp_path):
    paths=create_chain(tmp_path)
    # A more permissive mathematical upper bound is valid for the model but
    # does not prove the exact source-quoted inequality as requested.
    proof=paths["certificate"].read_bytes()
    records=[json.loads(line) for line in proof.splitlines()]
    records[0]["claimed_upper"]="1/2"
    modified=b"".join(eo.canonical_bytes(rec) for rec in records)
    paths["certificate"].write_bytes(modified)
    args=paths["verify"]
    args[args.index("--expected-certificate-sha256")+1]=digest(modified)
    with pytest.raises(sc.UnsupportedClaim,match="CERTIFICATE_SOURCE_BOUND_MISMATCH"):
        workflow.verify_from_paths(workflow._args if False else _parse_verify_args(args))


def _parse_verify_args(args):
    # Parse with same public CLI, but use a minimal Namespace so a rejection
    # does not depend on stderr formatting.
    import argparse
    parsed={}
    for i, a in enumerate(args):
        if a.startswith("--") and i+1<len(args):
            parsed[a[2:].replace("-","_")]=args[i+1]
    for name in ("source","model","hints","candidate","certificate"):
        parsed[name]=Path(parsed[name])
    parsed["block_index"]=int(parsed.get("block_index",0))
    return argparse.Namespace(**parsed)


def test_replay_source_changed_with_matching_new_source_pin_still_rejects(tmp_path):
    paths=create_chain(tmp_path)
    new=paths["source"].read_bytes().replace(b"x + y == 1",b"x + y == 2")
    paths["source"].write_bytes(new)
    v=paths["verify"]
    v[v.index("--expected-source-sha256")+1]=digest(new)
    with pytest.raises(sc.UnsupportedClaim,match="REDERIVATION_MISMATCH"):
        workflow.verify_from_paths(_parse_verify_args(v))


def test_replay_hint_mutation_requires_matching_external_hint_pin_and_model(tmp_path):
    paths=create_chain(tmp_path)
    h=deepcopy(H_BI)
    h["partition"]["grid"]=4
    raw=eo.canonical_bytes(h)
    paths["hints"].write_bytes(raw)
    with pytest.raises(sc.UnsupportedClaim,match="EXTERNAL_HINTS_PIN_MISMATCH"):
        workflow.verify_from_paths(_parse_verify_args(paths["verify"]))
    v=paths["verify"]
    v[v.index("--expected-hints-sha256")+1]=digest(raw)
    with pytest.raises(sc.UnsupportedClaim,match="REDERIVATION_MISMATCH"):
        workflow.verify_from_paths(_parse_verify_args(v))


def test_candidate_compiler_never_overwrites_existing_model_or_candidate(tmp_path):
    paths=create_chain(tmp_path)
    model_original=paths["model"].read_bytes()
    candidate_original=paths["candidate"].read_bytes()
    with pytest.raises(sc.UnsupportedClaim,match="OUTPUT_ALREADY_EXISTS"):
        workflow.compile_from_paths(_parse_compile_args(paths["compile"]))
    assert paths["model"].read_bytes()==model_original
    assert paths["candidate"].read_bytes()==candidate_original


def _parse_compile_args(args):
    import argparse
    fields={}
    for i,x in enumerate(args):
        if x.startswith("--") and i+1 < len(args):
            fields[x[2:].replace("-","_")]=args[i+1]
    for name in ("source","hints","output_model","output_candidate"):
        fields[name]=Path(fields[name])
    fields["block_index"]=int(fields.get("block_index",0))
    return argparse.Namespace(**fields)


def test_cli_runs_under_optimized_python_and_honors_pins(tmp_path):
    paths=create_chain(tmp_path)
    args=paths["verify"]
    for flags in ([],["-O"]):
        v=subprocess.run([sys.executable,*flags,"-m","tools.source_claim_workflow",*args],
             capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1],timeout=20)
        assert v.returncode==0, v.stderr
        assert json.loads(v.stdout)["status"]=="candidate_formalization_and_math_bound_replayed"
        bad=args.copy()
        bad[bad.index("--expected-candidate-sha256")+1]="0"*64
        v=subprocess.run([sys.executable,*flags,"-m","tools.source_claim_workflow",*bad],
             capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1],timeout=20)
        assert v.returncode==2 and not v.stdout
        assert "CANDIDATE_PIN" in v.stderr


def test_source_size_and_block_count_limits():
    with pytest.raises(sc.UnsupportedClaim,match="SOURCE_BYTES"):
        compiled(b"A"*(sc.MAX_SOURCE_BYTES+1)+b"\n")
    with pytest.raises(sc.UnsupportedClaim,match="CLAIM_COUNT_LIMIT"):
        compiled(BILINEAR*17, H_BI)
    overly_long=BILINEAR.replace(b"maximize: z",b"maximize: z"+b" "*4100)
    with pytest.raises(sc.UnsupportedClaim,match="CLAIM_BLOCK_BYTES"):
        compiled(overly_long,H_BI)


def test_nonascii_context_only_accepted_with_uninterpreted_context_flag():
    prefix="Esimerkki: tätä ei pidä tulkita tieteelliseksi löydöksi.\n".encode()
    raw=prefix+BILINEAR
    cand,_=compiled(raw,H_BI)
    assert cand["source_span"]["start"]==len(prefix)
    assert not cand["unmarked_source_context_interpreted"]
    assert not cand["external_scientific_accuracy_established"]


def test_source_missing_final_LF_rejects_even_when_claim_has_end():
    with pytest.raises(sc.UnsupportedClaim,match="SOURCE_FINAL_LF"):
        compiled(b"Text without LF")

FALSE_BOUND=(b"RW-MATH-BEGIN v1\ndomain: bounded_real\n"
             b"variables: x[0,1]\nmaximize: x\nconstraints: none\n"
             b"upper_bound: 1/2\nRW-MATH-END\n")


def test_source_bound_false_claim_requires_exact_feasible_counterexample(tmp_path, capsys):
    # First compile as an unverified candidate, then show mathematically exact
    # refutation without an optimizer or an external author/publisher assertion.
    src=tmp_path/"source.txt"
    src.write_bytes(FALSE_BOUND)
    model=tmp_path/"model.json"
    candidate=tmp_path/"candidate.json"
    args=["compile","--source",str(src),"--expected-source-sha256",digest(FALSE_BOUND),
          "--output-model",str(model),"--output-candidate",str(candidate)]
    assert workflow.main(args)==0
    assert json.loads(capsys.readouterr().out)["mathematical_proof"]=="not_supplied"
    point=tmp_path/"point.json"
    point.write_bytes(eo.canonical_bytes(["1"]))
    refute=["refute","--source",str(src),"--expected-source-sha256",digest(FALSE_BOUND),
            "--model",str(model),"--candidate",str(candidate),"--point",str(point),
            "--expected-model-sha256",digest(model.read_bytes()),
            "--expected-candidate-sha256",digest(candidate.read_bytes()),
            "--expected-point-sha256",digest(point.read_bytes())]
    assert workflow.main(refute)==0
    report=json.loads(capsys.readouterr().out)
    assert report["status"]=="formal_model_upper_refuted_by_exact_point"
    assert report["verified_feasible_point_value"]=="1"
    assert report["strict_violation_margin"]=="1/2"
    assert report["source_span_rederived_exactly"]
    assert report["paper_error_established"] is False
    assert report["source_origin_authenticated"] is False
    # Valid, non-violating point cannot be mislabeled a counterexample.
    point.write_bytes(eo.canonical_bytes(["1/2"]))
    refute[refute.index("--expected-point-sha256")+1]=digest(point.read_bytes())
    with pytest.raises(sc.UnsupportedClaim,match="POINT_DOES_NOT_REFUTE_CLAIM"):
        workflow.refute_from_paths(_parse_refute_args(refute))
    # A point outside the declared source domain cannot refute it.
    point.write_bytes(eo.canonical_bytes(["2"]))
    refute[refute.index("--expected-point-sha256")+1]=digest(point.read_bytes())
    with pytest.raises(eo.CertificateError,match="POINT_BOUNDS"):
        workflow.refute_from_paths(_parse_refute_args(refute))


def _parse_refute_args(args):
    import argparse
    fields={}
    for i,x in enumerate(args):
        if x.startswith("--") and i+1 < len(args):
            fields[x[2:].replace("-","_")]=args[i+1]
    for name in ("source","model","candidate","point"):
        fields[name]=Path(fields[name])
    fields["hints"]=None
    fields["expected_hints_sha256"]=None
    fields["block_index"]=int(fields.get("block_index",0))
    return argparse.Namespace(**fields)


def test_refutation_stale_point_pin_and_tampered_source_fail(tmp_path):
    src=tmp_path/"s"
    src.write_bytes(FALSE_BOUND)
    cand,mod=compiled(FALSE_BOUND)
    model=tmp_path/"m"
    model.write_bytes(eo.canonical_bytes(mod))
    candidate=tmp_path/"c"
    candidate.write_bytes(eo.canonical_bytes(cand))
    point=tmp_path/"p"
    point.write_bytes(eo.canonical_bytes(["1"]))
    args=_parse_refute_args(["refute","--source",str(src),
          "--expected-source-sha256",digest(FALSE_BOUND),
          "--model",str(model),"--candidate",str(candidate),"--point",str(point),
          "--expected-model-sha256",digest(model.read_bytes()),
          "--expected-candidate-sha256",digest(candidate.read_bytes()),
          "--expected-point-sha256","0"*64])
    with pytest.raises(sc.UnsupportedClaim,match="EXTERNAL_POINT_PIN_MISMATCH"):
        workflow.refute_from_paths(args)
    args.expected_point_sha256=digest(point.read_bytes())
    assert workflow.refute_from_paths(args)["strict_violation_margin"]=="1/2"
    new=FALSE_BOUND.replace(b"upper_bound: 1/2", b"upper_bound: 2")
    src.write_bytes(new)
    args.expected_source_sha256=digest(new)
    with pytest.raises(sc.UnsupportedClaim,match="SOURCE_CANDIDATE_REDERIVATION_MISMATCH"):
        workflow.refute_from_paths(args)
