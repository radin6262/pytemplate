#!/usr/bin/env python
"""Template download wizard for PyTemplate."""

import click
import json
import requests
import shutil
import os
import re
from pathlib import Path
from typing import List, Dict, Set, Optional
from tqdm import tqdm
from urllib.parse import urlparse

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Public template registry - Replace with your actual registry URL
REGISTRY_URL = "https://raw.githubusercontent.com/radin6262/pytemplate/refs/heads/main/remote/registry/registry.json"


def color(text: str, fg: str = None, bold: bool = False, dim: bool = False) -> str:
    """Apply color to text using Click."""
    return click.style(text, fg=fg, bold=bold, dim=dim)


def fetch_registry() -> List[Dict]:
    """Fetch the template registry from the web."""
    try:
        click.echo(color(f"Fetching registry from: {REGISTRY_URL}", fg="white", dim=True))
        response = requests.get(REGISTRY_URL, timeout=10, stream=True)
        if response.status_code == 200:
            data = response.json()
            templates = data.get("templates", [])
            click.echo(color(f"[OK] Found {len(templates)} templates in registry", fg="green"))
            return templates
        else:
            click.echo(color(f"[ERROR] Failed to fetch registry: {response.status_code}", fg="red"))
            return []
    except requests.exceptions.ConnectionError:
        click.echo(color("[ERROR] No internet connection. Please check your network.", fg="red"))
        return []
    except requests.exceptions.Timeout:
        click.echo(color("[ERROR] Connection timed out. Please try again.", fg="red"))
        return []
    except Exception as e:
        click.echo(color(f"[ERROR] Error fetching registry: {e}", fg="red"))
        return []


def extract_reference_files(template_content: str) -> Set[str]:
    """Extract reference file names from template content."""
    references = set()

    # Look for @filename in file content
    # Pattern matches: filename: @reference or filename: @reference with spaces
    pattern = r':\s*@([^\s\n]+)'
    matches = re.findall(pattern, template_content)

    for match in matches:
        # Clean up the reference name (remove any trailing punctuation)
        ref_name = match.strip().rstrip('.,;:')
        if ref_name:
            references.add(ref_name)

    return references


def get_base_url(template_url: str) -> str:
    """Get the base URL from a template URL (same folder as the template)."""
    parsed = urlparse(template_url)
    # Get the directory path without the filename
    path_parts = parsed.path.rsplit('/', 1)
    base_path = path_parts[0] if len(path_parts) > 1 else parsed.path
    return f"{parsed.scheme}://{parsed.netloc}{base_path}"


