import argparse
import hashlib
import json
import os
import time
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from typing import Any

from scraper.paths import data_root
from scraper.s3_client import s3_client

ROOT = data_root()
DEFAULT_REGISTRY = ROOT / "sources" / "sources.example.json"
DEFAULT_MANIFEST = ROOT / "artifacts" / "manifests" / "download_manifest.json"
DEFAULT_ENDPOINT_URL = os.environ.get("HF_CDSS_S3_ENDPOINT_URL", "http://localhost:4566")
DEFAULT_BUCKET = os.environ.get("HF_CDSS_RAW_BUCKET", "hf-cdss-raw")
DEFAULT_PREFIX = os.environ.get("HF_CDSS_S3_PREFIX", "heart_failure")
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_bytes(url: str, timeout: int) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        request_context = playwright.request.new_context(
            user_agent=BROWSER_USER_AGENT,
            extra_http_headers={
                "Accept": "application/pdf,application/xml,application/json,text/html,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        response = request_context.get(url, timeout=timeout * 1000)
        if response.ok:
            payload = response.body()
            request_context.dispose()
            return payload
        request_context.dispose()

        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=BROWSER_USER_AGENT,
            extra_http_headers={
                "Accept": "application/pdf,application/xml,application/json,text/html,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        page = context.new_page()
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        if response is None:
            browser.close()
            raise RuntimeError(f"No browser response for {url}")
        if response.status >= 400:
            status = response.status
            browser.close()
            raise RuntimeError(f"Browser download returned HTTP {status} for {url}")
        payload = response.body()
        browser.close()
        return payload


def fetch_json(url: str, timeout: int) -> dict[str, Any]:
    return json.loads(download_bytes(url, timeout).decode("utf-8"))


def looks_like_html(payload: bytes) -> bool:
    head = payload[:8192].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<body" in head[:4096]


def html_target_path(target_path: str) -> str:
    path = Path(target_path)
    if path.suffix.lower() == ".html":
        return str(path)
    return str(path.with_suffix(".html"))


def coerce_download_item(item: dict[str, str], payload: bytes, url: str) -> dict[str, str]:
    """Accept HTML payloads for guideline sources that were registered as PDF."""
    kind = item.get("kind", "source")
    target_path = item["target_path"]
    suffix = Path(target_path).suffix.lower()

    if payload.startswith(b"%PDF"):
        return {**item, "kind": "pdf"}
    if looks_like_html(payload):
        if kind in {"pdf", "source"} or suffix == ".pdf":
            html_path = html_target_path(target_path)
            # Logical registry path (raw/…); durable write is S3 put_object with raw/ stripped.
            print(
                f"Received HTML instead of PDF from {url}; "
                f"S3 object key will use logical path {html_path} "
                f"(→ s3://…/{html_path.removeprefix('raw/')} after strip)"
            )
            return {**item, "kind": "html", "target_path": html_path}
        if kind == "html" or suffix == ".html":
            return {**item, "kind": "html"}
    validate_payload(kind, target_path, payload, url)
    return item


def artifact_kind_for_source(source: dict[str, Any]) -> str:
    explicit = source.get("artifact_kind")
    if explicit:
        return str(explicit)
    source_type = str(source.get("source_type", ""))
    if source_type == "guideline_html":
        return "html"
    if source_type == "guideline_pdf":
        return "pdf"
    if source_type == "drug_label_xml":
        return "xml"
    return "source"


def validate_payload(kind: str, target_path: str, payload: bytes, url: str) -> None:
    suffix = Path(target_path).suffix.lower()
    head = payload[:64].lstrip().lower()
    if (kind == "pdf" or suffix == ".pdf") and not payload.startswith(b"%PDF"):
        raise RuntimeError(f"Expected PDF but received non-PDF payload from {url}")
    if (kind == "html" or suffix == ".html") and not looks_like_html(payload):
        raise RuntimeError(f"Expected HTML but received non-HTML payload from {url}")
    if (kind == "xml" or suffix == ".xml") and not (head.startswith(b"<?xml") or head.startswith(b"<")):
        raise RuntimeError(f"Expected XML but received non-XML payload from {url}")


def s3_key(prefix: str, target_path: str) -> str:
    normalized = target_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("raw/"):
        normalized = normalized[len("raw/") :]
    return f"{prefix.strip('/')}/{normalized}"


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def ensure_bucket(client, bucket: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)


def dailymed_candidates(query: str, timeout: int) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote(query)
    base = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
    for name_type in ("generic", "both"):
        payload = fetch_json(f"{base}?drug_name={encoded}&name_type={name_type}&pagesize=100", timeout)
        rows = payload.get("data") or []
        if rows:
            return rows
    return []


def parse_date(value: str | None) -> date:
    if not value:
        return date.min
    candidates = (value[:10], value)
    for candidate, fmt in (
        (candidates[0], "%Y-%m-%d"),
        (candidates[1], "%b %d, %Y"),
        (candidates[1], "%B %d, %Y"),
    ):
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return date.min


def select_dailymed_candidate(source: dict[str, Any], timeout: int) -> dict[str, Any]:
    candidates = dailymed_candidates(source["query"], timeout)
    required = [term.upper() for term in source.get("required_terms", [])]
    excluded = [term.upper() for term in source.get("excluded_terms", [])]

    # Normalize slash-joined required terms ("A/B") into separate tokens so combo
    # labels like "SACUBITRIL AND VALSARTAN" still match.
    normalized_required: list[str] = []
    for term in required:
        parts = [part.strip() for part in term.replace("/", " ").split() if part.strip()]
        normalized_required.extend(parts)
    if not normalized_required:
        normalized_required = required

    matches = []
    for candidate in candidates:
        title = str(candidate.get("title", "")).upper()
        if all(term in title for term in normalized_required) and not any(term in title for term in excluded):
            matches.append(candidate)
    if not matches and "/" in str(source.get("query") or ""):
        # Retry with spaces/and instead of slash (registry legacy queries).
        alt_query = (
            str(source["query"]).replace("/", " and ").replace("  ", " ").strip()
        )
        for candidate in dailymed_candidates(alt_query, timeout):
            title = str(candidate.get("title", "")).upper()
            if all(term in title for term in normalized_required) and not any(term in title for term in excluded):
                matches.append(candidate)
    if not matches:
        raise ValueError(f"No DailyMed SPL candidate matched {source['query']}")
    return sorted(
        matches,
        key=lambda item: (parse_date(item.get("published_date")), int(item.get("spl_version") or 0)),
        reverse=True,
    )[0]


def resolved_downloads(source: dict[str, Any], timeout: int) -> tuple[dict[str, Any], list[dict[str, str]]]:
    resolved = dict(source)
    downloads = []
    strategy = source.get("download_strategy", "direct_url")
    if strategy == "dailymed_spl":
        best = select_dailymed_candidate(source, timeout)
        setid = best["setid"]
        resolved.update(
            {
                "title": best.get("title") or source.get("title"),
                "url": f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml",
                "setid": setid,
                "spl_version": best.get("spl_version"),
                "published_date": best.get("published_date"),
            }
        )
        downloads.append({"kind": "xml", "url": resolved["url"], "target_path": source["target_path"]})
        companion_pdf = source.get("companion_pdf_target_path")
        if companion_pdf:
            downloads.append(
                {
                    "kind": "pdf",
                    "url": f"https://dailymed.nlm.nih.gov/dailymed/downloadpdffile.cfm?setId={setid}",
                    "target_path": companion_pdf,
                }
            )
    elif strategy == "direct_url":
        downloads.append(
            {
                "kind": artifact_kind_for_source(source),
                "url": source["url"],
                "target_path": source["target_path"],
            }
        )
    else:
        raise ValueError(f"Unsupported download_strategy={strategy}")
    return resolved, downloads


def manifest_row(
    source: dict[str, Any],
    target: Path,
    status: str,
    detail: str | None = None,
    storage_uri: str | None = None,
    byte_count: int | None = None,
    sha256: str | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row = {
        "source_id": source["source_id"],
        "title": source.get("title"),
        "source_type": source.get("source_type"),
        "publisher": source.get("publisher"),
        "topic": source.get("topic"),
        "url": source.get("url"),
        "target_path": str(source.get("target_path", target)).replace("\\", "/"),
        "status": status,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "license_note": source.get("license_note"),
    }
    if storage_uri:
        row["storage_uri"] = storage_uri
    for field in ("slug", "query", "setid", "spl_version", "published_date"):
        if source.get(field) is not None:
            row[field] = source[field]
    if byte_count is not None:
        row["bytes"] = byte_count
    elif target.exists():
        row["bytes"] = target.stat().st_size
        row["sha256"] = sha256_file(target)
    if sha256:
        row["sha256"] = sha256
    if artifacts:
        row["artifacts"] = artifacts
        for artifact in artifacts:
            if artifact.get("kind") == "xml":
                row["xml"] = artifact["target_path"].replace("\\", "/").removeprefix("raw/drug_labels/")
            if artifact.get("kind") == "pdf":
                row["pdf"] = artifact["target_path"].replace("\\", "/").removeprefix("raw/drug_labels/")
    if detail:
        row["detail"] = detail
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Download curated clinical sources with provenance manifest.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, type=Path)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, type=Path)
    parser.add_argument("--source-id", action="append", help="Limit download to one or more source_id values.")
    parser.add_argument("--source-type", action="append", help="Limit download to one or more source_type values.")
    parser.add_argument("--dry-run", action="store_true", help="Validate registry and print planned downloads only.")
    parser.add_argument("--use-existing", action="store_true", help="Do not re-download files that already exist.")
    parser.add_argument("--storage", choices=["s3"], default="s3")
    parser.add_argument("--s3-bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--s3-prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--s3-endpoint-url", default=DEFAULT_ENDPOINT_URL)
    parser.add_argument("--allow-failures", action="store_true", help="Exit successfully even when some sources fail to download.")
    parser.add_argument("--timeout", default=60, type=int)
    args = parser.parse_args()

    registry = load_json(args.registry)
    rows = []
    client = s3_client(args.s3_endpoint_url) if args.storage == "s3" and not args.dry_run else None
    if client is not None:
        ensure_bucket(client, args.s3_bucket)
    selected_sources = registry.get("sources", [])
    if args.source_id:
        wanted = set(args.source_id)
        selected_sources = [source for source in selected_sources if source.get("source_id") in wanted]
    if args.source_type:
        wanted_types = set(args.source_type)
        selected_sources = [source for source in selected_sources if source.get("source_type") in wanted_types]

    for source in selected_sources:
        target = ROOT / source["target_path"]
        try:
            resolved_source, downloads = resolved_downloads(source, args.timeout) if not args.dry_run else (source, [])
        except Exception as exc:
            rows.append(manifest_row(source, target, "failed", str(exc)))
            continue
        key = s3_key(args.s3_prefix, source["target_path"])
        storage_uri = f"s3://{args.s3_bucket}/{key}" if args.storage == "s3" else None
        if args.dry_run:
            rows.append(manifest_row(source, target, "planned", storage_uri=storage_uri))
            continue
        download_keys = [s3_key(args.s3_prefix, item["target_path"]) for item in downloads]
        if args.storage == "s3" and args.use_existing and all(object_exists(client, args.s3_bucket, item) for item in download_keys):
            artifacts = [
                {
                    "kind": item["kind"],
                    "url": item["url"],
                    "target_path": item["target_path"],
                    "storage_uri": f"s3://{args.s3_bucket}/{s3_key(args.s3_prefix, item['target_path'])}",
                }
                for item in downloads
            ]
            rows.append(manifest_row(resolved_source, target, "existing", storage_uri=storage_uri, artifacts=artifacts))
            continue
        try:
            artifacts = []
            for item in downloads:
                payload = download_bytes(item["url"], args.timeout)
                item = coerce_download_item(item, payload, item["url"])
                validate_payload(item["kind"], item["target_path"], payload, item["url"])
                item_key = s3_key(args.s3_prefix, item["target_path"])
                item_sha = hashlib.sha256(payload).hexdigest()
                client.put_object(
                    Bucket=args.s3_bucket,
                    Key=item_key,
                    Body=payload,
                    Metadata={
                        "source_id": str(resolved_source.get("source_id", "")),
                        "publisher": str(resolved_source.get("publisher", "")),
                        "source_url": str(item.get("url", "")),
                        "kind": item["kind"],
                        "sha256": item_sha,
                    },
                )
                print(f"Uploaded s3://{args.s3_bucket}/{item_key} ({len(payload)} bytes)")
                artifacts.append(
                    {
                        "kind": item["kind"],
                        "url": item["url"],
                        "target_path": item["target_path"],
                        "storage_uri": f"s3://{args.s3_bucket}/{item_key}",
                        "bytes": len(payload),
                        "sha256": item_sha,
                    }
                )
            rows.append(
                manifest_row(
                    resolved_source,
                    target,
                    "downloaded",
                    storage_uri=storage_uri,
                    byte_count=artifacts[0]["bytes"] if artifacts else None,
                    sha256=artifacts[0]["sha256"] if artifacts else None,
                    artifacts=artifacts,
                )
            )
        except Exception as exc:
            detail = str(exc)
            fallback_url = resolved_source.get("html_url")
            if fallback_url:
                try:
                    payload = download_bytes(fallback_url, args.timeout)
                    item = coerce_download_item(
                        {
                            "kind": artifact_kind_for_source(resolved_source),
                            "url": fallback_url,
                            "target_path": resolved_source["target_path"],
                        },
                        payload,
                        fallback_url,
                    )
                    validate_payload(item["kind"], item["target_path"], payload, fallback_url)
                    item_key = s3_key(args.s3_prefix, item["target_path"])
                    item_sha = hashlib.sha256(payload).hexdigest()
                    client.put_object(
                        Bucket=args.s3_bucket,
                        Key=item_key,
                        Body=payload,
                        Metadata={
                            "source_id": str(resolved_source.get("source_id", "")),
                            "publisher": str(resolved_source.get("publisher", "")),
                            "source_url": fallback_url,
                            "kind": item["kind"],
                            "sha256": item_sha,
                        },
                    )
                    print(f"Uploaded s3://{args.s3_bucket}/{item_key} ({len(payload)} bytes, html fallback)")
                    artifacts = [
                        {
                            "kind": item["kind"],
                            "url": fallback_url,
                            "target_path": item["target_path"],
                            "storage_uri": f"s3://{args.s3_bucket}/{item_key}",
                            "bytes": len(payload),
                            "sha256": item_sha,
                        }
                    ]
                    rows.append(
                        manifest_row(
                            resolved_source,
                            target,
                            "downloaded",
                            detail=f"Primary download failed ({detail}); saved HTML fallback.",
                            storage_uri=f"s3://{args.s3_bucket}/{s3_key(args.s3_prefix, item['target_path'])}",
                            byte_count=len(payload),
                            sha256=item_sha,
                            artifacts=artifacts,
                        )
                    )
                    continue
                except Exception as fallback_exc:
                    detail = f"{detail}; html fallback failed: {fallback_exc}"
            rows.append(manifest_row(resolved_source, target, "failed", detail, storage_uri=storage_uri))

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = [row for row in rows if row["status"] == "failed"]
    succeeded = [row for row in rows if row["status"] in {"downloaded", "existing"}]
    print(f"Wrote {len(rows)} source manifest rows to {args.manifest}")
    print(f"Download summary: {len(succeeded)} ok, {len(failed)} failed")
    if failed:
        for row in failed:
            print(f"  FAILED {row.get('source_id')}: {row.get('detail')}")
        if args.allow_failures:
            print(f"Continuing with --allow-failures ({len(succeeded)} sources available).")
            return
        raise SystemExit(f"{len(failed)} download(s) failed; inspect {args.manifest}")


if __name__ == "__main__":
    main()
