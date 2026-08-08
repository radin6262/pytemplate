"""Template manager for PyTemplate - Interactive template navigator (TUI)."""

import click
import os
import shutil
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# Import the TUI runner (no circular import since we pass the manager)
from .template_manager_tui import run_template_manager_tui


def color(text: str, fg: str = None, bold: bool = False, dim: bool = False) -> str:
    """Apply color to text using Click."""
    return click.style(text, fg=fg, bold=bold, dim=dim)


class TemplateManager:
    """Manages PyTemplate templates with metadata and organization."""

    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self.metadata_file = templates_dir / "registry.json"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict:
        """Load template metadata from registry.json."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except:
                return {"templates": {}}
        return {"templates": {}}

    def _save_metadata(self):
        """Save template metadata to registry.json."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    def _extract_metadata(self, template_path: Path) -> Dict:
        """Extract metadata from a .setup file."""
        metadata = {
            "name": template_path.stem,
            "description": "",
            "author": "",
            "version": "1.0.0",
            "category": "uncategorized",
            "tags": [],
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
            "type": "local",
            "path": str(template_path)
        }

        try:
            content = template_path.read_text()
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('# @'):
                    parts = line[3:].split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        if key == 'template':
                            metadata['name'] = value
                        elif key == 'description':
                            metadata['description'] = value
                        elif key == 'author':
                            metadata['author'] = value
                        elif key == 'version':
                            metadata['version'] = value
                        elif key == 'category':
                            metadata['category'] = value
                        elif key == 'tags':
                            metadata['tags'] = [t.strip() for t in value.split(',')]
        except:
            pass

        return metadata

    def list_templates(self) -> List[Dict]:
        """List all templates from the templates directory."""
        templates = []

        # Scan the templates directory for .setup files
        for template_file in self.templates_dir.glob("*.setup"):
            # Skip registry.json and other non-template files
            if template_file.name == "registry.json":
                continue
            metadata = self._extract_metadata(template_file)
            templates.append(metadata)

        return sorted(templates, key=lambda x: x["name"])

    def get_template(self, name: str) -> Optional[Dict]:
        """Get template metadata by name."""
        templates = self.list_templates()
        for t in templates:
            if t["name"] == name:
                return t
        return None

    def remove_template(self, name: str) -> bool:
        """Remove a template by name."""
        template = self.get_template(name)
        if not template:
            click.echo(color(f"Template '{name}' not found.", fg="red"))
            return False

        if not click.confirm(color(f"Remove template '{name}'?", fg="yellow")):
            return False

        template_path = Path(template["path"])
        if template_path.exists():
            template_path.unlink()
            click.echo(color(f"[OK] Removed: {name}", fg="green"))
            return True

        click.echo(color(f"Template file not found: {template_path}", fg="red"))
        return False

    def rename_template(self, old_name: str, new_name: str) -> bool:
        """Rename a template."""
        template = self.get_template(old_name)
        if not template:
            click.echo(color(f"Template '{old_name}' not found.", fg="red"))
            return False

        if self.get_template(new_name):
            click.echo(color(f"Template '{new_name}' already exists.", fg="red"))
            return False

        old_path = Path(template["path"])
        new_path = old_path.parent / f"{new_name}.setup"

        if old_path.exists():
            old_path.rename(new_path)
            click.echo(color(f"[OK] Renamed: {old_name} -> {new_name}", fg="green"))
            return True

        click.echo(color(f"Template file not found: {old_path}", fg="red"))
        return False

    def export_template(self, name: str, output_path: Path) -> bool:
        """Export a template to a file."""
        template = self.get_template(name)
        if not template:
            click.echo(color(f"Template '{name}' not found.", fg="red"))
            return False

        source_path = Path(template["path"])
        if not source_path.exists():
            click.echo(color(f"Template file not found: {source_path}", fg="red"))
            return False

        try:
            shutil.copy2(source_path, output_path)
            click.echo(color(f"[OK] Exported: {output_path}", fg="green"))
            return True
        except Exception as e:
            click.echo(color(f"Error exporting template: {e}", fg="red"))
            return False

    def import_template(self, source_path: Path) -> bool:
        """Import a template from a file."""
        if not source_path.exists():
            click.echo(color(f"File not found: {source_path}", fg="red"))
            return False

        if source_path.suffix != '.setup':
            click.echo(color("File must have .setup extension.", fg="red"))
            return False

        name = source_path.stem
        dest_path = self.templates_dir / f"{name}.setup"

        if dest_path.exists():
            if not click.confirm(color(f"Template '{name}' already exists. Overwrite?", fg="yellow")):
                return False

        try:
            shutil.copy2(source_path, dest_path)
            click.echo(color(f"[OK] Imported: {name}", fg="green"))
            return True
        except Exception as e:
            click.echo(color(f"Error importing template: {e}", fg="red"))
            return False


def launch_template_builder(template_name: str = None):
    """Launch the template builder with optional template name."""
    script_path = Path(__file__).parent / "cli.py"

    if template_name:
        cmd = [sys.executable, str(script_path), "buildtemplate", template_name]
    else:
        name = click.prompt(color("Template name", fg="cyan"), type=str)
        cmd = [sys.executable, str(script_path), "buildtemplate", name]

    click.echo(color(f"\nLaunching template builder...", fg="yellow"))
    click.echo(color(f"Running: {' '.join(cmd)}\n", dim=True))

    try:
        subprocess.run(cmd)
        return True
    except Exception as e:
        click.echo(color(f"Error launching template builder: {e}", fg="red"))
        return False


def launch_template_downloader():
    """Launch the template downloader wizard."""
    script_path = Path(__file__).parent / "downloadtemplate.py"

    if not script_path.exists():
        click.echo(color(f"Download template wizard not found at: {script_path}", fg="red"))

    click.echo(color(f"\nLaunching template downloader...", fg="yellow"))
    click.echo(color(f"Running: {script_path}\n", dim=True))

    try:
        subprocess.run([sys.executable, str(script_path)])
        return True
    except Exception as e:
        click.echo(color(f"Error launching template downloader: {e}", fg="red"))
        return False


def interactive_template_manager(templates_dir: Path):
    """Run the interactive template manager (TUI)."""
    # Create the manager instance
    manager = TemplateManager(templates_dir)
    # Pass it to the TUI runner (no circular import)
    run_template_manager_tui(manager)


def register_commands(cli_group):
    """Register template manager command with the CLI group."""

    @cli_group.command()
    def templates():
        """Open interactive template navigator (TUI)."""
        templates_dir = Path(__file__).parent / "templates"
        interactive_template_manager(templates_dir)