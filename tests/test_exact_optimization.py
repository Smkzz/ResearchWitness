"""Contract, exact math, parser, identity, coverage and mutation regressions."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys

import pytest

from researchwitness import exact_optimization as eo
from tools import exact_optimization_reference as reference
from tools import optimization_examples as examples


def rebind(fixture):
    fixture["header"]["model_sha256"] = hashlib.sha256(eo.canonical_bytes(fixture["model"])).hexdigest()
    return fixture


def run(fixture):
    return eo.verify_records(eo.compile_model(fixture["model"]), fixture["header"],
                             fixture["leaves"], model_sha256=fixture["header"]["model_sha256"])


def write_case(path, fixture):
    m = eo.canonical_bytes(fixture["model"])
    proof = eo.canonical_bytes(fixture["header"]) + b"".join(
        eo.canonical_bytes(leaf) for leaf in fixture["leaves"])
    mp, cp = path / "model.json", path / "certificate.jsonl"
    mp.write_bytes(m)
    cp.write_bytes(proof)
    return mp, cp, hashlib.sha256(m).hexdigest(), hashlib.sha256(proof).hexdigest()


@pytest.mark.parametrize("fixture", examples.positive_cases(), ids=lambda f: f["name"])
def test_separate_positive_cases_and_exact_witness(fixture):
    result = run(fixture)
    alternative = reference.reference_verify(fixture["model"], fixture["header"], fixture["leaves"])
    assert alternative["valid"] is True
    assert result["verified_upper"] == alternative["maximum_upper"] == fixture["optimum"]
    assert result["partition_complete"] and alternative["complete_coverage"]
    assert result["proved_empty_leaves"] == alternative["empty_leaves"]
    point_value = eo.verify_point(eo.compile_model(fixture["model"]), fixture["witness"])
    assert point_value == F(fixture["optimum"])
    assert result["global_optimum_established"] is False  # The bound alone does not assert attainment.
    assert result["source_correspondence"] == "not_established_by_this_checker"


def corrupt(kind):
    f = examples.bilinear_half()
    if kind == "target":
        f["header"]["claimed_upper"] = "1/5"
    elif kind == "swapped_duals":
        f["leaves"][0]["lambda"], f["leaves"][1]["lambda"] = (
            f["leaves"][1]["lambda"], f["leaves"][0]["lambda"])
    elif kind == "product":
        f["model"]["products"] = [[0, 0, 2]]
    elif kind == "row_index":
        f["leaves"][0]["lambda"] = [[4, "1"]]
    elif kind == "negative_lambda":
        f["leaves"][0]["lambda"] = [[3, "-1"]]
    elif kind == "zero_lambda":
        f["leaves"][0]["lambda"] = [[3, "0"]]
    elif kind == "duplicate_sparse":
        f["leaves"][0]["lambda"] = [[3, "1"], [3, "1"]]
    elif kind == "negative_index":
        f["leaves"][0]["lambda"] = [[-1, "1"]]
    elif kind == "bool_index":
        f["leaves"][0]["nu"] = [[False, "1/2"]]
    elif kind == "missing":
        f["leaves"].pop()
    elif kind == "additional":
        f["leaves"].append(deepcopy(f["leaves"][0]))
    elif kind == "false_empty":
        f["leaves"][0] = {"kind": "empty", "lower": [0], "upper": [1]}
    elif kind == "unrelated_field":
        f["leaves"][0]["reported_bound"] = "0"
    elif kind == "residual_omitted":
        f = examples.linear_resource()
        f["header"]["claimed_upper"] = "9"
    elif kind == "repeated_operand":
        f = examples.repeated_operand()
        f["header"]["claimed_upper"] = "3/4"
    elif kind == "point_not_empty":
        f = examples.infeasible_leaf()
        f["model"]["equalities"][0]["rhs"] = "1/2"
        f["header"]["claimed_upper"] = "1/2"
    else:
        raise AssertionError(kind)
    return rebind(f)


@pytest.mark.parametrize("kind", ["target", "swapped_duals", "product", "row_index",
    "negative_lambda", "zero_lambda", "duplicate_sparse", "negative_index", "bool_index",
    "missing", "additional", "false_empty", "unrelated_field", "residual_omitted",
    "repeated_operand", "point_not_empty"])
def test_re_pinned_semantic_mutations_rejected_by_both(kind):
    fixture = corrupt(kind)
    with pytest.raises(eo.CertificateError):
        run(fixture)
    assert not reference.reference_verify(fixture["model"], fixture["header"],
                                          fixture["leaves"])["valid"]


@pytest.mark.parametrize("mutation", ["duplicate", "hole", "ancestor", "equal_volume", "noncanonical"])
def test_partition_attack_not_merely_volume(mutation):
    f = examples.coverage_control()
    leaves = f["leaves"]
    if mutation == "duplicate":
        leaves.append(deepcopy(leaves[0]))
    elif mutation == "hole":
        leaves.pop()
    elif mutation == "ancestor":
        leaves.append(examples.bound([0, 0], [1, 1]))
    elif mutation == "equal_volume":
        leaves[:] = leaves[:3] + [examples.bound([i, j], [i+1, j+1])
                                  for i in (0, 1) for j in (0, 1)]
        assert sum((l["upper"][0]-l["lower"][0])*(l["upper"][1]-l["lower"][1])
                   for l in leaves) == 16
    elif mutation == "noncanonical":
        leaves[:] = [examples.bound([0, 0], [1, 4]), examples.bound([1, 0], [4, 4])]
    f["header"]["leaf_count"] = len(leaves)
    with pytest.raises(eo.CertificateError):
        run(f)
    assert not reference.reference_verify(f["model"], f["header"], f["leaves"])["valid"]


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":{"a":0,"a":1}}',
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":0.2}', b'{"x":1e1}',
    b'\xff', b'{', b'1'*19, b'[] []', b'[\n'*18+b'0'+b']'*18, b''])
def test_json_rejections(raw):
    with pytest.raises(eo.CertificateError):
        eo.parse_json(raw)


@pytest.mark.parametrize("raw", [True, 1, 0.1, None, "NaN", "1/-2", "1/0", "1/01", "01",
    "-0", "2/2", "0/2", "1.0", "1e3", " 1", "1"*31, "1/"+"9"*31])
def test_rational_literals(raw):
    with pytest.raises(eo.CertificateError):
        eo.rational(raw)


def test_direct_and_file_identity_controls(tmp_path):
    f = examples.bilinear_half()
    m, c, mh, ch = write_case(tmp_path, f)
    good = eo.verify_paths(m, c, expected_model_sha256=mh, expected_certificate_sha256=ch)
    assert good["verified_upper"] == "1/4" and good["external_byte_pins_checked"]
    with pytest.raises(eo.CertificateError, match="EXTERNAL_MODEL_PIN"):
        eo.verify_paths(m, c, expected_model_sha256="0"*64, expected_certificate_sha256=ch)
    with pytest.raises(eo.CertificateError, match="EXTERNAL_CERTIFICATE_PIN"):
        eo.verify_paths(m, c, expected_model_sha256=mh, expected_certificate_sha256="0"*64)
    f["header"]["model_sha256"] = "0"*64
    with pytest.raises(eo.CertificateError, match="MODEL_BINDING"):
        eo.verify_records(eo.compile_model(f["model"]), f["header"], f["leaves"], model_sha256=mh)
    m.write_bytes(m.read_bytes()+b' ')
    with pytest.raises(eo.CertificateError, match="EXTERNAL_MODEL_PIN"):
        eo.verify_paths(m, c, expected_model_sha256=mh, expected_certificate_sha256=ch)


def test_file_boundaries_and_cli(tmp_path, capsys, monkeypatch):
    f = examples.bilinear_half()
    m, c, mh, ch = write_case(tmp_path, f)
    args = ["--model", str(m), "--certificate", str(c), "--expected-model-sha256", mh,
            "--expected-certificate-sha256", ch]
    assert eo.main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "upper_bound_certified"
    assert eo.main(args[:-1]+["f"*64]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "rejected"
    c.write_bytes(c.read_bytes().rstrip(b'\n'))
    with pytest.raises(eo.CertificateError, match="UNTERMINATED"):
        eo.verify_paths(m, c, expected_model_sha256=mh, expected_certificate_sha256=ch)
    c.write_bytes(b'')
    with pytest.raises(eo.CertificateError, match="EMPTY_CERTIFICATE"):
        eo.verify_paths(m, c, expected_model_sha256=mh, expected_certificate_sha256=ch)
    with monkeypatch.context() as p:
        p.setattr(eo, "MAX_MODEL_BYTES", 3)
        with pytest.raises(eo.CertificateError, match="FILE_SIZE"):
            eo.verify_paths(m, c, expected_model_sha256=mh, expected_certificate_sha256=ch)
    c.unlink()
    assert eo.main(args) == 2
    assert "FileNotFoundError" in capsys.readouterr().err


def test_symlink_and_hardlink_refused(tmp_path):
    m, c, mh, ch = write_case(tmp_path, examples.bilinear_half())
    link = tmp_path / "link"
    try:
        link.symlink_to(m)
    except (OSError, NotImplementedError):
        pytest.skip("symlink privilege is not available on this platform")
    with pytest.raises(eo.CertificateError, match="UNSAFE_FILE"):
        eo.verify_paths(link, c, expected_model_sha256=mh, expected_certificate_sha256=ch)
    link.unlink()
    os.link(m, link)
    with pytest.raises(eo.CertificateError, match="UNSAFE_FILE"):
        eo.verify_paths(m, c, expected_model_sha256=mh, expected_certificate_sha256=ch)


def test_normal_and_optimized_python_have_same_contract(tmp_path):
    m, c, mh, ch = write_case(tmp_path, examples.bilinear_half())
    args = ["-m", "researchwitness.exact_optimization", "--model", str(m),
            "--certificate", str(c), "--expected-model-sha256", mh,
            "--expected-certificate-sha256", ch]
    good = []
    for opts in ([], ["-O"]):
        result = subprocess.run([sys.executable, *opts, *args], capture_output=True, text=True,
                                timeout=20, cwd=Path(__file__).resolve().parents[1])
        assert result.returncode == 0, result.stderr
        good.append(json.loads(result.stdout))
        result = subprocess.run([sys.executable, *opts, *args[:-1], "0"*64],
                                capture_output=True, text=True, timeout=20,
                                cwd=Path(__file__).resolve().parents[1])
        assert result.returncode == 2 and not result.stdout
    assert good[0] == good[1]


def test_all_empty_and_signed_residuals():
    m = examples.model([["0", "1"], ["2", "3"]], [[0,"1"]],
                       equalities=[examples.row([[0,"1"],[1,"-1"]],"0")],
                       derivations=[[1,0]])
    f = examples.case("all_empty", m, "-100", [{"kind":"empty","lower":[0],"upper":[1]}], None, None)
    result = run(f)
    assert result["status"] == "infeasible_model_certified" and result["verified_upper"] is None
    assert reference.reference_verify(m,f["header"],f["leaves"])["maximum_upper"] is None
    m = examples.model([["-2","3"],["-1","4"]], [[0,"-2"],[1,"3"]], constant="7")
    f = examples.case("signed",m,"23",[examples.bound([0],[1])],"23",["-2","4"])
    assert run(f)["verified_upper"] == "23"
    assert eo.verify_point(eo.compile_model(m),f["witness"]) == 23


def test_exact_residual_upper_for_random_feasible_models():
    rng = random.Random(614031)
    for _ in range(100):
        n=3
        lo=[F(rng.randint(-5,0),rng.randint(1,5)) for _ in range(n)]
        hi=[x+F(rng.randint(1,5),rng.randint(1,5)) for x in lo]
        point=[(x+y)/2 for x,y in zip(lo,hi)]
        c=[F(rng.randint(-4,4),3) for _ in range(n)]
        matrix=[[F(rng.randint(-5,5),2) for _ in range(n)] for _ in range(2)]
        rhs=[sum(a*x for a,x in zip(row,point))+1 for row in matrix]
        m=examples.model([[str(a),str(b)] for a,b in zip(lo,hi)],
                         [[j,str(a)] for j,a in enumerate(c) if a],constant="-1/7",
                         inequalities=[examples.row([[j,str(a)] for j,a in enumerate(row) if a],str(b))
                                       for row,b in zip(matrix,rhs)])
        leaf=examples.bound([0],[1],[[0,"1/3"],[1,"2/5"]])
        compiled=eo.compile_model(m)
        upper=eo.leaf_upper(compiled,leaf)
        value=eo.verify_point(compiled,[str(x) for x in point])
        assert upper >= value
        f=examples.case("random",m,str(upper),[leaf],None,None)
        assert reference.reference_verify(m,f["header"],f["leaves"])["maximum_upper"] == str(upper)


def test_resource_budgets_and_model_rejections(monkeypatch):
    f=examples.bilinear_half()
    with monkeypatch.context() as p:
        p.setattr(eo,"MAX_WORK",1)
        with pytest.raises(eo.CertificateError,match="WORK_BUDGET"):
            run(f)
    with monkeypatch.context() as p:
        p.setattr(eo,"MAX_INTEGER_BITS",2)
        with pytest.raises(eo.CertificateError,match="BIT_BUDGET"):
            eo._checked(F(100))
    with monkeypatch.context() as p:
        p.setattr(eo,"MAX_JSON_NODES",2)
        with pytest.raises(eo.CertificateError,match="STRUCTURE"):
            eo.parse_json(b'[1,2,3]')
    for key,value in (("products",[[0,1,0]]),("products",[[0,1,2],[0,1,2]]),
                      ("bound_derivations",[[2,0]]),("bound_derivations",[[1,0],[1,0]]),
                      ("partition",{"variables":[1,0],"grid":2}),
                      ("partition",{"variables":[0],"grid":3}),
                      ("partition",{"variables":[],"grid":2}),
                      ("bounds",[["1","0"],["0","1"],["0","1"]])):
        m=deepcopy(f["model"])
        m[key]=value
        with pytest.raises(eo.CertificateError):
            eo.compile_model(m)
    for values,code in ((["1","1","1"],"EQUALITY"),(["1/2","1/2","1/3"],"PRODUCT"),
                        (["-1","2","0"],"BOUNDS"),(["0"],"DIMENSION")):
        with pytest.raises(eo.CertificateError,match=code):
            eo.verify_point(eo.compile_model(f["model"]),values)
    m=examples.linear_resource()["model"]
    with pytest.raises(eo.CertificateError,match="INEQUALITY"):
        eo.verify_point(eo.compile_model(m),["2","3"])


def test_examples_writer_is_exclusive_and_replayable(tmp_path, capsys):
    out=tmp_path/"fresh"
    assert examples.main(["--output-dir",str(out)]) == 0
    pins=json.loads(capsys.readouterr().out)
    for f in examples.positive_cases():
        name=f["name"]
        result=eo.verify_paths(out/(name+".model.json"),out/(name+".certificate.jsonl"),
            expected_model_sha256=pins[name+".model.json"],
            expected_certificate_sha256=pins[name+".certificate.jsonl"])
        assert result["verified_upper"]==f["optimum"]
    with pytest.raises(FileExistsError):
        examples.write_examples(out)


def test_reference_validates_unused_rows_and_reports_resource_limit():
    for sparse in ([[-1, "1"]], [[0, "1/0"]], [[0, "2/2"]]):
        f = examples.linear_resource()
        f["model"]["inequalities"].append(examples.row(sparse, "1"))
        rebind(f)
        # No multiplier points to this added row, but it still must be parsed.
        with pytest.raises(eo.CertificateError):
            run(f)
        outcome = reference.reference_verify(f["model"], f["header"], f["leaves"])
        assert outcome["status"] == "rejected"
    m = examples.model([["0", str(F(1, 2**83 + 2*i + 1))] for i in range(40)], [])
    f = examples.case("reference_lcm_limit", m, "0", [examples.bound([0], [1])], None, None)
    assert run(f)["verified_upper"] == "0"
    outcome = reference.reference_verify(m, f["header"], f["leaves"])
    assert not outcome["valid"] and outcome["status"] == "inconclusive"
    assert outcome["error"] == "reference LCM budget"


def test_decoded_duplicate_keys_and_extra_stream_records(tmp_path):
    with pytest.raises(eo.CertificateError, match="DUPLICATE_JSON_KEY"):
        eo.parse_json(b'{"axis":0,"\\u0061xis":1}')
    m, c, mh, ch = write_case(tmp_path, examples.bilinear_half())
    original = c.read_bytes()
    for suffix in (b'\n', b'{}\n', b'null\n', b'extra data\n'):
        altered = original + suffix
        c.write_bytes(altered)
        with pytest.raises(eo.CertificateError):
            eo.verify_paths(m, c, expected_model_sha256=mh,
                            expected_certificate_sha256=hashlib.sha256(altered).hexdigest())


def test_proof_changes_during_read_cannot_return_success(tmp_path, monkeypatch):
    m, c, mh, ch = write_case(tmp_path, examples.bilinear_half())
    opener = eo._open_regular
    # A bounded file-like wrapper deterministically changes consumed bytes after
    # the trusted file has been opened. It does not claim OS snapshot isolation.
    class MutatingReader:
        def __init__(self, handle):
            self.handle = handle
            self.lines = 0
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.handle.close()
        def readline(self, size):
            line = self.handle.readline(size)
            self.lines += 1
            if self.lines == 2:
                return b' ' + line  # Valid same mathematics, wrong consumed-byte hash.
            return line
    def open_changed(path, maximum):
        handle = opener(path, maximum)
        return MutatingReader(handle) if path == c else handle
    monkeypatch.setattr(eo, "_open_regular", open_changed)
    with pytest.raises(eo.CertificateError, match="EXTERNAL_CERTIFICATE_PIN"):
        eo.verify_paths(m, c, expected_model_sha256=mh, expected_certificate_sha256=ch)
