from monitor.store.dedupe import sha256_bytes, truncate_for_llm


def test_sha256_stable():
    assert sha256_bytes(b"abc") == sha256_bytes(b"abc")


def test_truncate_for_llm():
    txt = "x" * 200
    out = truncate_for_llm(txt, 50)
    assert len(out) <= 60
