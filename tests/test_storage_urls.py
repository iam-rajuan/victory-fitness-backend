from app.config import settings
from app.utils import storage_urls


def test_canonicalize_s3_url_rewrites_bucket_region(monkeypatch):
    monkeypatch.setattr(settings, "aws_s3_bucket", "victory-fitness-storage")
    monkeypatch.setattr(settings, "aws_s3_region", "eu-central-1")
    monkeypatch.setattr(settings, "aws_region", "eu-north-1")
    monkeypatch.setattr(storage_urls, "get_s3_bucket_region", lambda: "eu-central-1")

    url = "https://victory-fitness-storage.s3.eu-north-1.amazonaws.com/coach-archives/legal-pdfs/doc.pdf"

    assert storage_urls.canonicalize_s3_url(url) == (
        "https://victory-fitness-storage.s3.eu-central-1.amazonaws.com/coach-archives/legal-pdfs/doc.pdf"
    )


def test_canonicalize_s3_urls_in_html_rewrites_image_urls(monkeypatch):
    monkeypatch.setattr(settings, "aws_s3_bucket", "victory-fitness-storage")
    monkeypatch.setattr(settings, "aws_s3_region", "eu-central-1")
    monkeypatch.setattr(settings, "aws_region", "eu-north-1")
    monkeypatch.setattr(storage_urls, "get_s3_bucket_region", lambda: "eu-central-1")

    html = '<p><img src="https://victory-fitness-storage.s3.eu-north-1.amazonaws.com/coach-archives/legal-images/a.png"></p>'

    assert "s3.eu-central-1.amazonaws.com" in storage_urls.canonicalize_s3_urls_in_html(html)
