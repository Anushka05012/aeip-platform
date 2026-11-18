from src.failure_analysis import extract_error_lines
from src.public_benchmarks import chunk_coverage, evaluate_logchunks, logchunks_root, split_for

TRAVIS_LOG = """$ npm install
npm WARN deprecated left-pad
$ npm test
> jest
FAIL src/cart.test.js
  ● cart › applies discount
    expect(received).toBe(expected)
    Expected: 90
    Received: 100
Tests: 1 failed, 12 passed
The command "npm test" exited with 1.
$ artifacts upload
ERROR: failed to upload: out/app.tar.gz
err: open out/app.tar.gz: no such file or directory
Done. Your build exited with 1.
"""


def test_extraction_reads_the_failing_step_not_the_cleanup_after_it():
    lines = extract_error_lines(TRAVIS_LOG)
    assert any("applies discount" in line for line in lines)
    assert any("Expected: 90" in line for line in lines)
    assert not any("failed to upload" in line for line in lines)
    assert not any("npm WARN" in line for line in lines)


def test_extraction_handles_github_actions_markers_and_colour_codes():
    log = ("2026-09-01T10:00:00.0000000Z ##[group]Run pytest\n"
           "2026-09-01T10:00:01.0000000Z \x1b[31mE   AssertionError: totals differ\x1b[0m\n"
           "2026-09-01T10:00:02.0000000Z ##[error]Process completed with exit code 1.\n"
           "2026-09-01T10:00:03.0000000Z ##[group]Post job cleanup\n"
           "2026-09-01T10:00:04.0000000Z Error: cache save failed\n")
    lines = extract_error_lines(log)
    assert "E   AssertionError: totals differ" in lines
    assert not any("cache save failed" in line for line in lines)


def test_extraction_without_a_failure_marker_searches_the_whole_log():
    lines = extract_error_lines("starting\nsrc/a.js:3 Strings must use singlequote. (quotes/quotes)\ndone\n")
    assert any("singlequote" in line for line in lines)


def test_chunk_coverage_ignores_colour_codes_and_spacing():
    assert chunk_coverage(["\x1b[31mE  assert 1 == 2\x1b[0m"], ["[31mE assert 1 == 2"]) == 1.0
    assert chunk_coverage(["something else"], ["E assert 1 == 2", "other"]) == 0.0


def test_split_is_stable():
    assert split_for("nvbn@thefuck") == split_for("nvbn@thefuck")
    assert {split_for(f"owner@repo{i}") for i in range(20)} == {"dev", "test"}


def test_logchunks_benchmark_on_a_tiny_copy(tmp_path):
    root = tmp_path / "logchunks" / "LogChunks"
    (root / "build-failure-reason" / "JavaScript").mkdir(parents=True)
    (root / "logs" / "JavaScript" / "acme@shop" / "failed").mkdir(parents=True)
    (root / "logs" / "JavaScript" / "acme@shop" / "failed" / "1.log").write_text(TRAVIS_LOG, encoding="utf-8")
    (root / "build-failure-reason" / "JavaScript" / "acme@shop.xml").write_text(
        "<Examples><Example><Log>JavaScript/acme@shop/failed/1.log</Log>"
        "<Chunk>  ● cart › applies discount\n    Expected: 90\n    Received: 100</Chunk></Example></Examples>",
        encoding="utf-8")
    assert logchunks_root(tmp_path) == root
    result = evaluate_logchunks(root)
    assert result["repositories"] == 1
    assert result["all"]["aeip"]["wholeChunkFound"] == 1.0
    assert set(result) >= {"all", "test" if split_for("acme@shop") == "test" else "dev"}


def test_previous_extractor_showed_cleanup_noise():
    from src.public_benchmarks import previous_extractor
    assert any("failed to upload" in line for line in previous_extractor(TRAVIS_LOG))
