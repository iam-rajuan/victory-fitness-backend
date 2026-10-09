from app.utils.html import sanitize_html_content


def test_sanitize_html_content_preserves_safe_legal_markup():
    raw = """
    <h2>Privacy</h2>
    <p><strong>Readable</strong> <em>content</em> <u>matters</u>.</p>
    <ul><li>First</li><li>Second</li></ul>
    <a href="https://victoryfitnessapp.com" target="_blank">Victory</a>
    <img src="https://cdn.example.com/legal.png" alt="Legal" width="999" onerror="alert(1)">
    """

    cleaned = sanitize_html_content(raw)

    assert "<h2>Privacy</h2>" in cleaned
    assert "<strong>Readable</strong>" in cleaned
    assert "<ul><li>First</li><li>Second</li></ul>" in cleaned
    assert 'href="https://victoryfitnessapp.com"' in cleaned
    assert 'rel="noopener noreferrer"' in cleaned
    assert 'src="https://cdn.example.com/legal.png"' in cleaned
    assert "width=" not in cleaned
    assert "onerror" not in cleaned


def test_sanitize_html_content_removes_unsafe_tags_and_urls():
    raw = """
    <script>alert(1)</script>
    <style>body{display:none}</style>
    <p onclick="alert(1)">Safe text</p>
    <a href="javascript:alert(1)">Bad link</a>
    <img src="data:image/png;base64,AAAA" alt="Inline data">
    <iframe src="https://example.com"></iframe>
    """

    cleaned = sanitize_html_content(raw)

    assert "<script" not in cleaned
    assert "<style" not in cleaned
    assert "<iframe" not in cleaned
    assert "onclick" not in cleaned
    assert "javascript:" not in cleaned
    assert "data:image" not in cleaned
    assert "<p>Safe text</p>" in cleaned
