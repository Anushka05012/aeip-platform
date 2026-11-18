import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domain import Commit, Document, RepositorySnapshot
from src.risk_engine import RiskEngine, is_test_path, covered_module

NOW = datetime(2026, 9, 10)


def commit(sha, day, files, deps=()):
    return Commit(sha, datetime(2026, 9, day), tuple(files), 50, 10, 2, f"change {sha}", tuple(deps))


def score(commits, documents=()):
    snapshot = RepositorySnapshot("o/r", tuple(commits), (), tuple(documents))
    return {item.path: item for item in RiskEngine().score_files(snapshot, NOW, window_days=30)}


def test_test_files_are_recognised_across_languages():
    assert is_test_path("tests/test_cart.py") and is_test_path("src/cart.spec.ts") and is_test_path("pkg/cart_test.go")
    assert is_test_path("src/test/java/CartTest.java") and not is_test_path("src/cart.py")
    assert covered_module("tests/test_cart.py") == covered_module("src/cart.spec.ts") == covered_module("pkg/cart_test.go") == "cart"


def test_untested_file_scores_higher_than_a_tested_one():
    risks = score([commit("1", 1, ["src/cart.py", "src/billing.py"]), commit("2", 2, ["tests/test_cart.py"])])
    assert risks["src/billing.py"].breakdown()["testGap"] == 15 and not risks["src/billing.py"].has_tests
    assert risks["src/cart.py"].has_tests
    assert risks["src/billing.py"].score > risks["src/cart.py"].score
    assert "tests/test_cart.py" not in risks  # tests are evidence, never scored themselves


def test_a_test_folder_named_after_the_module_counts_as_tests():
    risks = score([commit("1", 1, ["src/utils.py"]), commit("2", 2, ["tests/test_utils/test_paths.py"])])
    assert risks["src/utils.py"].has_tests


def test_changes_that_also_update_tests_reduce_the_gap():
    with_tests = score([commit("1", 1, ["src/cart.py", "tests/test_cart.py"])])["src/cart.py"]
    without = score([commit("1", 1, ["src/cart.py"]), commit("0", 1, ["tests/test_cart.py"])])["src/cart.py"]
    assert with_tests.test_touch_ratio == 1.0 and with_tests.breakdown()["testGap"] == 0
    assert without.breakdown()["testGap"] == 7


def test_files_imported_by_many_others_have_a_larger_blast_radius():
    docs = [Document(f"src/view{i}.py", "from payments import charge\n", "code") for i in range(5)]
    docs.append(Document("src/payments.py", "def charge(): pass\n", "code"))
    risks = score([commit("1", 1, ["src/payments.py", "src/other.py"])], docs)
    assert risks["src/payments.py"].dependents == 5 and risks["src/payments.py"].breakdown()["blastRadius"] == 5
    assert risks["src/other.py"].dependents == 0
    assert any("imported by 5 other files" in reason for reason in risks["src/payments.py"].reasons)


def test_change_alongside_a_dependency_update_is_flagged():
    risks = score([commit("1", 1, ["src/api.py"], deps=["package.json", "package-lock.json"])])
    assert risks["src/api.py"].dependency_changes == 1 and risks["src/api.py"].breakdown()["dependencies"] == 5


def test_docs_get_no_test_gap_points():
    assert score([commit("1", 1, ["docs/guide.md"])])["docs/guide.md"].breakdown()["testGap"] == 0


def test_score_is_the_sum_of_the_breakdown_and_capped_at_100():
    heavy = [Commit(str(i), datetime(2026, 9, 1 + i % 9), ("src/core.py",), 400, 400, 40, "", ("go.mod",))
             for i in range(20)]
    docs = [Document(f"src/m{i}.py", "import core\n", "code") for i in range(20)]
    result = score(heavy, docs)["src/core.py"]
    assert result.score == sum(result.breakdown().values()) == 100


def test_lockfile_lines_do_not_inflate_churn():
    from src.github_source import GitHubDataSource

    detail = {"sha": "c", "commit": {"author": {"date": "2026-09-01T00:00:00Z"}, "message": "bump"},
              "files": [{"filename": "src/app.py", "additions": 5, "deletions": 1, "patch": ""},
                        {"filename": "package-lock.json", "additions": 4000, "deletions": 3000}]}
    parsed = GitHubDataSource._to_commit(detail)
    assert (parsed.additions, parsed.deletions) == (5, 1)
    assert parsed.dependency_files == ("package-lock.json",)
