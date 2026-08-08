"""Template downloading backend for PyTemplate."""

import json
import re
import requests
from pathlib import Path
from typing import List, Dict, Set, Optional, Callable
from urllib.parse import urlparse


TEMPLATES_DIR = Path(__file__).parent / "templates"

REGISTRY_URL = (
    "https://raw.githubusercontent.com/radin6262/pytemplate/"
    "refs/heads/main/remote/registry/registry.json"
)


class TemplateDownloadError(Exception):
    """Raised when a template download fails."""


def fetch_registry() -> List[Dict]:
    """Fetch the template registry from the web.

    Returns:
        A list of template metadata dictionaries.

    Raises:
        TemplateDownloadError: If the registry cannot be fetched.
    """
    try:
        response = requests.get(REGISTRY_URL, timeout=10)
        response.raise_for_status()

        data = response.json()
        return data.get("templates", [])

    except requests.exceptions.ConnectionError as e:
        raise TemplateDownloadError(
            "No internet connection."
        ) from e

    except requests.exceptions.Timeout as e:
        raise TemplateDownloadError(
            "Connection timed out."
        ) from e

    except requests.exceptions.RequestException as e:
        raise TemplateDownloadError(
            f"Failed to fetch registry: {e}"
        ) from e

    except (ValueError, json.JSONDecodeError) as e:
        raise TemplateDownloadError(
            "Registry returned invalid JSON."
        ) from e


def extract_reference_files(template_content: str) -> Set[str]:
    """Extract reference file names from template content."""
    references = set()

    pattern = r":\s*@([^\s\n]+)"
    matches = re.findall(pattern, template_content)

    for match in matches:
        ref_name = match.strip().rstrip(".,;:")

        if ref_name:
            references.add(ref_name)

    return references


def get_base_url(template_url: str) -> str:
    """Get the directory URL containing the template."""
    parsed = urlparse(template_url)

    path_parts = parsed.path.rsplit("/", 1)
    base_path = (
        path_parts[0]
        if len(path_parts) > 1
        else parsed.path
    )

    return f"{parsed.scheme}://{parsed.netloc}{base_path}"


def download_reference_file(
    ref_name: str,
    base_url: str,
    templates_dir: Path,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> bool:
    """Download a single template reference file.

    Args:
        ref_name:
            Reference filename without the @ prefix.

        base_url:
            Directory containing the reference file.

        templates_dir:
            Destination directory.

        progress_callback:
            Optional callback receiving (downloaded_bytes, total_bytes).

    Returns:
        True if downloaded successfully, otherwise False.
    """
    ref_path = templates_dir / f"@{ref_name}"

    if ref_path.exists():
        return True

    url = f"{base_url}/@{ref_name}"

    try:
        response = requests.get(
            url,
            timeout=10,
            stream=True,
        )

        if response.status_code != 200:
            return False

        total_size = int(
            response.headers.get("content-length", 0)
        )

        downloaded = 0

        with open(ref_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue

                file.write(chunk)
                downloaded += len(chunk)

                if progress_callback:
                    progress_callback(
                        downloaded,
                        total_size,
                    )

        return True

    except (requests.RequestException, OSError):
        if ref_path.exists():
            try:
                ref_path.unlink()
            except OSError:
                pass

        return False


def download_template(
    template_info: Dict,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    reference_progress_callback: Optional[
        Callable[[str, int, int], None]
    ] = None,
    overwrite: bool = False,
) -> Dict:
    """Download a template and its reference files.

    Args:
        template_info:
            Template metadata from the registry.

        progress_callback:
            Called with (downloaded_bytes, total_bytes)
            while downloading the main template.

        reference_progress_callback:
            Called with
            (reference_name, downloaded_bytes, total_bytes)
            while downloading references.

        overwrite:
            Whether an existing template should be overwritten.

    Returns:
        A result dictionary containing download information.

    Raises:
        TemplateDownloadError: If the template download fails.
        ValueError: If template metadata is invalid.
    """
    name = template_info.get("name")
    url = template_info.get("url")
    description = template_info.get("description", "")
    references_list = template_info.get("references", [])

    if not name or not url:
        raise ValueError(
            "Invalid template info: missing name or url."
        )

    TEMPLATES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    dest_path = TEMPLATES_DIR / f"{name}.setup"

    if dest_path.exists() and not overwrite:
        raise FileExistsError(
            f"Template '{name}' already exists."
        )

    try:
        response = requests.get(
            url,
            timeout=30,
            stream=True,
        )

        if response.status_code != 200:
            raise TemplateDownloadError(
                f"Failed to download template: "
                f"HTTP {response.status_code}"
            )

        total_size = int(
            response.headers.get("content-length", 0)
        )

        downloaded = 0

        with open(dest_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue

                file.write(chunk)
                downloaded += len(chunk)

                if progress_callback:
                    progress_callback(
                        downloaded,
                        total_size,
                    )

    except requests.exceptions.Timeout as e:
        raise TemplateDownloadError(
            "Download timed out."
        ) from e

    except requests.exceptions.RequestException as e:
        raise TemplateDownloadError(
            f"Download failed: {e}"
        ) from e

    except OSError as e:
        raise TemplateDownloadError(
            f"Could not save template: {e}"
        ) from e

    try:
        template_content = dest_path.read_text()
    except OSError as e:
        raise TemplateDownloadError(
            f"Could not read downloaded template: {e}"
        ) from e

    references = extract_reference_files(
        template_content
    )

    if references_list:
        references.update(references_list)

    reference_results = {}

    if references:
        base_url = get_base_url(url)

        for ref in sorted(references):
            def ref_progress(
                downloaded: int,
                total: int,
                ref_name=ref,
            ):
                if reference_progress_callback:
                    reference_progress_callback(
                        ref_name,
                        downloaded,
                        total,
                    )

            success = download_reference_file(
                ref,
                base_url,
                TEMPLATES_DIR,
                progress_callback=ref_progress,
            )

            reference_results[ref] = success

    return {
        "success": True,
        "name": name,
        "path": dest_path,
        "description": description,
        "references": reference_results,
        "references_total": len(references),
        "references_downloaded": sum(
            1 for success in reference_results.values()
            if success
        ),
    }


def find_template(
    name: str,
    templates: List[Dict],
) -> Optional[Dict]:
    """Find a template by name, case-insensitively."""
    name = name.lower()

    for template in templates:
        if template.get("name", "").lower() == name:
            return template

    return None


def download_template_from_name(
    name: str,
    overwrite: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    reference_progress_callback: Optional[
        Callable[[str, int, int], None]
    ] = None,
) -> Dict:
    """Find and download a template by name.

    This function is intended to be called by the CLI,
    TUI, GUI, API, or another frontend.
    """
    templates = fetch_registry()

    template = find_template(
        name,
        templates,
    )

    if not template:
        raise TemplateDownloadError(
            f"Template '{name}' not found in registry."
        )

    return download_template(
        template,
        progress_callback=progress_callback,
        reference_progress_callback=reference_progress_callback,
        overwrite=overwrite,
    )


def get_templates() -> List[Dict]:
    """Return all templates available in the remote registry."""
    return fetch_registry()