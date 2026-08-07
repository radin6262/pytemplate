#!/usr/bin/env python
"""Template download wizard for Pytemplate."""

import click
import json
import requests
import shutil
import os
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm

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


def download_template(template_info: Dict) -> bool:
    """Download a template from the registry with progress bar."""
    name = template_info.get("name")
    url = template_info.get("url")
    description = template_info.get("description", "")

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

            star_str = f" *{stars}" if stars else ""
            version_str = f" v{version}" if version else ""
            click.echo(
                f"  {color(f'[{i:2d}]', fg='cyan')} {color(name, fg='white', bold=True):<20} - {color(desc, fg='white')}")
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