def download_reference_file(ref_name: str, base_url: str, templates_dir: Path, pbar: tqdm = None) -> bool:
    """Download a single reference file from the same folder as the template with progress."""
    ref_path = templates_dir / f"@{ref_name}"

    if ref_path.exists():
        if pbar:
            pbar.update(1)
        click.echo(color(f"  [SKIP] Reference @{ref_name} already exists", fg="yellow"))
        return True

    # Only try the @refname format (no .txt extensions or other variations)
    url = f"{base_url}/@{ref_name}"

    try:
        # Stream download with progress for the reference file
        response = requests.get(url, timeout=10, stream=True)
        if response.status_code == 200:
            total_size = int(response.headers.get('content-length', 0))

            # Use a nested progress bar for the individual file
            with tqdm(total=total_size, unit='B', unit_scale=True,
                      desc=f"  @{ref_name}", leave=False, position=1) as ref_pbar:
                with open(ref_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            ref_pbar.update(len(chunk))

            if pbar:
                pbar.update(1)
            click.echo(color(f"  [OK] Downloaded reference: @{ref_name}", fg="green"))
            return True
        else:
            if pbar:
                pbar.update(1)
            click.echo(color(f"  [ERROR] Status {response.status_code} for @{ref_name}", fg="red"))
            return False
    except Exception as e:
        if pbar:
            pbar.update(1)
        click.echo(color(f"  [ERROR] Failed to download @{ref_name}: {e}", fg="red"))
        return False


def download_template(template_info: Dict) -> bool:
    """Download a template from the registry with progress bar."""
    name = template_info.get("name")
    url = template_info.get("url")
    description = template_info.get("description", "")
    references_list = template_info.get("references", [])  # Optional: pre-defined in registry

    if not name or not url:
        click.echo(color("[ERROR] Invalid template info: missing name or url", fg="red"))
        return False

    dest_path = TEMPLATES_DIR / f"{name}.setup"

    if dest_path.exists():
        if not click.confirm(color(f"Template '{name}' already exists. Overwrite?", fg="yellow")):
            return False

    try:
        click.echo(color(f"Downloading {name}...", fg="cyan"))

        # Stream download with progress bar
        response = requests.get(url, timeout=30, stream=True)
        if response.status_code == 200:
            total_size = int(response.headers.get('content-length', 0))

            # Create progress bar
            with tqdm(total=total_size, unit='B', unit_scale=True, desc=f"Downloading {name}") as pbar:
                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

            click.echo(color(f"[OK] Downloaded: {name}", fg="green"))
            if description:
                click.echo(color(f"  Description: {description}", fg="white", dim=True))

            # Extract and download reference files
            template_content = dest_path.read_text()
            references = extract_reference_files(template_content)

            # Also use any references from the registry
            if references_list:
                references.update(references_list)

            if references:
                click.echo(color(f"\n  Found {len(references)} reference file(s):", fg="yellow"))
                for ref in sorted(references):
                    click.echo(color(f"    - @{ref}", fg="white", dim=True))

                # Ask user if they want to download references
                if click.confirm(color("\n  Download reference files?", fg="yellow"), default=True):
                    click.echo(color(f"\n  Downloading reference files from same folder...", fg="cyan"))

                    # Get base URL from template URL (same folder)
                    base_url = get_base_url(url)
                    click.echo(color(f"  Base URL: {base_url}", fg="white", dim=True))

                    # Create a progress bar for reference files
                    with tqdm(total=len(references), desc="  Downloading references", unit="file") as ref_pbar:
                        success_count = 0
                        for ref in sorted(references):
                            if download_reference_file(ref, base_url, TEMPLATES_DIR, ref_pbar):
                                success_count += 1

                    click.echo(
                        color(f"  [OK] Downloaded {success_count}/{len(references)} reference files", fg="green"))

                    if success_count < len(references):
                        click.echo(color(f"  [WARNING] Some reference files could not be downloaded", fg="yellow"))
                        click.echo(
                            color(f"  You may need to create them manually or check the template source.", fg="white",
                                  dim=True))
            else:
                click.echo(color(f"\n  No reference files found in template.", fg="white", dim=True))

            return True
        else:
            click.echo(color(f"[ERROR] Failed to download: HTTP {response.status_code}", fg="red"))
            return False
    except requests.exceptions.Timeout:
        click.echo(color("[ERROR] Download timed out. Please try again.", fg="red"))
        return False
    except Exception as e:
        click.echo(color(f"[ERROR] Error downloading: {e}", fg="red"))
        return False


def download_from_url():
    """Download a template from a manual URL."""
    click.echo("\n" + color("MANUAL DOWNLOAD", fg="cyan", bold=True))

    url = click.prompt(color("Template URL", fg="cyan"), default="", show_default=False)
    if not url:
        return

    name = click.prompt(color("Template name", fg="cyan"), default="", show_default=False)
    if not name:
        return

    description = click.prompt(color("Description (optional)", fg="cyan"), default="", show_default=False)

    template_info = {
        "name": name,
        "url": url,
        "description": description
    }

    download_template(template_info)


def interactive_downloader():
    """Interactive template downloader."""
    click.echo("\n" + color("=" * 60, fg="blue", bold=True))
    click.echo(color("TEMPLATE DOWNLOADER", fg="cyan", bold=True))
    click.echo(color("=" * 60, fg="blue", bold=True))

    # Ensure templates directory exists
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    click.echo(color("\nFetching template registry...", fg="yellow"))
    templates = fetch_registry()

    if not templates:
        click.echo(color("\nNo templates found in registry.", fg="red"))
        click.echo(color("You can still enter a URL manually.", fg="yellow"))

        if click.confirm(color("\nWould you like to download from a URL manually?", fg="yellow")):
            download_from_url()
        return

    while True:
        click.echo("\n" + color("AVAILABLE TEMPLATES:", fg="yellow", bold=True))
        click.echo(color("-" * 60, fg="blue"))

        for i, t in enumerate(templates, 1):
            name = t.get("name", "unknown")
            desc = t.get("description", "No description")
            author = t.get("author", "Unknown")
            version = t.get("version", "")
            stars = t.get("stars", "")
            refs = t.get("references", [])

            star_str = f" *{stars}" if stars else ""
            version_str = f" v{version}" if version else ""
            refs_str = f" [{len(refs)} refs]" if refs else ""
            click.echo(
                f"  {color(f'[{i:2d}]', fg='cyan')} {color(name, fg='white', bold=True):<20} - {color(desc, fg='white')}{color(refs_str, fg='yellow')}")
            click.echo(
                f"        {color(f'by {author}', fg='white', dim=True)}{color(version_str, fg='white', dim=True)}{color(star_str, fg='yellow')}")

        click.echo("\n" + color("-" * 60, fg="blue"))
        click.echo(color("ACTIONS:", fg="yellow", bold=True))
        click.echo("  " + color("[number]", fg="cyan") + "  Download template")
        click.echo("  " + color("[u]", fg="green", bold=True) + "       Download from URL manually")
        click.echo("  " + color("[r]", fg="magenta", bold=True) + "       Refresh registry")
        click.echo("  " + color("[q]", fg="red", bold=True) + "       Quit")
        click.echo(color("=" * 60, fg="blue", bold=True))

        choice = click.prompt("\nChoice", default="q", show_default=False)

        if choice.lower() == 'q':
            break

        elif choice.lower() == 'u':
            download_from_url()
            continue

        elif choice.lower() == 'r':
            click.echo(color("\nRefreshing registry...", fg="yellow"))
            templates = fetch_registry()
            continue

        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(templates):
                    template = templates[idx]

                    # Show template details
                    click.echo("\n" + color("=" * 50, fg="blue"))
                    click.echo(color(f"TEMPLATE: {template.get('name')}", fg="cyan", bold=True))
                    click.echo(color("=" * 50, fg="blue"))
                    click.echo(color(f"  Description: {template.get('description', 'N/A')}", fg="white"))
                    click.echo(color(f"  Author: {template.get('author', 'N/A')}", fg="white"))
                    click.echo(color(f"  Version: {template.get('version', 'N/A')}", fg="white"))
                    click.echo(color(f"  Category: {template.get('category', 'N/A')}", fg="white"))
                    if template.get('tags'):
                        click.echo(color(f"  Tags: {', '.join(template.get('tags', []))}", fg="white"))

                    # Show references if available
                    refs = template.get('references', [])
                    if refs:
                        click.echo(color(f"  References: {len(refs)} file(s)", fg="yellow"))
                        for ref in refs[:5]:
                            click.echo(color(f"    - @{ref}", fg="white", dim=True))
                        if len(refs) > 5:
                            click.echo(color(f"    ... and {len(refs) - 5} more", fg="white", dim=True))

                    click.echo(color("=" * 50, fg="blue"))

                    if click.confirm(color("\nDownload this template?", fg="yellow")):
                        download_template(template)
                else:
                    click.echo(color("Invalid selection.", fg="red"))
            except ValueError:
                click.echo(color(f"Unknown command: {choice}", fg="red"))


def download_template_from_args(name: str):
    """Download a specific template by name from the command line."""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    click.echo(color(f"Searching for template: {name}", fg="yellow"))
    templates = fetch_registry()

    if not templates:
        click.echo(color("[ERROR] No templates found in registry.", fg="red"))
        return

    # Search for template by name
    found = None
    for t in templates:
        if t.get("name", "").lower() == name.lower():
            found = t
            break

    if found:
        click.echo(color(f"Found template: {found.get('name')}", fg="green"))
        click.echo(color(f"  Description: {found.get('description', 'N/A')}", fg="white"))
        click.echo(color(f"  Author: {found.get('author', 'N/A')}", fg="white"))

        if click.confirm(color("\nDownload this template?", fg="yellow")):
            download_template(found)
    else:
        click.echo(color(f"[ERROR] Template '{name}' not found in registry.", fg="red"))
        click.echo(color("Available templates:", fg="yellow"))
        for t in templates:
            click.echo(color(f"  - {t.get('name')}", fg="white"))


@click.command()
@click.argument('name', required=False)
def main(name):
    """Download templates from the PyTemplate template registry.

    If NAME is provided, download that specific template directly.
    Otherwise, open the interactive downloader.

    Examples:

        downloadtemplate
            Open interactive template browser

        downloadtemplate flet
            Download the 'flet' template directly
    """
    if name:
        download_template_from_args(name)
    else:
        interactive_downloader()


if __name__ == "__main__":
    main()